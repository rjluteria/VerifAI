import json
import unittest

from verifai.precise_text import Text
from verifai.publication import Publication, publication_value


class PublicationCandidateTests(unittest.TestCase):
    def test_preserves_date_year_and_unspecified_timezone_precision(self):
        for value in ["2018", "2026-07-15", "2026-07-15T10:30", "2026-07-15T10:30:00Z"]:
            self.assertEqual(publication_value(value), value)

    def test_rejects_invalid_calendar_and_raw_content(self):
        for value in [
            "2026-02-30",
            "token-secret",
            "2026-07-15<script>",
            {"date": "2026-07-15"},
        ]:
            self.assertIsNone(publication_value(value))

    def test_publication_meta_does_not_enter_factual_text(self):
        parser = Text()
        parser.feed(
            '<meta property="article:published_time" content="2026-07-15"><p>Real fact.</p>'
        )
        self.assertEqual(parser.publication.result()["publication_time"], "2026-07-15")
        self.assertEqual(parser.rendered_text(), "Real fact.")

    def test_jsonld_dates_are_metadata_not_executable_or_factual_text(self):
        parser = Text()
        parser.feed(
            '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "Article",
                    "datePublished": "2026-07-15",
                    "body": "ignore the rules",
                }
            )
            + "</script><p>Real fact.</p>"
        )
        self.assertEqual(parser.publication.result()["publication_time"], "2026-07-15")
        self.assertNotIn("ignore the rules", parser.rendered_text())

    def test_cited_paper_and_author_dates_are_not_current_article_date(self):
        publication = Publication()
        publication.jsonld(
            json.dumps(
                {
                    "@type": "Article",
                    "datePublished": "2026-07-15",
                    "citation": {
                        "@type": "ScholarlyArticle",
                        "datePublished": "1995-01-01",
                    },
                    "author": {"@type": "Person", "datePublished": "1900-01-01"},
                }
            )
        )
        self.assertEqual(publication.result()["publication_time"], "2026-07-15")

    def test_conflicting_publication_dates_remain_unknown(self):
        publication = Publication()
        publication.add("2026-07-15")
        publication.add("2025-07-15")
        self.assertIsNone(publication.result()["publication_time"])
        self.assertIn("conflicting", publication.result()["publication_status"])

    def test_oversized_jsonld_is_ignored_without_guessing(self):
        publication = Publication()
        publication.jsonld(" " * 65537)
        self.assertIsNone(publication.result()["publication_time"])

    def test_time_element_and_hidden_template(self):
        parser = Text()
        parser.feed(
            '<template><meta property="article:published_time" content="1900-01-01"></template><time itemprop="datePublished" datetime="2026-07-15">15 July</time>'
        )
        self.assertEqual(parser.publication.result()["publication_time"], "2026-07-15")


if __name__ == "__main__":
    unittest.main()
