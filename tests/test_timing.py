import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.timing import summary


class TimingTests(unittest.TestCase):
    def test_nested_and_parallel_spans_are_not_added(self):
        result = summary(
            {
                "elapsed_ms": 100,
                "events": [
                    {"stage": "model_call", "start_ms": 10, "end_ms": 90},
                    {"stage": "model_call", "start_ms": 20, "end_ms": 95},
                    {"stage": "provider_transport", "start_ms": 15, "end_ms": 80},
                    {"stage": "provider_transport", "start_ms": 30, "end_ms": 90},
                    {"stage": "provider_body", "start_ms": 80, "end_ms": 92},
                ],
            }
        )
        self.assertEqual(result["provider_network_wall_ms"], 77)
        self.assertEqual(result["model_call_wall_ms"], 85)
        self.assertEqual(result["outside_model_call_wall_ms"], 15)

    def test_partial_or_truncated_trace_cannot_prove_fast_completion(self):
        for trace in [
            {"elapsed_ms": 0, "events": []},
            {"elapsed_ms": 10, "truncated": True, "events": []},
            {"elapsed_ms": 10, "events": [{"stage": "model_call", "start_ms": 0}]},
            {
                "elapsed_ms": 10,
                "events": [{"stage": "model_call", "start_ms": 2, "end_ms": 1}],
            },
        ]:
            with self.assertRaises(ValueError):
                summary(trace)
