import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from verifai.model import Models


class RankingTests(unittest.TestCase):
    def test_only_successful_query_embeddings_are_reused_within_supplied_cache(self):
        models = Models()
        models.key = "synthetic-test-key"
        calls = []
        candidates = [
            {"text": "source " + str(i), "start": i, "end": i + 1} for i in range(8)
        ]

        def response(request, timeout):
            data = json.loads(request.data)
            calls.append(data["input_type"])
            return io.BytesIO(
                json.dumps(
                    {
                        "data": [
                            {"index": i, "embedding": [1, i + 1]}
                            for i in range(len(data["input"]))
                        ]
                    }
                ).encode()
            )

        with patch("verifai.model.paced_open", side_effect=response):
            cache = {}
            first = models.rank_cached("A claim.", candidates, cache)
            second = models.rank_cached("A claim.", candidates, cache)
            self.assertEqual(first, second)
            self.assertEqual(calls, ["passage", "query", "passage"])
            models.rank_cached("A claim.", candidates, {})
            self.assertEqual(calls[-2:], ["passage", "query"])
            models.rank_cached("A different claim.", candidates, cache)
            self.assertEqual(calls[-2:], ["passage", "query"])
        self.assertFalse(hasattr(models, "query_cache"))

    def test_failed_embeddings_do_not_poison_the_request_cache(self):
        models = Models()
        models.key = "synthetic-test-key"
        candidates = [
            {"text": "A source.", "start": 0, "end": 9},
            {"text": "Another source.", "start": 9, "end": 24},
        ]
        cache = {}
        with patch("verifai.model.paced_open", side_effect=TimeoutError()):
            self.assertEqual(
                models.rank_cached("A claim.", candidates, cache), candidates
            )
        self.assertEqual(cache, {})


if __name__ == "__main__":
    unittest.main()


class JobPassageCacheTests(unittest.TestCase):
    def test_reuses_exact_passages_only_inside_one_job(self):
        models = Models()
        models.key = "synthetic-test-key"
        calls = []
        candidates = [
            {"text": "source " + str(i), "start": i, "end": i + 1} for i in range(8)
        ]

        def response(request, timeout):
            data = json.loads(request.data)
            calls.append((data["input_type"], data["input"]))
            return io.BytesIO(
                json.dumps(
                    {
                        "data": [
                            {"index": i, "embedding": [1, i + 1]}
                            for i in range(len(data["input"]))
                        ]
                    }
                ).encode()
            )

        with (
            patch.dict("os.environ", {"JOB_PASSAGE_CACHE": "1"}),
            patch("verifai.model.paced_open", side_effect=response),
        ):
            cache = {}
            first = models.rank_cached("A claim.", candidates, cache)
            self.assertEqual(models.rank_cached("A claim.", candidates, cache), first)
            self.assertEqual(len(calls), 2)
            models.rank_cached("Another claim.", candidates, cache)
            self.assertEqual([c[0] for c in calls], ["passage", "query", "query"])
            models.rank_cached("A claim.", candidates, {})
            self.assertEqual([c[0] for c in calls[-2:]], ["passage", "query"])
            changed = [dict(c) for c in candidates]
            changed[0]["text"] += " Correction: not confirmed."
            models.rank_cached("A claim.", changed, cache)
            self.assertEqual(calls[-1], ("passage", [changed[0]["text"]]))
        self.assertFalse(hasattr(models, "passage_cache"))
