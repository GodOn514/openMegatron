import sys
from pathlib import Path
import unittest


RESEARCH_DIR = Path(__file__).resolve().parents[1] / "pysrc" / "skills" / "research"
sys.path.insert(0, str(RESEARCH_DIR))

from research_common import infer_contribution_type, infer_method, venue_score  # noqa: E402


class ResearchCommonInferenceTests(unittest.TestCase):
    def test_systematic_review_is_not_tagged_as_rag(self):
        text = "A systematic review and meta-analysis of human-AI collaboration."
        self.assertEqual(infer_method(text), "systematic review / meta-analysis")

    def test_rag_marker_uses_word_boundary(self):
        text = "The average improvement is evaluated in a user study."
        self.assertNotIn("retrieval / RAG", infer_method(text))

    def test_meta_analysis_contribution_type(self):
        text = "This meta-analysis synthesizes experimental evidence."
        self.assertEqual(infer_contribution_type(text), "review / meta-analysis / evidence synthesis")

    def test_journal_alias_does_not_match_book_series_substring(self):
        venue = "Advances in logistics, operations, and management science book series"
        self.assertEqual(venue_score(venue, domain="management"), 0)


if __name__ == "__main__":
    unittest.main()
