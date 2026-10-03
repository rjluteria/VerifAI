"""Bounded public HTTPS retrieval with validated and pinned destinations."""

import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urljoin, urlsplit, urlunsplit


class FetchRejected(Exception):
    pass


def bounded_resolve(host, port, **kwargs):
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,socket,sys; print(json.dumps(socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)))",
                host,
            ],
            capture_output=True,
            timeout=5,
            check=True,
        )
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        raise FetchRejected("dns-timeout") from None
    except (subprocess.CalledProcessError, ValueError):
        raise FetchRejected("dns-unavailable") from None


def destination(url, resolver=bounded_resolve):
    if any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise FetchRejected("control-or-whitespace")
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username is not None
        or p.password is not None
    ):
        raise FetchRejected("scheme-or-credentials")
    if p.port not in (None, 443):
        raise FetchRejected("port")
    host = p.hostname.encode("idna").decode("ascii").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise FetchRejected("local-host")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise FetchRejected("non-global-destination")
    resolved = resolver(host, 443, type=socket.SOCK_STREAM)
    addresses = sorted({r[4][0] for r in resolved})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise FetchRejected("non-global-destination")
    return (
        host,
        addresses[0],
        urlunsplit(("https", p.netloc, p.path or "/", p.query, "")),
    )


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        sock = socket.create_connection((self.ip, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
            self.transport = self.sock
        except BaseException:
            sock.close()
            raise


def fetch(
    url,
    *,
    resolver=bounded_resolve,
    connection=PinnedHTTPS,
    max_bytes=2000000,
    redirects=3,
    timeout=10,
    deadline=30,
    redirect_check=None,
):
    started = time.monotonic()
    trace = []
    for hop in range(redirects + 1):
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise FetchRejected("total-deadline")
        host, ip, url = destination(url, resolver)
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise FetchRejected("total-deadline")
        conn = connection(host, ip, min(timeout, remaining))
        p = urlsplit(url)

        def expire(connection_=conn):
            transport = getattr(connection_, "transport", None) or getattr(
                connection_, "sock", None
            )
            if transport:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection_.close()

        watchdog = threading.Timer(remaining, expire)
        watchdog.daemon = True
        watchdog.start()
        response = None
        try:
            conn.request(
                "GET",
                urlunsplit(("", "", p.path, p.query, "")),
                headers={
                    "User-Agent": "VerifAI/0.1",
                    "Accept-Encoding": "identity",
                    "Accept": "text/html, text/plain, application/json",
                },
            )
            response = conn.getresponse()
            trace.append({"url": url, "status": response.status, "ip": ip})
            if response.status in (301, 302, 303, 307, 308):
                if hop == redirects:
                    raise FetchRejected("redirect-limit")
                location = response.getheader("Location")
                if not location:
                    raise FetchRejected("missing-location")
                url = urljoin(url, location)
                if redirect_check:
                    redirect_check(url)
                continue
            if response.status != 200:
                raise FetchRejected("http-" + str(response.status))
            mime = response.getheader("Content-Type", "").split(";")[0].lower()
            if mime not in ("text/html", "text/plain", "application/json"):
                raise FetchRejected("content-type")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise FetchRejected("encoded-response")
            length = response.getheader("Content-Length")
            try:
                expected_size = int(length) if length is not None else None
            except ValueError:
                raise FetchRejected("invalid-content-length") from None
            if expected_size is not None and expected_size < 0:
                raise FetchRejected("invalid-content-length")
            if expected_size is not None and expected_size > max_bytes:
                raise FetchRejected("response-size")
            chunks = []
            size = 0
            while True:
                remaining = deadline - (time.monotonic() - started)
                if remaining <= 0:
                    raise FetchRejected("total-deadline")
                if getattr(conn, "sock", None):
                    conn.sock.settimeout(min(timeout, remaining))
                block = response.read1(min(16384, max_bytes - size + 1))
                if not block:
                    break
                chunks.append(block)
                size += len(block)
                if size > max_bytes:
                    raise FetchRejected("response-size")
            if expected_size is not None and size != expected_size:
                raise FetchRejected("incomplete-response")
            return {
                "url": url,
                "body": b"".join(chunks),
                "content_type": mime,
                "trace": trace,
            }
        finally:
            watchdog.cancel()
            if response is not None:
                response.close()
            conn.close()
    raise FetchRejected("redirect-limit")
