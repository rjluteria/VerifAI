import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, urlunsplit

from .network import FetchRejected, fetch
from .precise_text import Text as PreciseText

_SEARCH_SLOTS = threading.BoundedSemaphore(2)


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if not self.hidden and tag in (
            "p",
            "br",
            "div",
            "li",
            "tr",
            "td",
            "th",
            "h1",
            "h2",
            "h3",
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.hidden:
            self.hidden -= 1
        if not self.hidden:
            self.parts.append(
                "\n" if tag in ("p", "div", "li", "tr", "h1", "h2", "h3") else " "
            )

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def allowed(url):
    origin = urlsplit(url)
    # Retest reproduced service-readable content but browser-denied Chegg access.
    # Keep its URLs visible as excluded sources; never admit them as proof.
    host = (origin.hostname or "").lower().rstrip(".")
    if host == "chegg.com" or host.endswith(".chegg.com"):
        raise FetchRejected("provider-browser-access-restricted")
    # Historical user DNS/browser failure is unresolved and browser rechecking
    # is restricted. Retain the requested destination but admit no new proof
    # until access can be independently established; alternate discovery remains.
    if host == "webel.com.au" or host.endswith(".webel.com.au"):
        raise FetchRejected("provider-browser-access-unconfirmed")
    robots_url = urlunsplit((origin.scheme, origin.netloc, "/robots.txt", "", ""))
    try:
        robots = fetch(robots_url, max_bytes=200000, deadline=10)
        rules = urllib.robotparser.RobotFileParser()
        rules.parse(robots["body"].decode("utf-8", errors="replace").splitlines())
        if not rules.can_fetch("VerifAI", url):
            raise FetchRejected("robots-disallow")
    except FetchRejected as exc:
        if str(exc) not in ("http-404", "http-410"):
            raise


def document(url):
    allowed(url)
    result = fetch(url, redirect_check=allowed)
    raw = result["body"].decode("utf-8", errors="replace")
    if result["content_type"] == "text/html":
        parser = (
            PreciseText() if os.getenv("PRECISE_SOURCE_BLOCKS", "1") == "1" else Text()
        )
        parser.feed(raw)
        text = (
            parser.rendered_text()
            if isinstance(parser, PreciseText)
            else "\n".join(
                " ".join(line.split())
                for line in "".join(parser.parts).splitlines()
                if line.strip()
            )
        )
    else:
        text = " ".join(raw.split())
    if len(text) < 80 or any(
        v in text[:2000].lower()
        for v in (
            "verify you are human",
            "access denied",
            "enable javascript and cookies",
            "checking your browser",
            "subscribe to continue",
            "sign in to read",
            "subscription required",
        )
    ):
        raise FetchRejected("blocked-or-empty-content")
    return {
        "url": result["url"],
        "text": text,
        "accessible": True,
        "checked_at": int(time.time()),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        **(
            parser.publication.result()
            if result["content_type"] == "text/html" and isinstance(parser, PreciseText)
            else {}
        ),
    }


def discovery(query):
    body = json.dumps(
        {
            "query": query,
            "max_results": 3,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    key = os.getenv("TAVILY_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    elif os.getenv("ALLOW_KEYLESS_SEARCH") == "1":
        headers["X-Tavily-Access-Mode"] = "keyless"
    else:
        raise RuntimeError("discovery-unconfigured")

    def search(search_query):
        urls = []
        payload = json.loads(body)
        payload["query"] = search_query
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            if not _SEARCH_SLOTS.acquire(timeout=20):
                return []
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    raw = response.read(500001)
            finally:
                _SEARCH_SLOTS.release()
            if len(raw) > 500000:
                raise ValueError("discovery-size")
            results = json.loads(raw).get("results", [])
            if not isinstance(results, list):
                raise ValueError("discovery-schema")
            for row in results[:3]:
                if (
                    isinstance(row, dict)
                    and isinstance(row.get("url"), str)
                    and row["url"].startswith("https://")
                    and row["url"] not in urls
                ):
                    urls.append(row["url"])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return urls

    # Preserve query/result order even when the official-source request finishes
    # first. Search snippets remain discovery hints, never admitted as evidence.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(copy_context().run, search, search_query)
            for search_query in (query, query + " official source")
        ]
        urls = list(dict.fromkeys(url for future in futures for url in future.result()))
    # The engine owns alternate discovery after checking acquired evidence.
    # Falling back here would repeat the same search if its pages are unavailable.
    return urls


def encyclopedia(query):
    url = "https://en.wikipedia.org/w/api.php?" + urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        }
    )
    req = urllib.request.Request(url, headers={"User-Agent": "VerifAI/0.1"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(500001)
    if len(raw) > 500000:
        raise RuntimeError("discovery-size")
    rows = json.loads(raw).get("query", {}).get("search", [])
    return ["https://en.wikipedia.org/?curid=" + str(row["pageid"]) for row in rows[:3]]
