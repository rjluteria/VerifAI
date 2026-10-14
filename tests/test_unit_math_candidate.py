import unittest
from unittest.mock import patch

from verifai.engine import classify
from verifai.unit_math import plan_conversion


class ReferenceReviewers:
    names = ("primary", "secondary")

    def __init__(self, reference_label="SUPPORTED", same_model=False):
        self.calls = []
        self.reference_label = reference_label
        self.same_model = same_model

    def judge(self, name, claim, evidence):
        self.calls.append(claim)
        label = self.reference_label if claim.startswith("1 ") else "UNVERIFIED"
        result = {
            "label": label,
            "reason": "review",
            "quotes": [evidence] if label == "SUPPORTED" else [],
        }
        if self.same_model:
            result["model"] = "same-standby"
        return result


class UnitMathCandidateTests(unittest.TestCase):
    def setUp(self):
        flags = patch.dict("os.environ", {"GROUNDED_UNIT_ARITHMETIC": "1"})
        flags.start()
        self.addCleanup(flags.stop)

    evidence = "1 microgram of vitamin D is equal to 40 IU."

    def test_observed_five_micrograms_miss_uses_validated_definition(self):
        models = ReferenceReviewers()
        result = classify(
            models,
            "5 micrograms of vitamin D equals 250 International Units of vitamin D",
            self.evidence,
        )
        self.assertEqual(result["label"], "CONTRADICTED")
        self.assertEqual(result["quotes"], [self.evidence])
        self.assertEqual(result["derivation"]["calculated_IU_fraction"], "200/1")
        self.assertEqual(len(models.calls), 2)
        self.assertTrue(all(claim.startswith("1 ") for claim in models.calls))

    def test_twentyfive_micrograms_support(self):
        result = classify(
            ReferenceReviewers(),
            "25 micrograms of vitamin D equals 1000 International Units of vitamin D.",
            self.evidence,
        )
        self.assertEqual(result["label"], "SUPPORTED")

    def test_mass_scales_use_exact_fractions(self):
        plan = plan_conversion(
            "0.005 milligrams of vitamin D equals 200 International Units of vitamin D.",
            self.evidence,
        )
        self.assertEqual(plan.label(), "SUPPORTED")

    def test_rejected_reference_cannot_supply_arithmetic_proof(self):
        result = classify(
            ReferenceReviewers("UNVERIFIED"),
            "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
            self.evidence,
        )
        self.assertEqual(result["label"], "UNVERIFIED")
        self.assertNotIn("derivation", result)

    def test_same_standby_is_not_two_independent_reference_reviewers(self):
        result = classify(
            ReferenceReviewers(same_model=True),
            "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
            self.evidence,
        )
        self.assertEqual(result["label"], "UNVERIFIED")
        self.assertNotIn("derivation", result)

    def test_wrong_entity_and_chemical_case_not_merged(self):
        self.assertIsNone(
            plan_conversion(
                "5 micrograms of vitamin A equals 250 International Units of vitamin A.",
                self.evidence,
            )
        )
        self.assertIsNone(
            plan_conversion(
                "5 micrograms of CO equals 250 International Units of CO.",
                "1 microgram of Co is equal to 40 IU.",
            )
        )

    def test_approximate_and_temporal_claims_use_semantic_path(self):
        for claim in [
            "About 5 micrograms of vitamin D equals 250 International Units of vitamin D.",
            "As of 2031, 5 micrograms of vitamin D equals 250 International Units of vitamin D.",
        ]:
            self.assertIsNone(plan_conversion(claim, self.evidence))

    def test_conflicting_definitions_do_not_choose_convenient_coefficient(self):
        evidence = self.evidence + " 1 microgram of vitamin D is equal to 50 IU."
        self.assertIsNone(
            plan_conversion(
                "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
                evidence,
            )
        )

    def test_source_condition_is_not_stripped_to_create_definition(self):
        self.assertIsNone(
            plan_conversion(
                "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
                "1 microgram of vitamin D is equal to 40 IU only under special conditions.",
            )
        )

    def test_nih_clause_and_selected_quote_are_exact(self):
        evidence = "RDAs for vitamin D are listed in both micrograms (mcg) and International Units (IU); 1 mcg vitamin D is equal to 40 IU (Table 2)."
        result = classify(
            ReferenceReviewers(),
            "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
            evidence,
        )
        self.assertEqual(result["label"], "CONTRADICTED")
        self.assertEqual(result["quotes"], [evidence])


if __name__ == "__main__":
    unittest.main()


class ReferenceCacheTests(unittest.TestCase):
    def test_identical_definition_context_reused_only_in_supplied_job_cache(self):
        models = ReferenceReviewers()
        evidence = "1 microgram of vitamin D is equal to 40 IU."
        with patch.dict("os.environ", {"GROUNDED_UNIT_ARITHMETIC": "1"}):
            cache = {}
            first = classify(
                models,
                "25 micrograms of vitamin D equals 1000 International Units of vitamin D.",
                evidence,
                reference_cache=cache,
            )
            second = classify(
                models,
                "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
                evidence,
                reference_cache=cache,
            )
            self.assertEqual(first["label"], "SUPPORTED")
            self.assertEqual(second["label"], "CONTRADICTED")
            self.assertTrue(second["review_reused_within_job"])
            self.assertEqual(len(models.calls), 2)
            classify(
                models,
                "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
                evidence,
                reference_cache={},
            )
            self.assertEqual(len(models.calls), 4)
            classify(
                models,
                "5 micrograms of vitamin D equals 250 International Units of vitamin D.",
                evidence + " Context changed.",
                reference_cache=cache,
            )
            self.assertEqual(len(models.calls), 6)
        self.assertFalse(hasattr(models, "reference_cache"))
