import copy
import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

from .model import decomposition_scope, review_pair
from .trace import measured
from .unit_aliases import conflicting_mass_aliases, is_mass_conversion
from .unit_math import plan_conversion

# Final reasons describe the validated category only. Free-form reviewer prose
# can introduce measurements or facts absent from the admitted quotations.
# Keep that prose in raw review diagnostics rather than presenting it as proof.
EVIDENCE_REASONS = {
    "SUPPORTED": "The quoted source text supports this claim.",
    "CONTRADICTED": "The quoted source text contradicts this claim.",
    "PARTIALLY_SUPPORTED": "The quoted source text supports only part of this claim.",
    "UNVERIFIED": "The source evidence is insufficient to verify this claim.",
}


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


def partition_count(claim, evidence):
    # Closed, internally consistent age-count partitions establish their subgroup
    # counts. Do not compare an adult/juvenile count with the aggregate total.
    # Qualifiers, mismatched subjects and additional findings stay in model review.
    match = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9 -]{0,100}) counted ([0-9]{1,9}) (adult|juvenile) ([A-Za-z]{1,40})\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if not match or re.search(
        r"\b(?:and|or|not|never|no|only|about|approximately)\b", claim, re.IGNORECASE
    ):
        return None
    subject, claimed, category, noun = match.groups()
    source = re.fullmatch(
        re.escape(subject)
        + r" counted ([0-9]{1,9}) "
        + re.escape(noun)
        + r": ([0-9]{1,9}) adults and ([0-9]{1,9}) juveniles\.?",
        evidence.strip(),
        re.IGNORECASE,
    )
    if not source:
        return None
    total, adults, juveniles = map(int, source.groups())
    if total != adults + juveniles:
        return None
    observed = adults if category.lower() == "adult" else juveniles
    return {
        "label": "SUPPORTED" if int(claimed) == observed else "CONTRADICTED",
        "reason": f"The explicit partition counts {observed} {category.lower()} {noun}, rather than using the aggregate count of {total}.",
        "quotes": [evidence.strip()],
        "calculation": True,
    }


def bounded_abstention(claim, evidence):
    # A closed pair of explicitly equally credible, unresolved measurements
    # cannot establish either reported point. Preserve identity and units; do
    # not suppress corrections, additional findings or independently contradicted
    # values outside the reported pair.
    measurement = re.fullmatch(
        r"The ([A-Za-z][A-Za-z0-9 -]{0,100}) is (\d+(?:\.\d+)?) "
        r"(metres|meters|centimetres|centimeters|kilometres|kilometers|feet|inches) "
        r"(?:tall|long|wide|high|deep)\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if measurement and not re.search(
        r"\b(?:and|or|not|only|about|approximately)\b", claim, re.IGNORECASE
    ):
        unresolved = re.fullmatch(
            r"Two equally credible measurements report (\d+(?:\.\d+)?) "
            + re.escape(measurement[3])
            + r" and (\d+(?:\.\d+)?) "
            + re.escape(measurement[3])
            + r" for the same "
            + re.escape(measurement[1])
            + r"\.\s*No explanation resolves the discrepancy\.",
            evidence.strip(),
            re.IGNORECASE,
        )
        if unresolved:
            first, second = map(Decimal, unresolved.groups())
            if first != second and Decimal(measurement[2]) in {first, second}:
                return {
                    "label": "UNVERIFIED",
                    "reason": "The equally credible measurements disagree on the claimed point and explicitly leave the discrepancy unresolved.",
                    "quotes": [],
                }
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
    # Possibility plus explicit absence of testing establishes neither presence
    # nor absence. Require matching subject/analyte and the entire closed source;
    # direct findings, extra facts and compound claims remain in model review.
    absence = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9 -]{0,100}) contains no ([A-Za-z][A-Za-z0-9 -]{0,80})\.?",
        claim.strip(),
        re.IGNORECASE,
    )
    if (
        absence
        and not re.search(r"\b(?:and|or|no|not)\b", absence[2], re.IGNORECASE)
        and re.fullmatch(
            re.escape(absence[1])
            + r" may contain traces of "
            + re.escape(absence[2])
            + r"; testing for [A-Za-z][A-Za-z0-9 -]{0,80} contamination was not performed\.",
            evidence.strip(),
            re.IGNORECASE,
        )
    ):
        return {
            "label": "UNVERIFIED",
            "reason": "Possible traces with no contamination testing do not establish either presence or absence of the claimed substance.",
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


@decomposition_scope()
def classify(models, claim, evidence, _unit_math=True, reference_cache=None):
    deterministic = (
        bounded_abstention(claim, evidence)
        or partition_count(claim, evidence)
        or arithmetic(claim, evidence)
    )
    if deterministic:
        return deterministic
    if not evidence.strip():
        return {
            "label": "UNVERIFIED",
            "reason": "No reviewable evidence was selected for this check.",
            "quotes": [],
        }
    if _unit_math and os.getenv("GROUNDED_UNIT_ARITHMETIC", "0") == "1":
        plan = plan_conversion(claim, evidence)
        if plan:
            cache_key = (plan.reference_claim, evidence, tuple(models.names))
            reused = reference_cache is not None and cache_key in reference_cache
            reference = (
                copy.deepcopy(reference_cache[cache_key])
                if reused
                else classify(models, plan.reference_claim, evidence, _unit_math=False)
            )
            reviews = reference.get("reviews", [])
            if (
                reference["label"] == "SUPPORTED"
                and not reference.get("failures")
                and len(reviews) == 2
                and len({row["model"] for row in reviews}) == 2
                and any(plan.definition in quote for quote in reference["quotes"])
                and not any(
                    conflicting_mass_aliases(quote) for quote in reference["quotes"]
                )
            ):
                label = plan.label()
                if reference_cache is not None and not reused:
                    reference_cache[cache_key] = copy.deepcopy(reference)
                return {
                    **reference,
                    "label": label,
                    "reason": EVIDENCE_REASONS[label],
                    "derivation": plan.metadata(),
                    "review_scope": "quoted unit definition; complete claim derived by exact arithmetic",
                    "review_reused_within_job": reused,
                }
    assessments, failures = review_pair(models, claim, evidence)
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
            "failures": failures or ["Distinct independent reviewers unavailable."],
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
    if assessments[0]["label"] == "PARTIALLY_SUPPORTED":
        # Partial reviews may quote complementary supported/missing assertions.
        # Preserve their union rather than dropping one side of the decision.
        return {
            "label": assessments[0]["label"],
            "reason": EVIDENCE_REASONS[assessments[0]["label"]],
            "quotes": list(
                dict.fromkeys(q for row in assessments for q in row["quotes"])
            ),
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
    # Each validated review supplies a complete evidence set for its verdict.
    # Keep one whole set rather than combining optional/background quotations
    # from both reviewers or intersecting away material compound assertions.
    selected_review = min(
        assessments,
        key=lambda row: (
            sum(len(q) for q in dict.fromkeys(row["quotes"])),
            len(row["quotes"]),
            len(row.get("quote_spans", [])),
        ),
    )
    return {
        "label": selected_review["label"],
        "reason": EVIDENCE_REASONS[selected_review["label"]],
        "quotes": list(dict.fromkeys(selected_review["quotes"])),
        "reviews": assessments,
        "quotation_review_model": selected_review["model"],
        **(
            {"quote_spans": [dict(span) for span in selected_review["quote_spans"]]}
            if "quote_spans" in selected_review
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
    def __init__(self, models, fetcher, search, fallback_search=None):
        self.models, self.fetcher, self.search = models, fetcher, search
        self.fallback_search = fallback_search

    def verify(self, text, citations, progress=lambda stage: None):
        deadline = time.monotonic() + 900
        citations = list(dict.fromkeys(citations))
        progress("Analyzing claims")
        with measured("claim_extraction") as counts:
            claims, unsupported = self.models.extract(text)
            counts["count"] = len(claims)
        if len(claims) > 60:
            unsupported.append(
                "Claims beyond the first 60 were not verified in this request."
            )
            claims = claims[:60]
        progress({"claim_count": len(claims)})
        documents = {}
        source_ids = {}
        transport_origins = {}
        independent_urls = set()
        # Only this verification owns these query vectors; no cross-job persistence.
        query_cache = {}
        reference_cache = {} if os.getenv("JOB_REFERENCE_CACHE", "0") == "1" else None

        def independent_counts():
            # Count actual selected URL checks, not search snippets or originals.
            # Reused URLs across claims remain one acquisition in this job.
            progress(
                {
                    "tracks": {
                        "independent": {
                            "total": len(independent_urls),
                            "completed": sum(
                                url in documents for url in independent_urls
                            ),
                            "accessible": sum(
                                documents.get(url, {}).get("accessible") is True
                                for url in independent_urls
                            ),
                        }
                    }
                }
            )

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
                    with measured(
                        "source_fetch", count=1, source_id=source_ids[url]
                    ) as outcome:
                        try:
                            documents[url] = self.fetcher(url)
                            outcome["accessible"] = documents[url]["accessible"]
                        except Exception:
                            outcome["accessible"] = False
                            raise
                except Exception:
                    documents[url] = {
                        "url": url,
                        "accessible": False,
                        "error": "Source unavailable, restricted, or unsupported.",
                    }
            return documents[url]

        def transport_key(url):
            try:
                return urlsplit(url)._replace(fragment="").geturl()
            except (TypeError, ValueError):
                # Let the existing fetch policy record malformed destinations
                # as unavailable rather than failing the whole acquisition job.
                return url

        def prefetch(urls):
            pending = [url for url in dict.fromkeys(urls) if url not in documents]
            if not pending:
                return
            for url in pending:
                source_ids.setdefault(url, len(source_ids) + 1)
            # Fragments never reach the HTTP server. Reuse that exact transport
            # snapshot within this job, keeping every original URL and track.
            representatives = []
            for url in pending:
                key = transport_key(url)
                if key not in transport_origins:
                    transport_origins[key] = url
                    representatives.append(url)
            # Only this coordinator mutates alias mappings; source I/O remains
            # bounded and distinct paths/redirect aliases still fetch separately.
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(copy_context().run, source, url)
                    for url in representatives
                ]
                for future in futures:
                    future.result()
            for url in pending:
                documents[url] = documents[transport_origins[transport_key(url)]]

        def discover(claim, claim_id):
            try:
                with measured("search", claim_id=claim_id) as counts:
                    found = self.search(claim)
                    counts["count"] = len(found)
                return found, []
            except Exception:
                return [], ["Independent discovery unavailable."]

        progress("Checking citations")
        first_discovery = None
        if claims and citations and os.getenv("PARALLEL_RETRIEVAL", "0") == "1":
            progress("Searching independent sources")
            # Only independent discovery overlaps citation transport. Join before
            # reviewing; the document cache has one transport owner throughout.
            with ThreadPoolExecutor(max_workers=2) as pool:
                searching = pool.submit(
                    copy_context().run, discover, claims[0]["text"], 1
                )
                prefetch(citations)
                first_discovery = searching.result()
        else:
            prefetch(citations)
        progress({"stages": {"citations": "complete" if citations else "unavailable"}})
        progress(
            {
                "tracks": {
                    "citation": {
                        "total": len(citations),
                        "completed": len(citations),
                        "accessible": sum(
                            documents[url]["accessible"] for url in citations
                        ),
                    }
                }
            }
        )
        output = []
        checked = 0
        check_budget = min(120, max(1, int(os.getenv("MAX_SOURCE_CHECKS", "60"))))
        for claim_id, item in enumerate(claims, 1):
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
            found, errors = (
                first_discovery
                if claim_id == 1 and first_discovery is not None
                else discover(claim, claim_id)
            )
            urls = list(dict.fromkeys(citations + found))[:16]
            progress("Verifying evidence")
            independent_urls.update(url for url in urls if url in found)
            independent_counts()
            initial_urls = urls[: max(0, check_budget - checked)]
            prefetch(initial_urls)
            independent_counts()
            # Discovery returning URLs is not the same as acquiring usable pages.
            # Keep original unavailable destinations, and use bounded independent
            # discovery through the same fetch/SSRF policy, never search snippets.
            slots = min(3, 16 - len(urls), check_budget - checked - len(initial_urls))
            if (
                self.fallback_search
                and slots > 0
                and not any(
                    documents[url]["accessible"]
                    for url in found
                    if url in documents and url in initial_urls
                )
                and time.monotonic() < deadline
            ):
                try:
                    with measured("alternate_search", claim_id=claim_id) as counts:
                        alternatives = list(dict.fromkeys(self.fallback_search(claim)))
                        counts["count"] = len(alternatives)
                    alternatives = [url for url in alternatives if url not in urls][
                        :slots
                    ]
                except Exception:
                    alternatives = []
                independent_urls.update(alternatives)
                independent_counts()
                prefetch(alternatives)
                independent_counts()
                found = list(dict.fromkeys(found + alternatives))
                urls += alternatives
                if any(documents[url]["accessible"] for url in alternatives):
                    errors = [
                        error
                        for error in errors
                        if error != "Independent discovery unavailable."
                    ]
            tracks = {"citation": [], "independent": []}
            content_origins = {}
            destination_origins = {}
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
                        "source_id": source_ids[url],
                        "accessible": False,
                        "label": "UNVERIFIED",
                        "reason": doc["error"],
                        "snippets": [],
                    }
                else:
                    if doc["text"] in reviewed_content:
                        verdict, snippets, selected = reviewed_content[doc["text"]]
                    else:
                        candidates = passages(doc["text"], claim, limit=20)
                        cached_rank = getattr(self.models, "rank_cached", None)
                        with measured(
                            "ranking",
                            count=len(candidates),
                            source_id=source_ids[url],
                            claim_id=claim_id,
                        ):
                            selected = (
                                cached_rank(claim, candidates, query_cache)
                                if cached_rank
                                else self.models.rank(claim, candidates)
                            )
                        evidence = "\n\n".join(p["text"] for p in selected)
                        with measured(
                            "classification",
                            source_id=source_ids[url],
                            claim_id=claim_id,
                        ):
                            verdict = classify(
                                self.models,
                                claim,
                                evidence,
                                reference_cache=reference_cache,
                            )
                        snippets = quoted_snippets(verdict, selected)
                        if snippets is None:
                            verdict = {
                                "label": "UNVERIFIED",
                                "reason": "Quotation crossed selected evidence boundaries.",
                                "quotes": [],
                                "failures": [
                                    "Selected quotations could not be validated."
                                ],
                            }
                            snippets = []
                        if (
                            os.getenv("REJECT_MASS_ALIASES", "0") == "1"
                            and verdict["label"] != "UNVERIFIED"
                            and is_mass_conversion(claim)
                            and any(
                                conflicting_mass_aliases(s["text"]) for s in snippets
                            )
                        ):
                            verdict = {
                                **verdict,
                                "label": "UNVERIFIED",
                                "reason": "Selected evidence contains inconsistent mass-unit aliases.",
                                "quotes": [],
                            }
                            verdict.pop("quote_spans", None)
                            snippets = []
                        reviewed_content[doc["text"]] = (verdict, snippets, selected)
                    result = {
                        "url": url,
                        "source_id": source_ids[url],
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
                    if verdict.get("failures"):
                        marker = "Evidence review could not be completed."
                        if marker not in errors:
                            errors.append(marker)
                    content_original = content_origins.setdefault(doc["text"], url)
                    destination_original = destination_origins.setdefault(
                        doc["url"], url
                    )
                    original = (
                        content_original
                        if content_original != url
                        else destination_original
                    )
                    if original != url:
                        result["duplicate_of"] = original
                        result["duplicate_reason"] = (
                            "identical_content"
                            if content_original != url
                            else "same_destination"
                        )
                    result["evidence_packet"] = {
                        "source_id": source_ids[url],
                        "claim_id": claim_id,
                        "origin_id": source_ids[original],
                        "attribution_status": "original attribution not established",
                        "selected_spans": [
                            {
                                "start": passage["start"],
                                "end": passage["end"],
                                "sha256": hashlib.sha256(
                                    passage["text"].encode()
                                ).hexdigest(),
                            }
                            for passage in selected
                        ],
                        "sha256": doc["sha256"],
                        "retrieved_at": doc["checked_at"],
                        "publication_time": doc.get("publication_time"),
                        "publication_status": doc.get(
                            "publication_status", "not established"
                        ),
                        "context_scope": "exact selected source spans; source-declared publication time"
                        if doc.get("publication_time")
                        else "exact selected source spans; unknown publication time",
                    }
                    if verdict.get("review_reconsidered"):
                        result["review_reconsidered"] = True
                    if verdict.get("derivation"):
                        result["derivation"] = verdict["derivation"]
                        result["review_scope"] = verdict["review_scope"]
                        result["review_reused_within_job"] = verdict.get(
                            "review_reused_within_job", False
                        )
                    if verdict.get("reviews"):
                        result["review_models"] = [
                            r["model"] for r in verdict["reviews"]
                        ]
                    if verdict.get("calculation"):
                        result["calculation"] = True
                for tag in tags:
                    tracks[tag].append(result)
            combined = tracks["citation"] + tracks["independent"]
            with measured("aggregation", count=len(combined), claim_id=claim_id):
                final_label = aggregate(combined)
            output.append(
                {
                    "text": claim,
                    "quote": item["quote"],
                    "label": final_label,
                    "tracks": tracks,
                    "errors": errors,
                }
            )
        progress(
            {
                "stages": {
                    "independent": "complete" if claims else "unavailable",
                    "evaluation": "complete" if claims else "unavailable",
                }
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
