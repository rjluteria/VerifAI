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
from verifai.engine import (
    Engine,
    aggregate,
    arithmetic,
    classify,
    passages,
    quoted_snippets,
)
from verifai.model import ModelError, Models, retry_delay
from verifai.network import FetchRejected, destination
from verifai.server import Service, handler, strict_json, valid_request
from verifai.sources import Text, discovery


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
    def test_source_prefetch_is_bounded_and_preserves_url_attribution(self):
        barrier = threading.Barrier(2)
        active = 0
        maximum = 0
        lock = threading.Lock()

        def fetch(url):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            barrier.wait(timeout=2)
            with lock:
                active -= 1
            return {
                "url": url,
                "accessible": True,
                "text": "A is B.",
                "checked_at": 1,
                "sha256": "synthetic",
            }

        urls = ["https://first.example/", "https://second.example/"]
        result = Engine(Reviewers(), fetch, lambda claim: []).verify("A is B.", urls)
        self.assertEqual(maximum, 2)
        self.assertEqual(
            [row["url"] for row in result["claims"][0]["tracks"]["citation"]], urls
        )
        self.assertEqual(result["claims"][0]["label"], "SUPPORTED")

    def test_short_document_keeps_distant_qualification(self):
        text = (
            "The medicine is effective. "
            + "Background. " * 700
            + "Only adults were studied."
        )
        self.assertEqual(
            passages(text, "The medicine is effective in children."),
            [{"text": text, "start": 0, "end": len(text)}],
        )

    def test_passage_boundaries_and_offsets(self):
        sentence = "A detailed source qualification " + "word " * 350 + "ends here. "
        text = sentence * 8
        selected = passages(text, "source qualification", limit=20)
        self.assertTrue(selected)
        for row in selected:
            self.assertEqual(row["text"], text[row["start"] : row["end"]])
            self.assertTrue(row["text"].endswith("ends here. "))

    def test_oversized_indivisible_evidence_abstains(self):
        self.assertEqual(passages("word " * 3000, "word"), [])

    def test_observational_absence_and_unspecified_duration_abstain_without_guessed_metrics(
        self,
    ):
        model = Reviewers(["CONTRADICTED", "CONTRADICTED"])
        result = classify(
            model,
            "Exercise caused better recall.",
            "The observational study reported a correlation. It cannot prove causation.",
        )
        self.assertEqual(result["label"], "UNVERIFIED")
        result = classify(
            model,
            "Sensor B lasts 14 days.",
            "Sensor B weighs 1 kg. Battery endurance is 9 days.",
        )
        self.assertEqual(result["label"], "UNVERIFIED")
        # A direct disproof or a named metric must still reach factual review.
        self.assertEqual(
            classify(
                model,
                "Exercise caused better recall.",
                "The observational study reported a correlation. It cannot prove causation. A randomized trial disproved the claimed effect.",
            )["label"],
            "CONTRADICTED",
        )
        self.assertEqual(
            classify(
                model, "Sensor B battery lasts 14 days.", "Battery endurance is 9 days."
            )["label"],
            "CONTRADICTED",
        )

    def test_temporal_absence_guard_requires_matching_increase_and_closed_context(self):
        models = Reviewers(["CONTRADICTED", "CONTRADICTED"])
        evidence = "Yield increased after the retrofit was introduced. There is no causal evidence."
        self.assertEqual(
            classify(models, "The retrofit caused increased yield.", evidence)["label"],
            "UNVERIFIED",
        )
        self.assertEqual(
            classify(models, "The retrofit caused decreased yield.", evidence)["label"],
            "CONTRADICTED",
        )
        self.assertEqual(
            classify(
                models,
                "The retrofit caused increased yield and lowered costs.",
                evidence + " Costs doubled.",
            )["label"],
            "CONTRADICTED",
        )
        self.assertEqual(
            classify(
                models,
                "The report proved the retrofit caused increased yield.",
                evidence,
            )["label"],
            "CONTRADICTED",
        )

    def test_threshold_absence_does_not_mask_explicit_bounded_detection_or_later_findings(
        self,
    ):
        claim = "The laboratory detected cadmium."
        evidence = "The laboratory did not detect cadmium above the detection limit."
        self.assertEqual(
            classify(Reviewers(["CONTRADICTED", "CONTRADICTED"]), claim, evidence)[
                "label"
            ],
            "UNVERIFIED",
        )
        bounded = "The laboratory detected cadmium above the detection limit."
        self.assertEqual(
            classify(Reviewers(["CONTRADICTED", "CONTRADICTED"]), bounded, evidence)[
                "label"
            ],
            "CONTRADICTED",
        )
        self.assertEqual(
            classify(
                Reviewers(), claim, evidence + " Cadmium was detected below that limit."
            )["label"],
            "SUPPORTED",
        )
        mismatch = classify(
            Reviewers(["UNVERIFIED", "UNVERIFIED"]),
            "The laboratory detected copper.",
            evidence,
        )
        self.assertEqual(len(mismatch["reviews"]), 2)

    def test_partial_review_with_conflicting_atomic_fact_is_repaired_not_forced(self):
        models = Models()
        calls = []

        def call(name, prompt, data):
            calls.append(data)
            if data["claim"] == "The depot has 6 bays":
                return {
                    "label": "SUPPORTED",
                    "reason": "Bay count matches.",
                    "quote_ids": [0],
                }
            if data["claim"] == "The depot has 90 staff":
                return {
                    "label": "CONTRADICTED",
                    "reason": "Staff count differs.",
                    "quote_ids": [0],
                }
            if "atomic_checks" in data:
                return {
                    "label": "CONTRADICTED",
                    "reason": "The incompatible staff count takes precedence.",
                    "quote_ids": [0],
                }
            return {
                "label": "PARTIALLY_SUPPORTED",
                "reason": "Six bays are supported but staff are not.",
                "quote_ids": [0],
            }

        models.call = call
        models.extract = lambda *args, **kwargs: (
            [{"text": "The depot has 6 bays"}, {"text": "The depot has 90 staff"}],
            [],
        )
        result = models.judge(
            "test",
            "The depot has 6 bays and 90 staff.",
            "The depot has 6 bays and 70 staff.",
        )
        self.assertEqual(result["label"], "CONTRADICTED")
        self.assertEqual(result["review_attempts"], 2)
        self.assertIn("atomic_checks", calls[-1])
        self.assertEqual(result["quotes"], ["The depot has 6 bays and 70 staff."])

    def test_repeated_quote_preserves_the_model_selected_source_occurrence(self):
        text = "Alpha is the first enclosure. Its height is 121 metres.\n\nBeta is the second enclosure. Its height is 121 metres."
        models = Models()
        models.extract = lambda claim: ([{"text": claim, "quote": claim}], [])
        models.rank = lambda claim, passages, **kwargs: passages
        models.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "Beta's height matches.",
            "quote_ids": [3],
        }
        document = {
            "url": "https://example.org/enclosures",
            "text": text,
            "accessible": True,
            "checked_at": 0,
            "sha256": "fixture",
        }
        result = Engine(models, lambda url: document, lambda claim: []).verify(
            "Beta is 121 metres tall.", [document["url"]]
        )
        snippet = result["claims"][0]["tracks"]["citation"][0]["snippets"][0]
        self.assertEqual(snippet["text"], "Its height is 121 metres.")
        self.assertEqual(snippet["start"], text.rfind(snippet["text"]))
        self.assertEqual(text[snippet["start"] : snippet["end"]], snippet["text"])

    def test_quote_occurrences_map_through_ranked_passages_and_reject_cross_boundary(
        self,
    ):
        selected = [{"text": "Same.", "start": 90}, {"text": "Same.", "start": 10}]
        verdict = {
            "quotes": ["Same."],
            "quote_spans": [
                {"text": "Same.", "start": 0, "end": 5},
                {"text": "Same.", "start": 7, "end": 12},
            ],
        }
        self.assertEqual(
            [s["start"] for s in quoted_snippets(verdict, selected)], [90, 10]
        )
        crossing = {
            "quotes": [".\n\nS"],
            "quote_spans": [{"text": ".\n\nS", "start": 4, "end": 8}],
        }
        self.assertIsNone(quoted_snippets(crossing, selected))

    def test_compound_duration_keeps_other_supported_fact_in_review(self):
        model = Reviewers(["PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED"])
        self.assertEqual(
            classify(
                model,
                "The device weighs 2 kg and lasts 10 hours.",
                "The device weighs 2 kg. Battery life has not been measured.",
            )["label"],
            "PARTIALLY_SUPPORTED",
        )

    def test_partial_review_that_affirms_contradiction_is_repaired_without_forcing_label(
        self,
    ):
        model = Models()
        responses = iter(
            [
                {
                    "label": "PARTIALLY_SUPPORTED",
                    "reason": "The date is contradicted; the length matches.",
                    "quote_ids": [0],
                },
                {
                    "label": "CONTRADICTED",
                    "reason": "The opening date is incompatible.",
                    "quote_ids": [0],
                },
            ]
        )
        model.call = lambda *args: next(responses)
        self.assertEqual(
            model.judge(
                "test",
                "The bridge is 30 m and opened in 2000.",
                "The bridge is 30 m and opened in 2001.",
            )["label"],
            "CONTRADICTED",
        )

    def test_partial_reason_with_negated_contradiction_remains_valid(self):
        model = Models()
        model.call = lambda name, prompt, data: {
            "label": "PARTIALLY_SUPPORTED"
            if " and " in data["claim"]
            else "SUPPORTED"
            if "weighs" in data["claim"]
            else "UNVERIFIED",
            "reason": "Mass is supported; volume unreported. No assertions are contradicted.",
            "quote_ids": [0],
        }
        model.extract = lambda *args, **kwargs: (
            [{"text": "The crate weighs 2 kg."}, {"text": "The crate holds 3 litres."}],
            [],
        )
        self.assertEqual(
            model.judge(
                "test",
                "The crate weighs 2 kg and holds 3 litres.",
                "The crate weighs 2 kg; volume is unknown.",
            )["label"],
            "PARTIALLY_SUPPORTED",
        )

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
            "quote_ids": [-1],
        }
        with self.assertRaises(ModelError):
            model.judge("test", "a", "b")

    def test_no_quote_support_rejected(self):
        model = Models()
        model.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "yes",
            "quote_ids": [],
        }
        with self.assertRaises(ModelError):
            model.judge("test", "a", "b")

    def test_invalid_label_type_rejected(self):
        model = Models()
        model.call = lambda *args: {"label": [], "reason": "bad", "quote_ids": []}
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
                self.assertEqual(payload["reasoning_effort"], "low")
                self.assertNotIn("chat_template_kwargs", payload)

    def test_invalid_quote_repair_keeps_exact_validation(self):
        model = Models()
        outputs = iter(
            [
                {"label": "SUPPORTED", "reason": "yes", "quote_ids": [99]},
                {"label": "SUPPORTED", "reason": "yes", "quote_ids": [0]},
            ]
        )
        model.call = lambda *args: next(outputs)
        result = model.judge("test", "A is B.", "A is B.")
        self.assertEqual(result["quotes"], ["A is B."])
        self.assertEqual(result["review_attempts"], 2)

    def test_repeated_invalid_quote_repair_abstains(self):
        model = Models()
        model.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "yes",
            "quote_ids": [-1],
        }
        with self.assertRaisesRegex(ModelError, "ungrounded-model-output"):
            model.judge("test", "A is B.", "A is B.")

    def test_passage_separator_does_not_become_quoted_source_text(self):
        model = Models()
        model.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "direct",
            "quote_ids": [1],
        }
        original_passages = ["Navigation ends.\n", "Ocean covers 71%.\n"]
        result = model.judge(
            "test", "Ocean covers 71%.", "\n\n".join(original_passages)
        )
        self.assertEqual(result["quotes"], ["Ocean covers 71%."])
        self.assertTrue(
            all(any(q in p for p in original_passages) for q in result["quotes"])
        )

    def test_selected_evidence_keeps_curly_quotes_and_context(self):
        model = Models()
        model.call = lambda *args: {
            "label": "SUPPORTED",
            "reason": "direct",
            "quote_ids": [0, 1],
        }
        evidence = "Your “day” is 243 days. This means rotation, not a solar day."
        result = model.judge("test", "Rotation takes 243 days.", evidence)
        self.assertEqual(" ".join(result["quotes"]), evidence)
        for bad in (True, 2, -1, "0"):
            model.call = lambda *args: {
                "label": "SUPPORTED",
                "reason": "direct",
                "quote_ids": [bad],
            }
            with self.subTest(bad=bad), self.assertRaises(ModelError):
                model.judge("test", "Rotation takes 243 days.", evidence)

    def test_standby_identity_is_distinct_and_visible(self):
        model = Models()

        def judge(name, *args):
            if name == model.names[0]:
                raise ModelError("model-http-429")
            return {"label": "SUPPORTED", "reason": "direct", "quotes": ["A is B."]}

        model.judge = judge
        result = classify(model, "A is B.", "A is B.")
        self.assertEqual(result["label"], "SUPPORTED")
        self.assertEqual(len({r["model"] for r in result["reviews"]}), 2)
        self.assertEqual(result["reviews"][0]["requested_model"], model.names[0])

    def test_same_standby_cannot_count_as_two_reviewers(self):
        model = Models()
        model.review = lambda *args, **kwargs: {
            "model": "same-standby",
            "label": "SUPPORTED",
            "reason": "direct",
            "quotes": ["A is B."],
        }
        self.assertEqual(classify(model, "A is B.", "A is B.")["label"], "UNVERIFIED")

    def test_atomic_related_fact_cannot_be_partial_support(self):
        model = Models()
        model.call = lambda *args: {
            "label": "PARTIALLY_SUPPORTED",
            "reason": "related",
            "quote_ids": [0],
        }
        model.extract = lambda text, **kwargs: ([{"text": text, "quote": text}], [])
        self.assertEqual(
            model.judge("test", "Ocean covers 71%.", "Ocean covers 70%.")["label"],
            "UNVERIFIED",
        )

    def test_one_bounded_reassessment_preserves_distinct_agreement(self):
        models = Reviewers(["CONTRADICTED", "PARTIALLY_SUPPORTED"])
        calls = []

        def reconcile(claim, evidence):
            calls.append((claim, evidence))
            return (
                [
                    {
                        "model": n,
                        "label": "CONTRADICTED",
                        "reason": "incompatible year",
                        "quotes": [evidence],
                    }
                    for n in models.names
                ],
                [],
            )

        models.reconcile = reconcile
        result = classify(models, "Bridge opened in 2010.", "Bridge opened in 2011.")
        self.assertEqual(result["label"], "CONTRADICTED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result["initial_reviews"]), 2)
        models.reconcile = lambda *args: (
            [
                {
                    "model": n,
                    "label": label,
                    "reason": "still disagree",
                    "quotes": ["evidence"],
                }
                for n, label in zip(models.names, ["SUPPORTED", "CONTRADICTED"])
            ],
            [],
        )
        self.assertEqual(classify(models, "claim", "evidence")["label"], "UNVERIFIED")

    def test_unavailable_decomposition_does_not_replace_valid_evidence_reviewer(self):
        model = Models()
        model.call = lambda name, prompt, data: {
            "label": "PARTIALLY_SUPPORTED"
            if " and " in data["claim"]
            else "SUPPORTED"
            if "branches" in data["claim"]
            else "UNVERIFIED",
            "reason": "one missing",
            "quote_ids": [0],
        }
        model.extract = lambda text, names: (
            ([], ["unavailable"])
            if names == [model.names[1]]
            else (
                [
                    {"text": "A has 10 branches", "quote": "A has 10 branches"},
                    {"text": "A has 40 employees", "quote": "40 employees"},
                ],
                [],
            )
        )
        row = model.review(
            model.names[1],
            "A has 10 branches and 40 employees",
            "A has 10 branches. Employee count is unknown.",
        )
        self.assertEqual(row["model"], model.names[1])
        self.assertEqual(row["label"], "PARTIALLY_SUPPORTED")
        self.assertEqual(row["decomposition_model"], "z-ai/glm-5.3-flash")
        self.assertNotIn("requested_model", row)

    def test_reassessment_waits_once_for_observed_reviewer_cooldown(self):
        model = Models()
        model.review = lambda name, *args, **kwargs: {
            "model": name,
            "label": "SUPPORTED",
        }
        with (
            patch(
                "verifai.model._RATE_LIMITED_UNTIL",
                {model.names[0]: 135, model.names[1]: 125},
            ),
            patch("verifai.model.time.monotonic", return_value=100),
            patch("verifai.model.time.sleep") as wait,
        ):
            rows, failures = model.reconcile("claim", "evidence")
            wait.assert_called_once_with(35)
            self.assertEqual({r["model"] for r in rows}, set(model.names))
            self.assertEqual(failures, [])

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

    def test_copied_sources_keep_provenance_without_new_reviews(self):
        models = Reviewers()
        calls = []
        original = models.judge

        def judge(*args):
            calls.append(args)
            return original(*args)

        models.judge = judge

        def get(url):
            return {
                "url": url,
                "accessible": True,
                "text": "A is B.",
                "checked_at": 1,
                "sha256": "same",
            }

        result = Engine(models, get, lambda c: ["https://copy.example/b"]).verify(
            "A is B.", ["https://original.example/a"]
        )
        claim = result["claims"][0]
        copy = claim["tracks"]["independent"][0]
        self.assertEqual(copy["duplicate_of"], "https://original.example/a")
        self.assertEqual(copy["final_url"], "https://copy.example/b")
        self.assertEqual(copy["snippets"][0]["text"], "A is B.")
        self.assertEqual(len(calls), 2)

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

    def test_discovery_expands_query_without_treating_snippets_as_proof(self):
        responses = [
            io.BytesIO(
                json.dumps(
                    {
                        "results": [
                            {
                                "url": "https://example.org/a",
                                "content": "Unverified search snippet",
                            }
                        ]
                    }
                ).encode()
            ),
            io.BytesIO(
                json.dumps(
                    {
                        "results": [
                            {"url": "https://example.org/a"},
                            {"url": "https://official.example/b"},
                        ]
                    }
                ).encode()
            ),
        ]
        with (
            patch.dict("os.environ", {"ALLOW_KEYLESS_SEARCH": "1"}),
            patch(
                "verifai.sources.urllib.request.urlopen", side_effect=responses
            ) as calls,
        ):
            self.assertEqual(
                discovery("claim"),
                ["https://example.org/a", "https://official.example/b"],
            )
        queries = [json.loads(call.args[0].data) for call in calls.call_args_list]
        self.assertEqual(
            [q["query"] for q in queries], ["claim", "claim official source"]
        )
        self.assertTrue(
            all(
                not q["include_answer"] and not q["include_raw_content"]
                for q in queries
            )
        )

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
            "https://[fc00::1]/",
            "https://[fe80::1]/",
            "https://[::ffff:127.0.0.1]/",
            "https://0.0.0.0/",
            "https://100.64.0.1/",
            "https://192.168.1.1/",
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
