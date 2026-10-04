import io
import json
import sys
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.engine import Engine, classify
from verifai.model import ModelError, Models
from verifai.server import Service


class ReliabilityTests(unittest.TestCase):
    def test_queued_prefetch_does_not_start_sources_after_job_budget_expires(self):
        clock = [0]
        fetched = []

        class Extractor:
            def extract(self, text):
                return ([{"text": text, "quote": text}], [])

        def fetcher(url):
            fetched.append(url)
            clock[0] = 901
            return {
                "url": url,
                "text": "Synthetic source text.",
                "accessible": True,
                "checked_at": 0,
                "sha256": "synthetic",
            }

        with patch("verifai.engine.time.monotonic", side_effect=lambda: clock[0]):
            result = Engine(Extractor(), fetcher, lambda c: []).verify(
                "A is B.", ["https://example.org/" + str(i) for i in range(12)]
            )
        self.assertLessEqual(len(fetched), 2)
        self.assertEqual(result["claims"][0]["label"], "UNVERIFIED")
        self.assertIn(
            "Verification time budget exhausted.", result["claims"][0]["errors"]
        )

    def test_two_job_capacity_and_owner_results_remain_isolated(self):
        entered = threading.Barrier(3)
        release = threading.Event()

        class HeldEngine:
            def verify(self, text, citations, progress):
                entered.wait(timeout=2)
                if not release.wait(2):
                    raise TimeoutError()
                return {"synthetic_marker": text}

        service = Service(HeldEngine())
        first = service.start("owner-a", {"text": "case-a", "citations": []})
        second = service.start("owner-b", {"text": "case-b", "citations": []})
        try:
            entered.wait(timeout=2)
            self.assertIsNone(
                service.start("owner-c", {"text": "case-c", "citations": []})
            )
        finally:
            release.set()
        deadline = time.monotonic() + 2
        while any(service.jobs[key]["stage"] != "Complete" for key in [first, second]):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        self.assertEqual(service.jobs[first]["owner"], "owner-a")
        self.assertEqual(service.jobs[first]["result"]["synthetic_marker"], "case-a")
        self.assertEqual(service.jobs[second]["owner"], "owner-b")
        self.assertEqual(service.jobs[second]["result"]["synthetic_marker"], "case-b")

    def test_provider_faults_retry_bounded_and_redact_details(self):
        faults = [
            TimeoutError("private content"),
            OSError("private content"),
            urllib.error.HTTPError(
                "https://provider.test", 503, "private content", {}, io.BytesIO()
            ),
        ]
        for fault in faults:
            with self.subTest(fault=type(fault).__name__):
                model = Models()
                model.key = "synthetic-test-key"
                with (
                    patch("verifai.model.paced_open", side_effect=fault) as opened,
                    patch("verifai.model.time.sleep"),
                ):
                    with self.assertRaises(ModelError) as caught:
                        model.call("synthetic-model", "contract", {})
                    self.assertEqual(opened.call_count, 2)
                    self.assertNotIn("private content", str(caught.exception))
                    self.assertNotIn(model.key, str(caught.exception))

    def test_long_rate_limit_creates_cooldown_without_retry_amplification(self):
        model = Models()
        model.key = "synthetic-test-key"
        fault = urllib.error.HTTPError(
            "https://provider.test",
            429,
            "private diagnostic",
            {"Retry-After": "120"},
            io.BytesIO(b"private content"),
        )
        with (
            patch.dict("verifai.model._RATE_LIMITED_UNTIL", {}, clear=True),
            patch("verifai.model.paced_open", side_effect=fault) as opened,
            patch("verifai.model.time.sleep") as slept,
        ):
            for _ in range(2):
                with self.assertRaisesRegex(ModelError, "model-http-429") as caught:
                    model.call("synthetic-model", "contract", {})
                self.assertNotIn("private", str(caught.exception))
            self.assertEqual(opened.call_count, 1)
            slept.assert_not_called()

    def test_malformed_and_truncated_provider_output_never_becomes_a_verdict(self):
        payloads = [
            b"not json",
            json.dumps(
                {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
            ).encode(),
        ]
        for raw in payloads:
            model = Models()
            model.key = "synthetic-test-key"
            with (
                patch(
                    "verifai.model.paced_open",
                    side_effect=lambda *args, **kwargs: io.BytesIO(raw),
                ) as opened,
                patch("verifai.model.time.sleep"),
            ):
                with self.assertRaises(ModelError):
                    model.call("synthetic-model", "contract", {})
                self.assertLessEqual(opened.call_count, 2)

    def test_both_reviewers_unavailable_abstains_without_fabricated_quotes(self):
        models = Models()
        models.review = lambda *args, **kwargs: (_ for _ in ()).throw(
            ModelError("model-unavailable")
        )
        result = classify(models, "A is B.", "A is B.")
        self.assertEqual(result["label"], "UNVERIFIED")
        self.assertEqual(result["quotes"], [])
        self.assertEqual(result["reviews"], [])

    def test_search_and_fetch_failure_are_explicit_without_conclusive_evidence(self):
        class Extractor:
            def extract(self, text):
                return ([{"text": text, "quote": text}], [])

        def unavailable(*args):
            raise OSError("private diagnostic")

        result = Engine(Extractor(), unavailable, unavailable).verify(
            "A is B.", ["https://source.example/"]
        )
        claim = result["claims"][0]
        self.assertEqual(claim["label"], "UNVERIFIED")
        self.assertIn("Independent discovery unavailable.", claim["errors"])
        self.assertFalse(claim["tracks"]["citation"][0]["accessible"])
        self.assertNotIn("private diagnostic", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
