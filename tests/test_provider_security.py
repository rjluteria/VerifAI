import io
import json
import os
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

    def test_fixed_reviewers_and_server_only_credential(self):
        with patch.dict(
            os.environ, {"NVIDIA_API_KEY": "synthetic-server-only"}, clear=True
        ):
            model = Models()
        self.assertEqual(
            model.names, ["nvidia/nemotron-3-super-120b-a12b", "poolside/laguna-xs-2.1"]
        )
        self.assertEqual(model.standby, "openai/gpt-oss-20b")
        response = {
            "model": model.names[0],
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        }
        with patch(
            "verifai.model.paced_open",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ) as opened:
            self.assertEqual(
                model.call(model.names[0], "Code-owned rules", {"claim": "synthetic"}),
                {},
            )
        request = opened.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        self.assertEqual(opened.call_args.kwargs["timeout"], 60)
        self.assertEqual(
            request.headers["Authorization"], "Bearer synthetic-server-only"
        )
        self.assertNotIn(b"synthetic-server-only", request.data)
