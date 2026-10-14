import unittest

from verifai.progress import JobProgress


class ProgressTests(unittest.TestCase):
    def test_terminal_state_cannot_be_overwritten(self):
        status = JobProgress("opaque")
        status.update({"claim_count": 2})
        status.update("Checking citations")
        status.update("Searching independent sources")
        before = status.snapshot()
        self.assertEqual(before["stages"]["citations"], "active")
        self.assertEqual(before["stages"]["independent"], "active")
        status.update("Complete")
        terminal = status.snapshot()
        status.update("Analyzing claims")
        self.assertEqual(status.snapshot()["sequence"], terminal["sequence"])
        self.assertEqual(status.snapshot()["outcome"], "complete")
        self.assertEqual(before["outcome"], "pending")

    def test_failure_never_claims_stages_completed(self):
        status = JobProgress("opaque")
        status.update("Failed")
        self.assertEqual(set(status.snapshot()["stages"].values()), {"unavailable"})

    def test_untrusted_counts_rejected(self):
        status = JobProgress("opaque")
        for count in (True, -1, 61, "2"):
            status.update({"claim_count": count})
        self.assertNotIn("claim_count", status.snapshot())


class IdempotentJobTests(unittest.TestCase):
    def test_lost_submission_reply_reuses_only_same_owner_and_input(self):
        import threading

        from verifai.server import Service

        release = threading.Event()

        class Pending:
            def verify(self, text, citations, progress):
                release.wait(2)
                return {"claims": [], "unsupported": []}

        service = Service(Pending())
        payload = {
            "text": "Synthetic fact.",
            "citations": [],
            "response_id": "opaque-run",
        }
        try:
            first = service.start("owner", payload)
            self.assertEqual(service.start("owner", payload), first)
            self.assertEqual(len(service.jobs), 1)
            with self.assertRaises(ValueError):
                service.start("owner", {**payload, "text": "Different synthetic fact."})
            other = service.start("other-owner", payload)
            self.assertNotEqual(first, other)
            self.assertNotIn("request_digest", service.read_job("owner", first))
            self.assertIsNone(service.read_job("other-owner", first))
        finally:
            release.set()
