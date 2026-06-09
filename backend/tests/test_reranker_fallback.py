import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import reranker


class RerankerFallbackTests(unittest.TestCase):
    """Tests for the fallback_scores parameter in rerank_with_cohere."""

    def _run(self, coro):
        return asyncio.run(coro)

    # -- Cohere success: fallback_scores ignored --------------------------

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_success_ignores_fallback_scores(self, mock_get_client):
        """When Cohere succeeds, fallback_scores are never used."""
        mock_client = MagicMock()
        mock_client.rerank.return_value = SimpleNamespace(
            results=[
                SimpleNamespace(index=2, relevance_score=0.95),
                SimpleNamespace(index=0, relevance_score=0.80),
            ]
        )
        mock_get_client.return_value = mock_client

        result = self._run(
            reranker.rerank_with_cohere(
                "test query",
                ["doc0", "doc1", "doc2"],
                top_n=2,
                fallback_scores=[0.1, 0.2, 0.3],
            )
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["index"], 2)
        self.assertAlmostEqual(result[0]["score"], 0.95)
        self.assertEqual(result[1]["index"], 0)
        self.assertAlmostEqual(result[1]["score"], 0.80)

    # -- Cohere failure + valid fallback_scores ---------------------------

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_failure_uses_fallback_scores(self, mock_get_client):
        """When Cohere fails and fallback_scores are provided, results are sorted by those scores."""
        mock_get_client.side_effect = RuntimeError("API down")

        result = self._run(
            reranker.rerank_with_cohere(
                "test query",
                ["doc0", "doc1", "doc2"],
                top_n=3,
                fallback_scores=[0.5, 0.9, 0.7],
            )
        )

        self.assertEqual(len(result), 3)
        # Sorted by fallback score descending: 0.9 (idx=1), 0.7 (idx=2), 0.5 (idx=0)
        self.assertEqual(result[0]["index"], 1)
        self.assertAlmostEqual(result[0]["score"], 0.9)
        self.assertEqual(result[1]["index"], 2)
        self.assertAlmostEqual(result[1]["score"], 0.7)
        self.assertEqual(result[2]["index"], 0)
        self.assertAlmostEqual(result[2]["score"], 0.5)

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_failure_fallback_scores_with_top_n(self, mock_get_client):
        """Fallback scores are correctly truncated to top_n."""
        mock_get_client.side_effect = RuntimeError("API down")

        result = self._run(
            reranker.rerank_with_cohere(
                "test query",
                ["doc0", "doc1", "doc2", "doc3"],
                top_n=2,
                fallback_scores=[0.3, 0.9, 0.5, 0.1],
            )
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["index"], 1)
        self.assertAlmostEqual(result[0]["score"], 0.9)
        self.assertEqual(result[1]["index"], 2)
        self.assertAlmostEqual(result[1]["score"], 0.5)

    # -- Cohere failure + no fallback_scores -> keyword overlap -----------

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_failure_no_fallback_uses_keyword_overlap(self, mock_get_client):
        """When fallback_scores is None, keyword overlap is used."""
        mock_get_client.side_effect = RuntimeError("API down")

        result = self._run(
            reranker.rerank_with_cohere(
                "machine learning",
                ["machine learning algorithms", "cooking recipes", "deep learning models"],
                top_n=3,
                fallback_scores=None,
            )
        )

        self.assertEqual(len(result), 3)
        # "machine learning" matches terms in doc0 ("machine learning algorithms")
        # and doc2 ("deep learning models"), but NOT doc1 ("cooking recipes")
        matched_indices = [r["index"] for r in result[:2]]
        self.assertIn(0, matched_indices)  # "machine learning algorithms"
        self.assertIn(2, matched_indices)  # "deep learning models"
        self.assertEqual(result[-1]["index"], 1)  # "cooking recipes" last

    # -- Cohere failure + mismatched fallback_scores length -> keyword ----

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_failure_mismatched_fallback_uses_keyword(self, mock_get_client):
        """When fallback_scores length != documents length, keyword overlap is used."""
        mock_get_client.side_effect = RuntimeError("API down")

        result = self._run(
            reranker.rerank_with_cohere(
                "machine learning",
                ["machine learning algorithms", "cooking recipes", "deep learning models"],
                top_n=3,
                fallback_scores=[0.5, 0.9],  # length mismatch
            )
        )

        self.assertEqual(len(result), 3)
        # Should have used keyword overlap, not the fallback scores
        # "machine learning" matches "machine learning" terms in docs,
        # so keyword overlap should give nonzero scores to matching docs
        self.assertGreater(result[0]["score"], 0)

    # -- Empty documents -------------------------------------------------

    def test_empty_documents_returns_empty(self):
        result = self._run(
            reranker.rerank_with_cohere(
                "query",
                [],
                top_n=5,
                fallback_scores=[],
            )
        )
        self.assertEqual(result, [])

    # -- Fallback scores with empty list and non-empty docs ---------------

    @patch.object(reranker, "_get_cohere_client")
    def test_cohere_failure_empty_fallback_list_uses_keyword(self, mock_get_client):
        """When fallback_scores is an empty list (falsy), keyword overlap is used."""
        mock_get_client.side_effect = RuntimeError("API down")

        result = self._run(
            reranker.rerank_with_cohere(
                "machine learning",
                ["doc0", "doc1"],
                top_n=2,
                fallback_scores=[],
            )
        )

        self.assertEqual(len(result), 2)

    # -- Fallback preserves RRF score ordering ----------------------------

    @patch.object(reranker, "_get_cohere_client")
    def test_fallback_preserves_rrf_ranking(self, mock_get_client):
        """Fallback scores maintain the RRF-based ranking when Cohere fails."""
        mock_get_client.side_effect = RuntimeError("API down")

        # Simulate RRF scores: doc2 has highest RRF score
        rrf_scores = [0.15, 0.35, 0.60, 0.10]
        result = self._run(
            reranker.rerank_with_cohere(
                "test query",
                ["doc0", "doc1", "doc2", "doc3"],
                top_n=4,
                fallback_scores=rrf_scores,
            )
        )

        # Order should be: idx=2 (0.60), idx=1 (0.35), idx=0 (0.15), idx=3 (0.10)
        self.assertEqual([r["index"] for r in result], [2, 1, 0, 3])
        self.assertEqual([r["score"] for r in result], [0.60, 0.35, 0.15, 0.10])


if __name__ == "__main__":
    unittest.main()
