import io
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.network import FetchRejected, fetch
from verifai.sources import document


def resolver(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class Response:
    def __init__(self, status=200, body=b"source text", headers=None):
        self.status = status
        self.body = io.BytesIO(body)
        self.headers = headers or {"Content-Type": "text/plain"}

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read1(self, limit):
        return self.body.read(limit)

    def close(self):
        self.body.close()


def connection(responses, seen):
    class Connection:
        sock = None

        def __init__(self, host, ip, timeout):
            seen.append((host, ip, timeout))

        def request(self, *args, **kwargs):
            seen.append(kwargs["headers"])

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            pass

    return Connection


class NetworkTests(unittest.TestCase):
    def test_public_fetch_has_no_cookies_or_credentials(self):
        seen = []
        result = fetch(
            "https://example.org/a",
            resolver=resolver,
            connection=connection([Response()], seen),
        )
        self.assertEqual(result["body"], b"source text")
        self.assertNotIn("Authorization", seen[1])
        self.assertNotIn("Cookie", seen[1])
        self.assertEqual(seen[0][1], "93.184.216.34")

    def test_redirect_rebinding_rejected_before_second_connection(self):
        seen = []

        def changing(host, port, **kwargs):
            return (
                resolver(host, port, **kwargs)
                if host == "example.org"
                else [(2, 1, 6, "", ("10.0.0.1", 443))]
            )

        with self.assertRaises(FetchRejected):
            fetch(
                "https://example.org/a",
                resolver=changing,
                connection=connection(
                    [Response(302, headers={"Location": "https://other.example/b"})],
                    seen,
                ),
            )
        self.assertEqual(len(seen), 2)

    def test_redirect_policy_checked_before_next_get(self):
        seen = []

        def reject(url):
            raise FetchRejected("robots-disallow")

        with self.assertRaises(FetchRejected):
            fetch(
                "https://example.org/a",
                resolver=resolver,
                redirect_check=reject,
                connection=connection(
                    [Response(302, headers={"Location": "/restricted"})], seen
                ),
            )
        self.assertEqual(len(seen), 2)

    def test_mime_encoding_body_and_redirect_limits(self):
        fixtures = [
            Response(headers={"Content-Type": "application/pdf"}),
            Response(
                headers={"Content-Type": "text/plain", "Content-Encoding": "gzip"}
            ),
            Response(body=b"x" * 20),
            Response(302, headers={"Location": "/a"}),
        ]
        for response in fixtures:
            with self.assertRaises(FetchRejected):
                fetch(
                    "https://example.org/a",
                    resolver=resolver,
                    connection=connection([response], []),
                    max_bytes=10,
                    redirects=0,
                )

    def test_watchdog_interrupts_slow_headers(self):
        stopped = threading.Event()

        class Slow:
            sock = None

            def __init__(self, *args):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                if stopped.wait(1):
                    raise TimeoutError("closed by watchdog")
                raise AssertionError("watchdog failed")

            def close(self):
                stopped.set()

        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            fetch(
                "https://example.org", resolver=resolver, connection=Slow, deadline=0.05
            )
        self.assertLess(time.monotonic() - start, 0.5)

    def test_robots_blocks_retrieval(self):
        with patch(
            "verifai.sources.fetch",
            return_value={"body": b"User-agent: *\nDisallow: /\n"},
        ) as mocked:
            with self.assertRaises(FetchRejected):
                document("https://example.org/restricted")
            self.assertEqual(mocked.call_count, 1)

    def test_login_wall_not_supporting_evidence(self):
        def response(url, **kwargs):
            if url.endswith("/robots.txt"):
                raise FetchRejected("http-404")
            return {
                "body": b"<p>Sign in to read " + b"x" * 100 + b"</p>",
                "url": url,
                "content_type": "text/html",
            }

        with patch("verifai.sources.fetch", side_effect=response):
            with self.assertRaises(FetchRejected):
                document("https://example.org/login")


if __name__ == "__main__":
    unittest.main()
