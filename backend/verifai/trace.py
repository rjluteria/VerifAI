"""Opt-in, bounded causal timing; never accept content, URLs or credentials."""

import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE = ContextVar("verification_trace", default=None)
_PARENT = ContextVar("verification_trace_parent", default=None)
_STAGES = {
    "job",
    "claim_extraction",
    "search",
    "alternate_search",
    "source_fetch",
    "ranking",
    "classification",
    "aggregation",
    "model_call",
    "model_queue",
    "pacing_queue",
    "provider_transport",
    "provider_body",
    "retry_wait",
    "cooldown_wait",
    "embedding",
}
_MODEL = re.compile(
    r"^(?:nvidia|poolside|openai|z-ai|meta|google|mistralai|deepseek-ai|qwen|microsoft|ibm)/[a-z0-9][a-z0-9._-]{0,100}$"
)


def sanitized(fields):
    output = {}
    for key, value in fields.items():
        if key == "model" and isinstance(value, str) and _MODEL.fullmatch(value):
            output[key] = value
        elif key in {"count", "attempt", "http_status", "source_id", "claim_id"}:
            if type(value) is int and 0 <= value <= 1000000:
                output[key] = value
        elif key in {"ok", "timed_out", "accessible"} and type(value) is bool:
            output[key] = value
        elif key == "failure" and value in {"http", "timeout", "error"}:
            output[key] = value
    return output


class Trace:
    def __init__(self, job_id, limit=2000):
        if not isinstance(job_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", job_id
        ):
            raise ValueError("trace-job-id")
        self.job_id = job_id
        self.limit = max(1, min(2000, limit))
        self.started = time.perf_counter()
        self.started_epoch_ms = int(time.time() * 1000)
        self.lock = threading.Lock()
        self.events = []
        self.truncated = False

    def begin(self, stage, fields):
        if stage not in _STAGES:
            raise ValueError("trace-stage")
        with self.lock:
            if len(self.events) >= self.limit:
                self.truncated = True
                return None
            row = {
                "id": len(self.events) + 1,
                "parent": _PARENT.get(),
                "stage": stage,
                "start_ms": round((time.perf_counter() - self.started) * 1000, 3),
                **sanitized(fields),
            }
            self.events.append(row)
            return row

    def end(self, row, fields):
        if row is None:
            return
        with self.lock:
            row.update(sanitized(fields))
            row["end_ms"] = round((time.perf_counter() - self.started) * 1000, 3)

    def snapshot(self):
        with self.lock:
            events = [dict(row) for row in self.events]
        return {
            "version": 1,
            "job_id": self.job_id,
            "clock": "backend-perf-counter",
            "started_epoch_ms": self.started_epoch_ms,
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 3),
            "events": events,
            "truncated": self.truncated,
            "timing_rule": "Nested/concurrent spans overlap; never add them as total latency.",
        }


@contextmanager
def trace_scope(trace):
    active = _ACTIVE.set(trace)
    parent = _PARENT.set(None)
    try:
        yield
    finally:
        _PARENT.reset(parent)
        _ACTIVE.reset(active)


@contextmanager
def measured(stage, **fields):
    trace = _ACTIVE.get()
    if trace is None:
        yield {}
        return
    row = trace.begin(stage, fields)
    parent = _PARENT.set(row["id"] if row else _PARENT.get())
    outcome = {}
    try:
        yield outcome
        outcome.setdefault("ok", True)
    except Exception as error:
        outcome["ok"] = False
        code = getattr(error, "code", None)
        if type(code) is int:
            outcome.update(failure="http", http_status=code)
        elif isinstance(error, TimeoutError) or isinstance(
            getattr(error, "reason", None), TimeoutError
        ):
            outcome.update(failure="timeout", timed_out=True)
        else:
            outcome["failure"] = "error"
        raise
    finally:
        trace.end(row, outcome)
        _PARENT.reset(parent)
