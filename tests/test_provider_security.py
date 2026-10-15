import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.model import Models, paced_open


class ProviderSecurityTests(unittest.TestCase):
    def test_provider_redirect_never_forwards_credential_or_evidence(self):
        requests = []

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/unexpected-endpoint")
                self.end_headers()

            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/provider",
                data=b"synthetic evidence",
                headers={"Authorization": "Bearer test-only"},
            )
            with self.assertRaises(urllib.error.HTTPError) as error:
                paced_open(request, timeout=2)
            self.assertEqual(error.exception.code, 302)
            error.exception.close()
            self.assertEqual(requests, ["/provider"])
        finally:
            server.shutdown()
            thread.join(2)
            server.server_close()

    def test_unexpected_provider_identity_and_top_level_schema_fail_closed(self):
        for payload in [
            [],
            {
                "model": "other/unrequested-model",
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            },
        ]:
            with (
                self.subTest(payload=payload),
                patch(
                    "verifai.model.paced_open",
                    return_value=io.BytesIO(json.dumps(payload).encode()),
                ),
            ):
                model = Models()
                model.key = "test-only"
                with self.assertRaises(Exception) as error:
                    model.call(model.names[0], "Code-owned rules", {})
                self.assertIn(
                    str(error.exception),
                    ("model-response-schema", "model-response-identity"),
                )
