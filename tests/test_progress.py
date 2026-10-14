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
