import os
import re
import time
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

from .model import ModelError


def arithmetic(claim, evidence):
    # A bounded self-contained percentage expression can be checked without guessed operands.
    match = re.fullmatch(
        r"([A-Za-z][A-Za-z ]{0,60}) (increased|rose|grew) (\d+(?:\.\d+)?)%, from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)\.",
        claim,
    )
    if not match:
        return None
    metric, _, percentage, old, new = match.groups()
    before, after = Decimal(old), Decimal(new)
    if before <= 0:
        return {
            "label": "UNVERIFIED",
            "reason": "Nonpositive percentage base needs explicit interpretation.",
            "quotes": [],
        }
    actual = (after - before) / before * 100
    quantum = Decimal(1).scaleb(-len(percentage.partition(".")[2]))
    if actual.quantize(quantum, rounding=ROUND_HALF_UP) != Decimal(percentage):
        return {
            "label": "CONTRADICTED",
            "reason": "The stated operands imply "
            + str(actual)
            + "% rather than "
            + percentage
            + "%.",
            "quotes": [],
            "calculation": True,
        }
    # Ground only a complete, unqualified single-metric evidence sentence.
    grounded = re.fullmatch(
        re.escape(metric)
        + r" was (\d+(?:\.\d+)?) in (\d{4}) and (\d+(?:\.\d+)?) in (\d{4})\.",
        evidence,
        re.IGNORECASE,
    )
    if (
        grounded
        and grounded.group(1) == old
        and grounded.group(3) == new
        and int(grounded.group(2)) < int(grounded.group(4))
    ):
        return {
            "label": "SUPPORTED",
            "reason": "Explicit source operands imply "
            + str(actual)
            + "% at the stated precision.",
            "quotes": [evidence],
            "calculation": True,
        }
    # Internally consistent arithmetic alone does not ground the source values.
    return None


def classify(models, claim, evidence):
    deterministic = arithmetic(claim, evidence)
    if deterministic:
        return deterministic
    if not evidence.strip():
        return {
            "label": "UNVERIFIED",
            "reason": "No accessible relevant evidence.",
            "quotes": [],
        }
    assessments, failures = [], []
    for name in models.names:
        try:
            assessments.append({"model": name, **models.judge(name, claim, evidence)})
        except ModelError as exc:
            failures.append(str(exc))
    if len(assessments) != 2:
        return {
            "label": "UNVERIFIED",
            "reason": "Independent evidence review could not be completed.",
            "quotes": [],
            "reviews": assessments,
            "failures": failures,
        }
    labels = {row["label"] for row in assessments}
    if len(labels) != 1:
        return {
            "label": "UNVERIFIED",
            "reason": "Evidence reviewers disagree; no conclusive verdict.",
            "quotes": [],
            "reviews": assessments,
        }
    quotes = list(dict.fromkeys(q for row in assessments for q in row["quotes"]))
    return {
        "label": assessments[0]["label"],
        "reason": assessments[0]["reason"],
        "quotes": quotes,
        "reviews": assessments,
    }


def passages(text, claim, limit=6):
    terms = set(re.findall(r"[a-z0-9]+", claim.lower())) - {
        "the",
        "is",
        "of",
        "a",
        "and",
        "to",
        "in",
    }
    parts = [text[start : start + 1600] for start in range(0, len(text), 1200)]
    ranked = sorted(
        enumerate(parts),
        key=lambda row: (
            -len(terms & set(re.findall(r"[a-z0-9]+", row[1].lower()))),
            row[0],
        ),
    )[:limit]
    return [
        {"text": part, "start": i * 1200, "end": i * 1200 + len(part)}
        for i, part in sorted(ranked)
    ]


def aggregate(rows):
    labels = {row["label"] for row in rows}
    if "SUPPORTED" in labels and "CONTRADICTED" in labels:
        return "UNVERIFIED"
    if "CONTRADICTED" in labels:
        return "CONTRADICTED"
    if "SUPPORTED" in labels:
        return "SUPPORTED"
    if "PARTIALLY_SUPPORTED" in labels:
        return "PARTIALLY_SUPPORTED"
    return "UNVERIFIED"


class Engine:
    def __init__(self, models, fetcher, search):
        self.models, self.fetcher, self.search = models, fetcher, search

    def verify(self, text, citations, progress=lambda stage: None):
        deadline = time.monotonic() + 900
        citations = list(dict.fromkeys(citations))
        progress("Analyzing claims")
        claims, unsupported = self.models.extract(text)
        if len(claims) > 60:
            unsupported.append(
                "Claims beyond the first 60 were not verified in this request."
            )
            claims = claims[:60]
        documents = {}

        def source(url):
            if url not in documents:
                try:
                    documents[url] = self.fetcher(url)
                except Exception:
                    documents[url] = {
                        "url": url,
                        "accessible": False,
                        "error": "Source unavailable, restricted, or unsupported.",
                    }
            return documents[url]

        progress("Checking citations")
        for url in citations:
            source(url)
        output = []
        checked = 0
        check_budget = min(120, max(1, int(os.getenv("MAX_SOURCE_CHECKS", "60"))))
        for item in claims:
            if time.monotonic() >= deadline:
                output.append(
                    {
                        "text": item["text"],
                        "quote": item["quote"],
                        "label": "UNVERIFIED",
                        "tracks": {"citation": [], "independent": []},
                        "errors": ["Verification time budget exhausted."],
                    }
                )
                continue
            claim = item["text"]
            progress("Searching independent sources")
            errors = []
            try:
                found = self.search(claim)
            except Exception:
                found = []
                errors.append("Independent discovery unavailable.")
            urls = list(dict.fromkeys(citations + found))[:16]
            progress("Verifying evidence")
            tracks = {"citation": [], "independent": []}
            for url in urls:
                if time.monotonic() >= deadline:
                    errors.append(
                        "Evidence checks stopped at the verification time budget."
                    )
                    break
                if checked >= check_budget:
                    errors.append(
                        "Source-review budget exhausted; remaining evidence was not assessed."
                    )
                    break
                checked += 1
                doc = source(url)
                tags = (["citation"] if url in citations else []) + (
                    ["independent"] if url in found else []
                )
                if not doc["accessible"]:
                    result = {
                        "url": url,
                        "accessible": False,
                        "label": "UNVERIFIED",
                        "reason": doc["error"],
                        "snippets": [],
                    }
                else:
                    selected = self.models.rank(
                        claim, passages(doc["text"], claim, limit=20)
                    )
                    evidence = "\n\n".join(p["text"] for p in selected)
                    verdict = classify(self.models, claim, evidence)
                    snippets = []
                    for quote in verdict["quotes"]:
                        for p in selected:
                            offset = p["text"].find(quote)
                            if offset >= 0:
                                snippets.append(
                                    {
                                        "text": quote,
                                        "start": p["start"] + offset,
                                        "end": p["start"] + offset + len(quote),
                                    }
                                )
                                break
                    if len(snippets) != len(verdict["quotes"]):
                        verdict = {
                            "label": "UNVERIFIED",
                            "reason": "Quotation crossed selected evidence boundaries.",
                            "quotes": [],
                        }
                        snippets = []
                    result = {
                        "url": url,
                        "final_url": doc["url"],
                        "accessible": True,
                        "checked_at": doc["checked_at"],
                        "sha256": doc["sha256"],
                        "label": verdict["label"],
                        "reason": verdict["reason"],
                        "snippets": snippets,
                        "publisher": urlsplit(doc["url"]).hostname,
                        "scope": "Text evidence; complex tables, images and arbitrary code execution are unsupported.",
                    }
                    if verdict.get("calculation"):
                        result["calculation"] = True
                for tag in tags:
                    tracks[tag].append(result)
            combined = tracks["citation"] + tracks["independent"]
            output.append(
                {
                    "text": claim,
                    "quote": item["quote"],
                    "label": aggregate(combined),
                    "tracks": tracks,
                    "errors": errors,
                }
            )
        progress("Finalizing results")
        return {
            "claims": output,
            "unsupported": unsupported,
            "citation_access": [
                {
                    "url": url,
                    "accessible": documents[url]["accessible"],
                    "error": documents[url].get("error"),
                }
                for url in citations
            ],
            "notice": "Accessibility is checked from the service at the recorded time. Network, region, login requirements and later changes can affect your access. Supported means supplied evidence supports the claim; it is not a guarantee of truth.",
        }
