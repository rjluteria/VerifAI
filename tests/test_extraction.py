import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.model import ModelError, Models


class ExtractionTests(unittest.TestCase):
    response = "The vessel weighs 7 kg and holds 9 litres."
    valid = {
        "claims": [
            {"text": "The vessel weighs 7 kg", "quote": "weighs 7 kg"},
            {"text": "The vessel holds 9 litres", "quote": "holds 9 litres"},
        ],
        "unsupported": [],
    }
    invalid = {
        "claims": [
            {"text": "The vessel holds 9 litres", "quote": "The vessel holds 9 litres"}
        ],
        "unsupported": [],
    }

    def test_reconstructed_quote_is_rejected_and_repaired_without_losing_assertions(
        self,
    ):
        with patch.object(
            Models, "call", side_effect=[self.invalid, self.valid]
        ) as call:
            claims, limitations = Models().extract(self.response, names=["reviewer"])
        self.assertEqual(claims, self.valid["claims"])
        self.assertEqual(limitations, [])
        self.assertEqual(call.call_count, 2)
        repair = call.call_args.args[2]
        self.assertEqual(repair["response"], self.response)
        self.assertIn("extraction-provenance", repair["repair"])
        self.assertTrue(all(c["quote"] in self.response for c in claims))

    def test_invalid_repairs_remain_unavailable_and_do_not_escape_retry_bound(self):
        with patch.object(Models, "call", return_value=self.invalid) as call:
            claims, limitations = Models().extract(self.response, names=["reviewer"])
        self.assertEqual(claims, [])
        self.assertTrue(limitations)
        self.assertEqual(call.call_count, 2)

    def test_network_failure_moves_to_next_provider_without_output_repair(self):
        with patch.object(
            Models, "call", side_effect=[ModelError("model-http-503"), self.valid]
        ) as call:
            claims, limitations = Models().extract(
                self.response, names=["first", "second"]
            )
        self.assertEqual(claims, self.valid["claims"])
        self.assertEqual(limitations, [])
        self.assertEqual([x.args[0] for x in call.call_args_list], ["first", "second"])
        self.assertNotIn("repair", call.call_args.args[2])

    def test_schema_repair_keeps_original_response_and_valid_assertions(self):
        with patch.object(Models, "call", side_effect=[{}, self.valid]) as call:
            claims, limitations = Models().extract(self.response, names=["reviewer"])
        self.assertEqual(claims, self.valid["claims"])
        self.assertEqual(limitations, [])
        self.assertIn("extraction-schema", call.call_args.args[2]["repair"])

    def test_attached_year_split_is_repaired_with_relationship_intact(self):
        response = "The company earned 8 million euros in 2024."
        split = {
            "claims": [
                {
                    "text": "The company earned 8 million euros.",
                    "quote": "The company earned 8 million euros",
                },
                {"text": "The company earned in 2024.", "quote": "in 2024"},
            ],
            "unsupported": [],
        }
        valid = {"claims": [{"text": response, "quote": response}], "unsupported": []}
        with patch.object(Models, "call", side_effect=[split, valid]) as call:
            claims, limitations = Models().extract(response, names=["reviewer"])
        self.assertEqual(claims, valid["claims"])
        self.assertEqual(limitations, [])
        self.assertIn("extraction-qualifier-split", call.call_args.args[2]["repair"])

    def test_separate_dated_events_remain_separate(self):
        response = "The company opened in 2024. The company closed in 2025."
        valid = {
            "claims": [
                {
                    "text": "The company opened in 2024.",
                    "quote": "The company opened in 2024.",
                },
                {
                    "text": "The company closed in 2025.",
                    "quote": "The company closed in 2025.",
                },
            ],
            "unsupported": [],
        }
        with patch.object(Models, "call", return_value=valid) as call:
            claims, limitations = Models().extract(response, names=["reviewer"])
        self.assertEqual(claims, valid["claims"])
        self.assertEqual(limitations, [])
        self.assertEqual(call.call_count, 1)

    def cached_review_model(self, disagree=False):
        model = Models()
        model.names = ["first", "second"]
        calls = []

        def call(name, instruction, data, *args):
            calls.append((name, data))
            if "response" in data:
                response = data["response"]
                subject = response.split(" has ")[0]
                return {
                    "claims": [
                        {"text": subject + " has 12 chairs.", "quote": "has 12 chairs"},
                        {"text": subject + " has 15 tables.", "quote": "15 tables"},
                    ],
                    "unsupported": [],
                }
            claim = data["claim"]
            if " and " in claim:
                if disagree and name == "second" and "previous_invalid_output" in data:
                    return {
                        "label": "CONTRADICTED",
                        "reason": "Disagreeing review.",
                        "quote_ids": [0],
                    }
                return {
                    "label": "PARTIALLY_SUPPORTED",
                    "reason": "Chairs known, tables unknown.",
                    "quote_ids": [0, 1],
                }
            return {
                "label": "CONTRADICTED"
                if disagree and name == "second" and "chairs" in claim
                else "SUPPORTED"
                if "chairs" in claim
                else "UNVERIFIED",
                "reason": "Independent atomic assessment.",
                "quote_ids": [0] if "chairs" in claim else [1],
            }

        model.call = call
        return model, calls

    def test_shared_structure_keeps_distinct_atomic_reviews_and_expires(self):
        from verifai.engine import classify

        model, calls = self.cached_review_model()
        claim = "Workshop A has 12 chairs and 15 tables."
        evidence = "Workshop A has 12 chairs. Its table count is unknown."
        for iteration in range(2):
            result = classify(model, claim, evidence)
            self.assertEqual(result["label"], "PARTIALLY_SUPPORTED")
            self.assertEqual(
                {r["model"] for r in result["reviews"]}, {"first", "second"}
            )
            self.assertEqual(
                {r["decomposition_model"] for r in result["reviews"]}, {"first"}
            )
            self.assertEqual(sum("response" in d for _, d in calls), iteration + 1)
        for name in model.names:
            atomic = [
                d["claim"]
                for n, d in calls
                if n == name and "claim" in d and " and " not in d["claim"]
            ]
            self.assertEqual(atomic.count("Workshop A has 12 chairs."), 2)
            self.assertEqual(atomic.count("Workshop A has 15 tables."), 2)

    def test_shared_structure_does_not_force_reviewer_agreement(self):
        from verifai.engine import classify

        model, calls = self.cached_review_model(disagree=True)
        result = classify(
            model,
            "Workshop A has 12 chairs and 15 tables.",
            "Workshop A has 12 chairs. Its table count is unknown.",
        )
        self.assertEqual(result["label"], "UNVERIFIED")
        self.assertEqual(
            {r["label"] for r in result["reviews"]},
            {"PARTIALLY_SUPPORTED", "CONTRADICTED"},
        )
        self.assertTrue(result["review_reconsidered"])
        self.assertEqual(sum("response" in d for _, d in calls), 1)

    def test_shared_structure_isolated_between_concurrent_claims(self):
        from concurrent.futures import ThreadPoolExecutor

        from verifai.engine import classify

        model, calls = self.cached_review_model()
        subjects = ["Workshop A", "Workshop B"]

        def run(subject):
            return classify(
                model,
                subject + " has 12 chairs and 15 tables.",
                subject + " has 12 chairs. Its table count is unknown.",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, subjects))
        self.assertTrue(all(r["label"] == "PARTIALLY_SUPPORTED" for r in results))
        extracted = [d["response"] for _, d in calls if "response" in d]
        self.assertCountEqual(
            extracted, [s + " has 12 chairs and 15 tables." for s in subjects]
        )
        for name in model.names:
            for subject in subjects:
                self.assertEqual(
                    sum(
                        n == name and d.get("claim") == subject + " has 15 tables."
                        for n, d in calls
                    ),
                    1,
                )
