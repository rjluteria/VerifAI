import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
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


def bounded_abstention(claim, evidence):
    # Closed observational-only grammar states absence of causal proof, not
    # disproof. Additional factual sentences fall outside this guard.
    if (
        re.search(r"\b(?:caused|causes|led to|leads to)\b", claim, re.IGNORECASE)
        and re.fullmatch(
            r"(?:An|The|This) observational study (?:found|reported|observed) (?:an association|a correlation)\.\s*"
            r"It (?:cannot|can not|could not) (?:establish|prove|demonstrate) causation\.",
            evidence.strip(),
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:proved|proven|confirmed|established|demonstrated)\b",
            claim,
            re.IGNORECASE,
        )
    ):
        return {
            "label": "UNVERIFIED",
            "reason": "Observational association without causal proof does not establish or disprove the claimed effect.",
            "quotes": [],
        }
    # A matching observed increase does not establish its cause. Only a closed
    # two-sentence temporal observation qualifies; other effects, quantities,
    # compound claims and additional source assertions stay in factual review.
    causal = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9 -]{0,100}) caused increased ([A-Za-z][A-Za-z0-9 -]{0,100})\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    temporal = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9 -]{0,100}) increased after ([A-Za-z][A-Za-z0-9 -]{0,100}) (?:was installed|was introduced|began|started)\.\s*There is no causal evidence\.",
        evidence.strip(),
        re.IGNORECASE,
    )

    def subject(value):
        return re.sub(r"^(?:the|an|a) ", "", value.lower()).strip()

    if (
        causal
        and temporal
        and subject(causal[1]) == subject(temporal[2])
        and subject(causal[2]) == subject(temporal[1])
        and not re.search(
            r"\b(?:and|or|proved|proves|confirmed|confirms|established|establishes|demonstrated|demonstrates)\b",
            claim,
            re.IGNORECASE,
        )
    ):
        return {
            "label": "UNVERIFIED",
            "reason": "The matching temporal increase does not establish or disprove the asserted cause; causal evidence is explicitly absent.",
            "quotes": [],
        }
    # A non-detection above a reporting limit does not settle an unqualified
    # detection assertion. Exact subject/analyte identity and one source sentence
    # are required, so additional findings and bounded claims remain reviewed.
    detection = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9 -]{0,100}) detected ([A-Za-z][A-Za-z0-9 -]{0,80})\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if (
        detection
        and not re.search(
            r"\b(?:above|below|and|or|no|not)\b", detection[2], re.IGNORECASE
        )
        and re.fullmatch(
            re.escape(detection[1])
            + r" did not detect "
            + re.escape(detection[2])
            + r" above the (?:reporting|detection|quantification) limit\.",
            evidence.strip(),
            re.IGNORECASE,
        )
    ):
        return {
            "label": "UNVERIFIED",
            "reason": "Non-detection above the stated limit does not establish whether detection occurred below that limit.",
            "quotes": [],
        }
    # An unqualified device duration does not select battery runtime over useful
    # lifetime. Directly repeated wording or an explicit claim metric stays in review.
    duration = re.fullmatch(
        r"[A-Za-z][A-Za-z0-9 -]{0,100} lasts \d+(?:\.\d+)? (?:hours|days|months|years)\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if (
        duration
        and not re.search(r"\b(?:and|or|weighs|contains|costs)\b", claim, re.IGNORECASE)
        and re.search(r"\b(?:battery|charge|endurance)\b", evidence, re.IGNORECASE)
        and not re.search(
            r"\b(?:battery|charge|runtime|endurance|lifetime|lifespan|life)\b",
            claim,
            re.IGNORECASE,
        )
        and claim.rstrip(".").lower() not in evidence.lower()
    ):
        return {
            "label": "UNVERIFIED",
            "reason": "The claim does not identify whether duration means battery runtime or useful lifetime; the supplied battery metric cannot resolve it.",
            "quotes": [],
        }
    # A closed pair of population counts cannot resolve geographic size.
    # Explicit metrics, definitions, direct comparisons and extra facts stay in review.
    geographic = r"(?:city|town|village|country|state|province|county|island|region) [A-Za-z][A-Za-z0-9 '-]{0,70}"
    comparison = re.fullmatch(
        r"("
        + geographic
        + r") is (larger|bigger|smaller) than ("
        + geographic
        + r")\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if not comparison:
        return None
    population = r" has \d+(?:,\d{3})*(?:\.\d+)? (?:residents|inhabitants|people)"
    if not re.fullmatch(
        re.escape(comparison[1])
        + population
        + r";\s*"
        + re.escape(comparison[3])
        + population
        + r"\.?",
        evidence.strip(),
        re.IGNORECASE,
    ):
        return None
    return {
        "label": "UNVERIFIED",
        "reason": "The geographic size comparison does not specify population or area; two population counts cannot resolve the unstated metric.",
        "quotes": [],
    }


def classify(models, claim, evidence):
    deterministic = bounded_abstention(claim, evidence) or arithmetic(claim, evidence)
    if deterministic:
        return deterministic
    if not evidence.strip():
        return {
            "label": "UNVERIFIED",
            "reason": "No reviewable evidence was selected for this check.",
            "quotes": [],
        }
    assessments, failures = [], []
    for name in models.names:
        try:
            review = models.review if hasattr(models, "review") else models.judge
            assessments.append({"model": name, **review(name, claim, evidence)})
        except ModelError as exc:
            failures.append(str(exc))
    initial_reviews = []
    reconsidered = False
    if hasattr(models, "reconcile") and (
        len(assessments) != 2
        or len({row["model"] for row in assessments}) != 2
        or len({row["label"] for row in assessments}) != 1
    ):
        reconsidered = True
        initial_reviews = assessments
        assessments, retry_failures = models.reconcile(claim, evidence)
        failures.extend(retry_failures)
    recovered_initial_review = False
    if (
        reconsidered
        and len(initial_reviews) == 1
        and len(assessments) == 1
        and initial_reviews[0]["model"] != assessments[0]["model"]
        and initial_reviews[0]["label"] == assessments[0]["label"]
    ):
        # Both answers evaluated the identical immutable claim/evidence input.
        # An unavailable fresh reviewer does not invalidate its earlier validated
        # answer. Never use this path to erase any observed label disagreement,
        # combine duplicate identities, or rescue a complete disagreeing pair.
        assessments = assessments + initial_reviews
        recovered_initial_review = True
    diagnostic = (
        {
            "initial_reviews": initial_reviews,
            "review_reconsidered": True,
            "review_recovery_used_initial": recovered_initial_review,
        }
        if reconsidered
        else {}
    )
    if len(assessments) != 2 or len({row["model"] for row in assessments}) != 2:
        return {
            "label": "UNVERIFIED",
            "reason": "Independent evidence review could not be completed.",
            "quotes": [],
            "reviews": assessments,
            "failures": failures,
            **diagnostic,
        }
    labels = {row["label"] for row in assessments}
    if len(labels) != 1:
        return {
            "label": "UNVERIFIED",
            "reason": "Evidence reviewers disagree; no conclusive verdict.",
            "quotes": [],
            "reviews": assessments,
            **diagnostic,
        }
    quotes = list(dict.fromkeys(q for row in assessments for q in row["quotes"]))
    return {
        "label": assessments[0]["label"],
        "reason": assessments[0]["reason"],
        "quotes": quotes,
        "reviews": assessments,
        **(
            {
                "quote_spans": [
                    dict(text=text, start=start, end=end)
                    for text, start, end in dict.fromkeys(
                        (span["text"], span["start"], span["end"])
                        for row in assessments
                        for span in row.get("quote_spans", [])
                    )
                ]
            }
            if any("quote_spans" in row for row in assessments)
            else {}
        ),
        **diagnostic,
    }


def quoted_snippets(verdict, selected):
    snippets = []
    if "quote_spans" not in verdict:
        for quote in verdict["quotes"]:
            for passage in selected:
                offset = passage["text"].find(quote)
                if offset >= 0:
                    snippets.append(
                        {
                            "text": quote,
                            "start": passage["start"] + offset,
                            "end": passage["start"] + offset + len(quote),
                        }
                    )
                    break
            else:
                return None
        return snippets
    spans = verdict["quote_spans"]
    if {span["text"] for span in spans} != set(verdict["quotes"]):
        return None
    for span in spans:
        cursor = 0
        for passage in selected:
            offset = span["start"] - cursor
            if (
                0 <= offset
                and span["end"] <= cursor + len(passage["text"])
                and span["end"] - span["start"] == len(span["text"])
                and passage["text"][offset : offset + len(span["text"])] == span["text"]
            ):
                snippets.append(
                    {
                        "text": span["text"],
                        "start": passage["start"] + offset,
                        "end": passage["start"] + offset + len(span["text"]),
                    }
                )
                break
            cursor += len(passage["text"]) + 2
        else:
            return None
    return snippets


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
    # Short documents need no selection: preserve all qualifications and corrections.
    if len(text) <= 12000:
        return [{"text": text, "start": 0, "end": len(text)}] if text.strip() else []
    # Never cut a sentence to fit a fixed character window. A large indivisible
    # sentence is outside this bounded text review rather than incomplete proof.
    boundaries = [0] + [m.end() for m in re.finditer(r"[.!?](?:\s+|$)|\n+", text)]
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    parts = []
    start = 0
    for left, right in zip(boundaries, boundaries[1:]):
        if right - left > 8000:
            return []
        if right - start > 1600 and left > start:
            parts.append({"text": text[start:left], "start": start, "end": left})
            start = left
    if start < len(text):
        parts.append({"text": text[start:], "start": start, "end": len(text)})
    ranked = sorted(
        parts,
        key=lambda row: (
            -len(terms & set(re.findall(r"[a-z0-9]+", row["text"].lower()))),
            row["start"],
        ),
    )[:limit]
    return sorted(ranked, key=lambda row: row["start"])


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
        # Only this verification owns these query vectors; no cross-job persistence.
        query_cache = {}

        def source(url):
            if url not in documents:
                if time.monotonic() >= deadline:
                    documents[url] = {
                        "url": url,
                        "accessible": False,
                        "error": "Source check stopped at the verification time budget.",
                    }
                    return documents[url]
                try:
                    documents[url] = self.fetcher(url)
                except Exception:
                    documents[url] = {
                        "url": url,
                        "accessible": False,
                        "error": "Source unavailable, restricted, or unsupported.",
                    }
            return documents[url]

        def prefetch(urls):
            pending = [url for url in dict.fromkeys(urls) if url not in documents]
            if not pending:
                return
            # Bound source I/O without changing review order or network policy.
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(copy_context().run, source, url) for url in pending
                ]
                for future in futures:
                    future.result()

        progress("Checking citations")
        prefetch(citations)
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
            prefetch(urls[: max(0, check_budget - checked)])
            tracks = {"citation": [], "independent": []}
            content_origins = {}
            reviewed_content = {}
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
                    if doc["text"] in reviewed_content:
                        verdict, snippets = reviewed_content[doc["text"]]
                    else:
                        candidates = passages(doc["text"], claim, limit=20)
                        cached_rank = getattr(self.models, "rank_cached", None)
                        selected = (
                            cached_rank(claim, candidates, query_cache)
                            if cached_rank
                            else self.models.rank(claim, candidates)
                        )
                        evidence = "\n\n".join(p["text"] for p in selected)
                        verdict = classify(self.models, claim, evidence)
                        snippets = quoted_snippets(verdict, selected)
                        if snippets is None:
                            verdict = {
                                "label": "UNVERIFIED",
                                "reason": "Quotation crossed selected evidence boundaries.",
                                "quotes": [],
                            }
                            snippets = []
                        reviewed_content[doc["text"]] = (verdict, snippets)
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
                    original = content_origins.setdefault(doc["text"], url)
                    if original != url:
                        result["duplicate_of"] = original
                    if verdict.get("review_reconsidered"):
                        result["review_reconsidered"] = True
                    if verdict.get("reviews"):
                        result["review_models"] = [
                            r["model"] for r in verdict["reviews"]
                        ]
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
