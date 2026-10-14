import hashlib
import unittest
from unittest.mock import patch

from verifai.engine import Engine
from verifai.unit_aliases import conflicting_mass_aliases, is_mass_conversion


class UnitAliasCandidateTests(unittest.TestCase):
    def setUp(self):
        flags = patch.dict("os.environ", {"REJECT_MASS_ALIASES": "1"})
        flags.start()
        self.addCleanup(flags.stop)

    def test_observed_harvard_wording(self):
        self.assertTrue(conflicting_mass_aliases("20 micrograms (mcg or mg)"))

    def test_scaled_mass_alias_errors(self):
        for text in ["milligrams (mg or g)", "grams (g or kg)"]:
            with self.subTest(text=text):
                self.assertTrue(conflicting_mass_aliases(text))

    def test_equivalent_microgram_spellings(self):
        for text in ["micrograms (mcg or µg)", "micrograms (μg/ug)"]:
            with self.subTest(text=text):
                self.assertFalse(conflicting_mass_aliases(text))

    def test_scaled_numeric_conversion_outside_alias_guard(self):
        self.assertFalse(conflicting_mass_aliases("20 micrograms (20 mcg or 0.02 mg)"))

    def test_correction_not_an_alias(self):
        self.assertFalse(conflicting_mass_aliases("micrograms (not mg; use mcg)"))

    def test_unknown_unit_remains_semantic(self):
        self.assertFalse(conflicting_mass_aliases("micrograms (mcg or custom units)"))

    def test_claim_scope_preserves_referent(self):
        self.assertTrue(
            is_mass_conversion(
                "20 micrograms of vitamin D equals 800 International Units of vitamin D."
            )
        )
        self.assertFalse(
            is_mass_conversion(
                "20 micrograms of vitamin D equals 800 International Units of vitamin A."
            )
        )

    def test_claim_scope_excludes_reports_and_compounds(self):
        self.assertFalse(is_mass_conversion("The paper misprints micrograms as mg."))
        self.assertFalse(
            is_mass_conversion(
                "20 micrograms of vitamin D equals 800 International Units of vitamin D. It is always safe."
            )
        )

    def test_engine_retains_claim_and_tracks_but_rejects_bad_proof(self):
        class Reviewers:
            names = ("primary", "secondary")

            def __init__(self):
                self.calls = []

            def extract(self, text):
                return ([{"text": text, "quote": text}], [])

            def judge(self, name, claim, evidence):
                self.calls.append(name)
                return {"label": "SUPPORTED", "reason": "review", "quotes": [evidence]}

            def rank(self, claim, candidates):
                return candidates

        text = "20 micrograms of vitamin D equals 800 International Units of vitamin D."
        evidence = "Vitamin D is 20 micrograms (mcg or mg) or 800 international units."
        models = Reviewers()

        def fetch(url):
            return {
                "url": url,
                "text": evidence,
                "accessible": True,
                "checked_at": 123,
                "sha256": hashlib.sha256(evidence.encode()).hexdigest(),
            }

        result = Engine(models, fetch, lambda claim: []).verify(
            text, ["https://example.org/fact"]
        )
        claim = result["claims"][0]
        citation = claim["tracks"]["citation"][0]
        self.assertEqual(claim["text"], text)
        self.assertEqual(claim["label"], "UNVERIFIED")
        self.assertEqual(set(models.calls), {"primary", "secondary"})
        self.assertTrue(citation["accessible"])
        self.assertEqual(citation["label"], "UNVERIFIED")
        self.assertEqual(citation["snippets"], [])
        self.assertIn("inconsistent mass-unit aliases", citation["reason"])
        self.assertEqual(claim["tracks"]["independent"], [])


if __name__ == "__main__":
    unittest.main()
