"""Overlapping interval accounting for complete, sanitized causal traces."""

import math


def union_ms(intervals):
    total = 0.0
    right = 0.0
    for start, end in sorted(intervals):
        total += max(0, end - max(start, right))
        right = max(right, end)
    return total


def summary(trace):
    elapsed = trace.get("elapsed_ms")
    if (
        type(elapsed) not in (int, float)
        or not math.isfinite(elapsed)
        or elapsed <= 0
        or trace.get("truncated")
    ):
        raise ValueError("Incomplete or invalid timing trace")
    events = trace.get("events", [])
    intervals = {}
    for row in events:
        a, b = row.get("start_ms"), row.get("end_ms")
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (a, b))
            or not 0 <= a <= b <= elapsed + 1
        ):
            raise ValueError("Incomplete or invalid timing event")
        intervals.setdefault(row["stage"], []).append((a, min(b, elapsed)))
    provider = union_ms(
        intervals.get("provider_transport", []) + intervals.get("provider_body", [])
    )
    models = union_ms(intervals.get("model_call", []))
    return {
        "elapsed_ms": elapsed,
        "provider_network_wall_ms": round(provider, 3),
        "model_call_wall_ms": round(models, 3),
        "outside_model_call_wall_ms": round(max(0, elapsed - models), 3),
        "outside_provider_network_wall_ms": round(max(0, elapsed - provider), 3),
        "raw_stage_unions_ms": {k: round(union_ms(v), 3) for k, v in intervals.items()},
        "accounting": "Each union counts overlap once. Stage unions overlap each other: never add them. Provider time includes network and service, not proven model compute alone. Outside model time may include retrieval, cooldowns and application work.",
    }
