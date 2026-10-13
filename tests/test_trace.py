import json
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.network import FetchRejected
from verifai.server import Service
from verifai.trace import Trace, measured, trace_scope


class TraceTests(unittest.TestCase):
    def test_default_off_and_whitelist_do_not_store_sensitive_inputs(self):
        with measured(
            "source_fetch", url="https://private.example/secret", token="key"
        ) as fields:
            fields["claim"] = "private conversation"
        trace = Trace("safe-job")
        with trace_scope(trace), measured("job"):
            with measured(
                "source_fetch", url="https://private.example/secret", token="key"
            ) as fields:
                fields.update(
                    quote="private source",
                    model="private/key",
                    http_status=403,
                    accessible=False,
                )
        raw = json.dumps(trace.snapshot())
        for forbidden in ("private", "secret", "token", "quote", "conversation"):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(trace.snapshot()["events"][1]["http_status"], 403)
        self.assertFalse(trace.snapshot()["events"][1]["accessible"])

    def test_parallel_spans_share_parent_without_mixing_jobs_and_are_bounded(self):
        trace = Trace("parallel", limit=3)
        barrier = threading.Barrier(2)

        def child():
            with measured("source_fetch"):
                barrier.wait(timeout=2)
                time.sleep(0.01)

        with trace_scope(trace), measured("job"):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(copy_context().run, child) for _ in range(2)]
                for future in futures:
                    future.result()
            with measured("ranking"):
                pass
        snapshot = trace.snapshot()
        self.assertEqual(len(snapshot["events"]), 3)
        self.assertTrue(snapshot["truncated"])
        self.assertEqual([row["parent"] for row in snapshot["events"]], [None, 1, 1])
        self.assertTrue(
            all(row["end_ms"] >= row["start_ms"] for row in snapshot["events"])
        )
        other = Trace("other")
        with trace_scope(other), measured("job"):
            pass
        self.assertEqual(len(other.snapshot()["events"]), 1)

    def test_http_and_timeout_failures_are_numeric_and_content_free(self):
        trace = Trace("failures")
        for failure in (
            FetchRejected("private URL secret", code=404),
            TimeoutError("secret"),
        ):
            with self.assertRaises(type(failure)):
                with (
                    trace_scope(trace),
                    measured("provider_transport", model="openai/gpt-oss-20b"),
                ):
                    raise failure
        rows = trace.snapshot()["events"]
        self.assertEqual(rows[0]["http_status"], 404)
        self.assertTrue(rows[1]["timed_out"])
        self.assertNotIn("secret", json.dumps(rows))

    def test_job_trace_is_opt_in_owned_and_not_added_to_factual_result(self):
        class Engine:
            def verify(self, text, citations, progress):
                with measured("claim_extraction", count=1):
                    return {"claims": [], "unsupported": []}

        for enabled in ("0", "1"):
            with patch.dict("os.environ", {"ENABLE_CAUSAL_DIAGNOSTICS": enabled}):
                service = Service(Engine())
            key = service.start("owner", {"text": "private text", "citations": []})
            end = time.monotonic() + 2
            while (
                service.read_job("owner", key)["stage"] != "Complete"
                and time.monotonic() < end
            ):
                time.sleep(0.01)
            job = service.read_job("owner", key)
            self.assertEqual(job["stage"], "Complete")
            self.assertIsNone(service.read_job("stranger", key))
            self.assertEqual("trace" in job, enabled == "1")
            self.assertNotIn("trace", job["result"])
            if enabled == "1":
                self.assertNotIn("private text", json.dumps(job["trace"]))
                self.assertEqual(job["trace"]["job_id"], key)

    def test_parallel_review_candidate_preserves_order_and_actual_reviewer_identity(
        self,
    ):
        from verifai.model import review_pair

        barrier = threading.Barrier(2)

        class Models:
            names = ["nvidia/primary", "openai/secondary"]
            parallel_reviews = True

            def review(self, name, claim, evidence, reconsider=False):
                barrier.wait(timeout=2)
                return {"model": name, "label": "SUPPORTED", "quotes": [evidence]}

        trace = Trace("pair")
        with trace_scope(trace), measured("classification"):
            reviews, failures = review_pair(Models(), "synthetic", "source")
        self.assertEqual([row["model"] for row in reviews], Models.names)
        self.assertEqual(failures, [])
        self.assertTrue(all(row["label"] == "SUPPORTED" for row in reviews))

    def test_candidate_pacing_config_is_bounded_and_baseline_default_unchanged(self):
        from verifai.model import request_interval

        for value, expected in [
            ("3", 3),
            ("0", 0),
            ("-1", 0),
            ("100", 3),
            ("nan", 3),
            ("bad", 3),
        ]:
            with patch.dict("os.environ", {"MODEL_REQUEST_INTERVAL_SECONDS": value}):
                self.assertEqual(request_interval(), expected)


if __name__ == "__main__":
    unittest.main()
