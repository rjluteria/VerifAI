import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, urlunsplit

from .network import FetchRejected, fetch


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
        parser = Text()
        parser.feed(raw)
        text = "\n".join(
            " ".join(line.split())
            for line in "".join(parser.parts).splitlines()
            if line.strip()
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
    urls = []
    for search_query in (query, query + " official source"):
        payload = json.loads(body)
        payload["query"] = search_query
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read(500001)
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
            continue
    return urls or encyclopedia(query)


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
