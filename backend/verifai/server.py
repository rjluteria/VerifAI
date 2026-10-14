import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .engine import Engine
from .model import Models
from .progress import JobProgress
from .runtime import process_metrics
from .sources import discovery, document, encyclopedia
from .trace import Trace, measured, trace_scope


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.capacity = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.capacity.release()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate-json-key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


class Service:
    def __init__(self, engine):
        self.engine = engine
        self.runtime_diagnostics = os.getenv("ENABLE_RUNTIME_DIAGNOSTICS") == "1"
        self.causal_diagnostics = os.getenv("ENABLE_CAUSAL_DIAGNOSTICS") == "1"
        self.secret = os.getenv("SESSION_SECRET", secrets.token_hex(32)).encode()
        self.origins = set(filter(None, os.getenv("ALLOWED_ORIGINS", "").split(",")))
        self.lock = threading.RLock()
        self.jobs, self.requests = {}, defaultdict(deque)
        self.completed = threading.Condition(self.lock)
        self.waiters = threading.BoundedSemaphore(8)
        self.running = threading.BoundedSemaphore(2)

    def token(self, origin, owner=None):
        data = json.dumps(
            {
                "id": owner or secrets.token_hex(16),
                "exp": int(time.time()) + 900,
                "origin": origin,
            }
        ).encode()
        encoded = base64.urlsafe_b64encode(data).decode()
        return (
            encoded
            + "."
            + hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        )

    def identity(self, token, origin):
        try:
            encoded, signature = token.split(".")
            expected = hmac.new(
                self.secret, encoded.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            payload = json.loads(base64.urlsafe_b64decode(encoded))
            if payload["origin"] != origin or payload["exp"] <= time.time():
                raise ValueError()
            return payload["id"]
        except Exception:
            raise ValueError("session-invalid") from None

    def limit(self, key, maximum):
        with self.lock:
            now = time.time()
            for old in list(self.requests):
                while self.requests[old] and self.requests[old][0] < now - 60:
                    self.requests[old].popleft()
                if not self.requests[old]:
                    del self.requests[old]
            bucket = self.requests[key]
            if len(bucket) >= maximum or len(self.requests) > 10000:
                return False
            bucket.append(now)
            return True

    def clean(self):
        with self.lock:
            now = time.time()
            for key in list(self.jobs):
                if self.jobs[key]["expires"] < now:
                    del self.jobs[key]

    def read_job(self, owner, key, wait=False):
        # Reserve only a bounded subset of HTTP threads for completion waits.
        # Ownership is checked before waiting and again before returning data.
        held = False
        try:
            with self.completed:
                job = self.jobs.get(key)
                if job is None or job["owner"] != owner:
                    return None
                if wait and job["stage"] not in ("Complete", "Failed"):
                    held = self.waiters.acquire(blocking=False)
                    if held:
                        self.completed.wait_for(
                            lambda: (
                                key not in self.jobs
                                or self.jobs[key]["owner"] != owner
                                or self.jobs[key]["stage"] in ("Complete", "Failed")
                            ),
                            timeout=5,
                        )
                job = self.jobs.get(key)
                if job is None or job["owner"] != owner:
                    return None
                return {k: v for k, v in job.items() if k not in ("owner", "expires")}
        finally:
            if held:
                self.waiters.release()

    def start(self, owner, payload):
        if not self.running.acquire(blocking=False):
            return None
        key = secrets.token_urlsafe(24)
        status = JobProgress(key, payload.get("response_id"))
        with self.lock:
            self.jobs[key] = {
                "owner": owner,
                "stage": "Analyzing claims",
                "progress": status.snapshot(),
                "expires": time.time() + 1800,
            }

        def work():
            def progress(stage):
                with self.lock:
                    if key in self.jobs:
                        status.update(stage)
                        self.jobs[key]["progress"] = status.snapshot()
                        if isinstance(stage, str):
                            self.jobs[key]["stage"] = stage

            tracer = Trace(key) if self.causal_diagnostics else None
            try:
                with trace_scope(tracer), measured("job"):
                    result = self.engine.verify(
                        payload["text"], payload["citations"], progress
                    )
                with self.lock:
                    if key in self.jobs:
                        status.update("Complete")
                        self.jobs[key]["progress"] = status.snapshot()
                        self.jobs[key].update(stage="Complete", result=result)
                        if tracer:
                            self.jobs[key]["trace"] = tracer.snapshot()
                        self.completed.notify_all()
            except Exception:
                with self.lock:
                    if key in self.jobs:
                        status.update("Failed")
                        self.jobs[key]["progress"] = status.snapshot()
                        self.jobs[key].update(
                            stage="Failed",
                            error="Verification unavailable; retry later.",
                        )
                        if tracer:
                            self.jobs[key]["trace"] = tracer.snapshot()
                        self.completed.notify_all()
            finally:
                self.running.release()

        threading.Thread(target=work, daemon=True).start()
        return key


def valid_request(data):
    if (
        not isinstance(data, dict)
        or set(data)
        not in ({"text", "citations"}, {"text", "citations", "response_id"})
        or (
            "response_id" in data
            and (
                not isinstance(data["response_id"], str)
                or not 1 <= len(data["response_id"]) <= 80
                or any(
                    c
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                    for c in data["response_id"]
                )
            )
        )
        or not isinstance(data["text"], str)
        or not 0 < len(data["text"]) <= 60000
        or not isinstance(data["citations"], list)
        or len(data["citations"]) > 12
        or any(not isinstance(v, str) or len(v) > 2048 for v in data["citations"])
    ):
        return False
    for url in data["citations"]:
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (443, None)
            ):
                return False
        except ValueError:
            return False
    return True


def handler(service):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def reply(self, code, data):
            raw = json.dumps(data).encode()
            self.send_response(code)
            origin = self.headers.get("Origin", "")
            if origin in service.origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            if code == 429:
                self.send_header("Retry-After", "60")
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self):
            if self.headers.get("Origin") not in service.origins:
                return self.reply(403, {"error": "origin"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, X-VerifAI-Origin",
            )
            self.end_headers()

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"status": "ok"})
            self.route(False)

        def do_POST(self):
            self.route(True)

        def route(self, post):
            service.clean()
            browser_origin = self.headers.get("Origin", "")
            declared_origin = self.headers.get("X-VerifAI-Origin", "")
            origin = browser_origin or declared_origin
            if origin not in service.origins or (
                browser_origin and declared_origin and browser_origin != declared_origin
            ):
                return self.reply(403, {"error": "origin"})
            # Proxy headers are intentionally not trusted on an unconfigured network.
            ip = self.client_address[0]
            if not service.limit("ip:" + ip, 120) or not service.limit("global", 500):
                return self.reply(429, {"error": "rate-limit"})
            if post and self.path == "/v1/session":
                if not service.limit("session:" + ip, 10):
                    return self.reply(429, {"error": "rate-limit"})
                owner = None
                try:
                    auth = self.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        owner = service.identity(auth[7:], origin)
                except ValueError:
                    pass
                return self.reply(
                    200,
                    {
                        "token": service.token(origin, owner),
                        "expires_in": 900,
                        "completion_wait": 5,
                        "progress_version": 1,
                    },
                )
            try:
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    raise ValueError()
                owner = service.identity(auth[7:], origin)
            except ValueError:
                return self.reply(401, {"error": "session"})
            if not post and self.path == "/v1/runtime":
                if not service.runtime_diagnostics:
                    return self.reply(404, {"error": "route"})
                return self.reply(200, process_metrics())
            if not post and self.path.startswith("/v1/jobs/"):
                path, separator, query = self.path.partition("?")
                if separator and query != "wait=5":
                    return self.reply(400, {"error": "query"})
                key = path.removeprefix("/v1/jobs/")
                job = service.read_job(owner, key, wait=bool(separator))
                if job is None:
                    return self.reply(404, {"error": "job"})
                return self.reply(200, job)
            if not post or self.path != "/v1/verify":
                return self.reply(404, {"error": "route"})
            if not service.limit("verify:" + owner, 5):
                return self.reply(429, {"error": "rate-limit"})
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError()
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    not 0 < length <= 100000
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    raise ValueError()
                payload = strict_json(self.rfile.read(length))
                if not valid_request(payload):
                    raise ValueError()
            except (ValueError, OSError):
                return self.reply(400, {"error": "payload"})
            key = service.start(owner, payload)
            if key is None:
                return self.reply(429, {"error": "busy"})
            return self.reply(202, {"job": key})

    return Handler


def main():
    service = Service(Engine(Models(), document, discovery, encyclopedia))
    if (
        not service.origins
        or not os.getenv("SESSION_SECRET")
        or len(os.getenv("SESSION_SECRET", "")) < 32
    ):
        raise SystemExit(
            "Configure ALLOWED_ORIGINS and a SESSION_SECRET of at least 32 characters."
        )
    server = BoundedServer(
        ("0.0.0.0", int(os.getenv("PORT", "8000"))), handler(service)
    )

    def clean():
        while True:
            time.sleep(60)
            service.clean()

    threading.Thread(target=clean, daemon=True).start()
    print(
        "Verification service listening; content and credentials are not logged.",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
