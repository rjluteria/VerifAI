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
