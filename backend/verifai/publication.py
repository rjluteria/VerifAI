"""Bounded source-declared dates; no inferred timezone or factual authority."""

import json
import re
from datetime import date, datetime


def publication_value(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"[1-9]\d{3}", value):
            return value
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return value
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?"
            r"(?:Z|[+-]\d{2}:?\d{2})?",
            value,
        ):
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
    except ValueError:
        pass
    return None


class Publication:
    def __init__(self):
        self.values = set()

    def add(self, value):
        parsed = publication_value(value)
        if parsed:
            self.values.add(parsed)

    def jsonld(self, raw):
        if len(raw) > 65536:
            return
        try:
            root = json.loads(raw)
        except (ValueError, RecursionError):
            return
        pending = [root]
        for _ in range(1000):
            if not pending:
                break
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node[:100])
            elif isinstance(node, dict):
                types = node.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if isinstance(types, list) and any(
                    value
                    in {
                        "Article",
                        "NewsArticle",
                        "BlogPosting",
                        "ScholarlyArticle",
                        "WebPage",
                    }
                    for value in types
                    if isinstance(value, str)
                ):
                    self.add(node.get("datePublished"))
                # Do not import dates from cited papers, authors, ads or offers.
                pending.extend(
                    node[key] for key in ("@graph", "mainEntity") if key in node
                )

    def result(self):
        if len(self.values) == 1:
            return {
                "publication_time": next(iter(self.values)),
                "publication_status": "source-declared; not independently established",
            }
        return {
            "publication_time": None,
            "publication_status": "conflicting source-declared dates"
            if self.values
            else "not available in supported publication metadata",
        }
