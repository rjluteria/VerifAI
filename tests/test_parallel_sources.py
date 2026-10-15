import hashlib
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.engine import Engine


class ParallelSourceTests(unittest.TestCase):
    def test_bounded_overlap_deduplication_and_stable_tracks(self):
        claim = "The beacon is blue."
        urls = [
            "https://one.example/a",
            "https://two.example/b",
            "https://three.example/duplicate",
        ]

        class Model:
            source_review_concurrency = 2

            def extract(self, text):
                return [{"text": text, "quote": text}], []

            def rank(self, claim, candidates):
                return candidates

        def fetch(url):
            text = claim + (" The tower is tall." if url == urls[1] else "")
            return {
                "url": url,
                "text": text,
                "accessible": True,
                "checked_at": 1,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }

        barrier = threading.Barrier(2)
        calls = []
        lock = threading.Lock()

        def evaluate(model, claim, evidence, reference_cache=None):
            with lock:
                calls.append(evidence)
            barrier.wait(timeout=2)
            return {"label": "SUPPORTED", "quotes": [claim], "reason": "Fixture proof."}

        with patch("verifai.engine.classify", side_effect=evaluate):
            result = Engine(Model(), fetch, lambda claim: urls[1:]).verify(
                claim, urls[:1]
            )
        self.assertEqual(len(calls), 2)
        row = result["claims"][0]
        self.assertEqual(row["label"], "SUPPORTED")
        self.assertEqual([v["url"] for v in row["tracks"]["citation"]], urls[:1])
        self.assertEqual([v["url"] for v in row["tracks"]["independent"]], urls[1:])
        self.assertEqual(row["tracks"]["independent"][1]["duplicate_of"], urls[0])
        for item in row["tracks"]["citation"] + row["tracks"]["independent"]:
            self.assertEqual(item["snippets"][0]["text"], claim)


if __name__ == "__main__":
    unittest.main()
