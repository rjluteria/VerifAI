import io
import json
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
from verifai.engine import Engine, aggregate, arithmetic, classify
from verifai.model import ModelError, Models, retry_delay
from verifai.network import FetchRejected, destination
from verifai.server import Service, handler, strict_json, valid_request
from verifai.sources import Text


class Reviewers:
    names = ["primary", "secondary"]

    def __init__(self, labels=None):
        self.labels = labels or ["SUPPORTED", "SUPPORTED"]

    def judge(self, name, claim, evidence):
        return {
            "label": self.labels[self.names.index(name)],
            "reason": "review",
            "quotes": [evidence],
        }

    def extract(self, text):
        return ([{"text": text, "quote": text}], [])

    def rank(self, claim, selected):
        return selected[:6]


class EngineTests(unittest.TestCase):
    def test_disagreement_abstains(self):
        self.assertEqual(
            classify(Reviewers(["SUPPORTED", "CONTRADICTED"]), "A is B.", "A is B.")[
                "label"
            ],
            "UNVERIFIED",
        )

    def test_unavailable_reviewer_abstains(self):
        models = Reviewers()
        models.judge = lambda *args: (_ for _ in ()).throw(ModelError("unavailable"))
        self.assertEqual(classify(models, "A is B.", "A is B.")["label"], "UNVERIFIED")

    def test_invalid_math(self):
        for claim in [
            "Profit increased 10%, from 80 to 100.",
            "Sales increased 15%, from 200 to 250.",
            "Revenue rose 50%, from 100 to 120.",
        ]:
            self.assertEqual(arithmetic(claim, "")["label"], "CONTRADICTED")

    def test_consistent_math_needs_evidence(self):
        self.assertIsNone(arithmetic("Revenue rose 20%, from 100 to 120.", ""))
        self.assertEqual(
            classify(Reviewers(), "Revenue rose 20%, from 100 to 120.", "")["label"],
            "UNVERIFIED",
        )

    def test_ambiguous_math_not_inferred(self):
        self.assertIsNone(arithmetic("Revenue increased 20% last year.", ""))

    def test_grounded_math_and_mismatched_entity(self):
        claim = "Revenue increased 25%, from 40 to 50."
        self.assertEqual(
            arithmetic(claim, "Revenue was 40 in 2024 and 50 in 2025.")["label"],
            "SUPPORTED",
        )
        for evidence in [
            "Profit was 40 in 2024 and 50 in 2025.",
            "Revenue was 40 in 2025 and 50 in 2024.",
            "Revenue was 40 in 2024 and 50 in 2025. Values are estimates.",
            "Revenue was 40 in 2024 and 55 in 2025.",
        ]:
            self.assertIsNone(arithmetic(claim, evidence))

    def test_conflicting_sources(self):
        self.assertEqual(
            aggregate([{"label": "SUPPORTED"}, {"label": "CONTRADICTED"}]), "UNVERIFIED"
        )

    def test_exact_quotes_enforced(self):
        model = Models()
        model.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "yes",
            "quotes": ["invented"],
        }
        with self.assertRaises(ModelError):
            model.judge("test", "a", "b")

    def test_no_quote_support_rejected(self):
        model = Models()
        model.call = lambda *args: {"label": "SUPPORTED", "reason": "yes", "quotes": []}
        with self.assertRaises(ModelError):
            model.judge("test", "a", "b")

    def test_invalid_label_type_rejected(self):
        model = Models()
        model.call = lambda *args: {"label": [], "reason": "bad", "quotes": []}
        with self.assertRaises(ModelError):
            model.judge("test", "a", "b")

    def test_model_specific_provider_contract(self):
        model = Models()
        model.key = "test-only"
        for name in ["z-ai/glm-5.3-flash", "openai/gpt-oss-20b"]:
            response = io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": "{}"}}
                        ]
                    }
                ).encode()
            )
            with patch(
                "verifai.model.urllib.request.urlopen", return_value=response
            ) as call:
                self.assertEqual(model.call(name, "instruction", {}), {})
            request = call.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(
                request.full_url, "https://integrate.api.nvidia.com/v1/chat/completions"
            )
            if name == "z-ai/glm-5.3-flash":
                self.assertEqual(payload["reasoning_effort"], "low")
                self.assertEqual(
                    payload["chat_template_kwargs"], {"clear_thinking": True}
                )
            else:
                self.assertNotIn("reasoning_effort", payload)
                self.assertNotIn("chat_template_kwargs", payload)

    def test_retry_after(self):
        self.assertEqual(retry_delay("15"), 15)
        self.assertEqual(retry_delay("invalid"), 1)
        with patch("verifai.model.time.time", return_value=0):
            self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:00:10 GMT"), 10)

    def test_both_tracks_and_accessibility(self):
        def get(url):
            if url.endswith("missing"):
                raise FetchRejected("404")
            return {
                "url": url,
                "accessible": True,
                "text": "A is B.",
                "checked_at": 1,
                "sha256": "hash",
            }

        engine = Engine(Reviewers(), get, lambda claim: ["https://example.org/source"])
        result = engine.verify(
            "A is B.", ["https://example.org/source", "https://example.org/missing"]
        )
        self.assertEqual(result["claims"][0]["label"], "SUPPORTED")
        self.assertEqual(len(result["claims"][0]["tracks"]["citation"]), 2)
        self.assertEqual(len(result["claims"][0]["tracks"]["independent"]), 1)
        self.assertFalse(result["citation_access"][1]["accessible"])
        self.assertEqual(
            result["claims"][0]["tracks"]["citation"][0]["snippets"][0]["text"],
            "A is B.",
        )

    def test_all_sources_fail(self):
        engine = Engine(
            Reviewers(), lambda u: (_ for _ in ()).throw(FetchRejected()), lambda c: []
        )
        result = engine.verify("A is B.", ["https://example.org/source"])
        self.assertEqual(result["claims"][0]["label"], "UNVERIFIED")

    def test_search_outage_preserves_citations(self):
        doc = {
            "url": "https://example.org/a",
            "accessible": True,
            "text": "A is B.",
            "checked_at": 1,
            "sha256": "x",
        }
        engine = Engine(
            Reviewers(), lambda u: doc, lambda c: (_ for _ in ()).throw(OSError())
        )
        result = engine.verify("A is B.", [doc["url"]])
        self.assertEqual(result["claims"][0]["label"], "SUPPORTED")
        self.assertTrue(result["claims"][0]["errors"])

    def test_hidden_html(self):
        parser = Text()
        parser.feed(
            "<p>A &amp; B</p><script>secret</script><style>hidden</style><p>C</p>"
        )
        self.assertEqual(" ".join("".join(parser.parts).split()), "A & B C")


class SecurityTests(unittest.TestCase):
    def resolver(self, host, port, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def test_url_attacks(self):
        for url in [
            "http://example.org",
            "https://localhost/",
            "https://127.0.0.1/",
            "https://169.254.169.254/",
            "https://[::1]/",
            "https://u:p@example.org/",
            "https://example.org:444/",
            "https://example.org/\nsecret",
        ]:
            with self.subTest(url=url), self.assertRaises((FetchRejected, ValueError)):
                destination(url, self.resolver)

    def test_mixed_dns(self):
        with self.assertRaises(FetchRejected):
            destination(
                "https://example.org",
                lambda *a, **k: (
                    self.resolver(*a, **k) + [(2, 1, 6, "", ("10.0.0.1", 443))]
                ),
            )

    def test_pinned_public_destination(self):
        self.assertEqual(
            destination("https://example.org/a#fragment", self.resolver),
            ("example.org", "93.184.216.34", "https://example.org/a"),
        )

    def test_dns_deadline(self):
        import subprocess

        from verifai.network import bounded_resolve

        with patch(
            "verifai.network.subprocess.run",
            side_effect=subprocess.TimeoutExpired("dns", 5),
        ):
            with self.assertRaises(FetchRejected):
                bounded_resolve("example.org", 443)

    def test_session_tamper_expiry_and_origin(self):
        service = Service(None)
        token = service.token("origin")
        self.assertTrue(service.identity(token, "origin"))
        with self.assertRaises(ValueError):
            service.identity(token + "x", "origin")
        with self.assertRaises(ValueError):
            service.identity(token, "other")
        with patch("verifai.server.time.time", return_value=time.time() + 1000):
            with self.assertRaises(ValueError):
                service.identity(token, "origin")

    def test_concurrent_limits(self):
        service = Service(None)
        values = []
        workers = [
            threading.Thread(target=lambda: values.append(service.limit("test", 5)))
            for _ in range(20)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sum(values), 5)

    def test_schema(self):
        self.assertTrue(valid_request({"text": "claim", "citations": []}))
        for data in [
            {"text": "claim", "citations": [], "extra": True},
            {"text": "", "citations": []},
            {"text": "x", "citations": ["http://example.org"]},
            {"text": "x" * 60001, "citations": []},
        ]:
            self.assertFalse(valid_request(data))

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            strict_json('{"text":"first","text":"second","citations":[]}')

    def test_cleanup(self):
        service = Service(None)
        service.jobs["old"] = {"expires": 0}
        service.clean()
        self.assertEqual(service.jobs, {})


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.service = Service(Engine(Reviewers(), lambda url: {}, lambda c: []))
        self.service.origins = {"chrome-extension://test"}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None, token=None, origin="chrome-extension://test"):
        headers = {"Origin": origin, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            self.url + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_session_job_flow_and_ownership(self):
        code, session = self.request("/v1/session", {})
        self.assertEqual(code, 200)
        code, job = self.request(
            "/v1/verify", {"text": "A is B.", "citations": []}, session["token"]
        )
        self.assertEqual(code, 202)
        for _ in range(50):
            code, result = self.request(
                "/v1/jobs/" + job["job"], token=session["token"]
            )
            if result["stage"] == "Complete":
                break
            time.sleep(0.01)
        self.assertEqual(result["result"]["claims"][0]["label"], "UNVERIFIED")
        other = self.service.token("chrome-extension://test")
        self.assertEqual(self.request("/v1/jobs/" + job["job"], token=other)[0], 404)

    def test_origin_and_auth(self):
        self.assertEqual(
            self.request("/v1/session", {}, origin="https://evil.example")[0], 403
        )
        self.assertEqual(
            self.request("/v1/verify", {"text": "x", "citations": []})[0], 401
        )

    def test_session_refresh_preserves_owner(self):
        old = self.service.token("chrome-extension://test")
        _, new = self.request("/v1/session", {}, old)
        self.assertEqual(
            self.service.identity(old, "chrome-extension://test"),
            self.service.identity(new["token"], "chrome-extension://test"),
        )

    def test_extension_declared_origin_requires_matching_session(self):
        token = self.service.token("chrome-extension://test")

        def request(origin=None):
            headers = {
                "X-VerifAI-Origin": "chrome-extension://test",
                "Authorization": "Bearer " + token,
            }
            if origin:
                headers["Origin"] = origin
            req = urllib.request.Request(self.url + "/v1/jobs/missing", headers=headers)
            try:
                with urllib.request.urlopen(req) as response:
                    return response.status
            except urllib.error.HTTPError as exc:
                with exc:
                    return exc.code

        self.assertEqual(request(), 404)
        self.assertEqual(request("https://evil.example"), 403)
        self.assertEqual(request("chrome-extension://test"), 404)

    def test_malformed_payload(self):
        token = self.service.token("chrome-extension://test")
        self.assertEqual(
            self.request(
                "/v1/verify", {"text": "x", "citations": [], "extra": 1}, token
            )[0],
            400,
        )


if __name__ == "__main__":
    unittest.main()
