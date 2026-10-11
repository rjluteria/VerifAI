import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.runtime import process_metrics
from verifai.server import Service, handler


class RuntimeContract(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {}, clear=True):
            self.service = Service(object())
        self.service.origins = {"chrome-extension://synthetic"}
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.service))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def request(self, auth=True, origin="chrome-extension://synthetic"):
        headers = {"Origin": origin}
        if auth:
            headers["Authorization"] = "Bearer " + self.service.token(
                "chrome-extension://synthetic"
            )
        req = urllib.request.Request(
            "http://127.0.0.1:" + str(self.http.server_port) + "/v1/runtime",
            headers=headers,
        )
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            r = exc
        with r:
            return r.status, json.load(r), dict(r.headers)

    def test_default_disabled(self):
        self.assertEqual(self.request()[0], 404)

    def test_enabled_requires_session(self):
        self.service.runtime_diagnostics = True
        self.assertEqual(self.request(auth=False)[0], 401)

    def test_enabled_rejects_other_origin(self):
        self.service.runtime_diagnostics = True
        self.assertEqual(self.request(origin="https://untrusted.test")[0], 403)

    def test_response_minimizes_data_and_prevents_cache(self):
        self.service.runtime_diagnostics = True
        status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(
            set(body),
            {
                "scope",
                "sampled_at",
                "observation_elapsed_seconds",
                "cpu_clock_seconds",
                "current_rss_bytes",
                "peak_rss_bytes",
            },
        )
        self.assertEqual(body["scope"], "python_process_only")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("synthetic", json.dumps(body))
        self.assertNotIn(self.service.secret.decode(), json.dumps(body))

    def test_cpu_clock_is_observed_own_process(self):
        before = process_metrics()
        # Some platforms expose a coarse process CPU clock. Perform bounded
        # work until an actual tick rather than assume one small loop spans it.
        deadline = time.monotonic() + 2
        after = before
        while (
            after["cpu_clock_seconds"] == before["cpu_clock_seconds"]
            and time.monotonic() < deadline
        ):
            sum(i * i for i in range(100000))
            after = process_metrics()
        self.assertGreater(after["cpu_clock_seconds"], before["cpu_clock_seconds"])
        self.assertGreaterEqual(
            after["observation_elapsed_seconds"], before["observation_elapsed_seconds"]
        )

    def test_memory_values_are_explicitly_nullable_or_positive(self):
        result = process_metrics()
        for field in ("current_rss_bytes", "peak_rss_bytes"):
            if result[field] is not None:
                self.assertGreater(result[field], 0)
        if sys.platform.startswith("linux"):
            self.assertIsNotNone(result["current_rss_bytes"])


if __name__ == "__main__":
    unittest.main()
