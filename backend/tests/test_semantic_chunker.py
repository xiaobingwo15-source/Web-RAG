"""Tests for semantic chunking helpers."""
import pytest
from app.services.chunker import _split_into_sentences, _cosine_similarity


class TestSplitIntoSentences:
    def test_simple_sentences(self):
        text = "Hello world. This is a test. Third sentence."
        result = _split_into_sentences(text)
        assert result == ["Hello world.", "This is a test.", "Third sentence."]

    def test_newline_delimited(self):
        text = "First line.\nSecond line.\nThird line."
        result = _split_into_sentences(text)
        assert len(result) >= 2
        assert "First line." in result[0]

    def test_empty_string(self):
        assert _split_into_sentences("") == []

    def test_single_sentence(self):
        result = _split_into_sentences("Just one sentence here.")
        assert result == ["Just one sentence here."]

    def test_preserves_content(self):
        text = "The quick brown fox. Jumped over the lazy dog."
        result = _split_into_sentences(text)
        combined = " ".join(result)
        assert "quick brown fox" in combined
        assert "lazy dog" in combined

    def test_long_text_multiple_sentences(self):
        sentences = [f"Sentence number {i}." for i in range(20)]
        text = " ".join(sentences)
        result = _split_into_sentences(text)
        assert len(result) == 20


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_similar_vectors_high_score(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.9, 0.1]
        score = _cosine_similarity(a, b)
        assert score > 0.9


import asyncio
from app.services.chunker import semantic_chunk_text


class TestSemanticChunkText:
    def _mock_embed_fn(self):
        """Create a mock async embed function that returns fixed vectors.

        Returns vectors where consecutive sentences in the same topic are similar
        and vectors at topic boundaries are dissimilar.
        """
        # Topic A: [1,0,0]-like, Topic B: [0,1,0]-like
        # Cat vectors are similar but not identical (cosine ~0.81-0.88)
        # Physics vectors are similar but not identical
        # Cross-topic vectors are near-orthogonal (cosine ~0)
        topic_vectors = {
            "The cat sat on the mat.": [1.0, 0.0, 0.0],
            "It was a fluffy cat.": [0.8, 0.5, 0.3],
            "The cat liked to nap.": [0.6, 0.3, 0.7],
            "Quantum physics is complex.": [0.0, 1.0, 0.0],
            "Particles behave as waves.": [0.1, 0.8, 0.6],
            "The observer effect is real.": [0.0, 0.6, 0.8],
        }

        async def embed_fn(texts: list[str]) -> list[list[float]]:
            return [topic_vectors.get(t, [0.5, 0.5, 0.0]) for t in texts]

        return embed_fn

    def test_returns_list_of_strings(self):
        embed_fn = self._mock_embed_fn()
        text = "The cat sat on the mat. It was a fluffy cat."
        result = asyncio.run(
            semantic_chunk_text(text, embed_fn=embed_fn)
        )
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_topic_boundary_creates_split(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. The cat liked to nap. "
            "Quantum physics is complex. Particles behave as waves. The observer effect is real."
        )
        result = asyncio.run(
            semantic_chunk_text(text, embed_fn=embed_fn, threshold=0.5, min_chunk_size=0)
        )
        # Should split into at least 2 chunks at the topic boundary
        assert len(result) >= 2
        # Topic A content should be together
        combined_0 = result[0]
        assert "cat" in combined_0.lower()
        # Topic B content should be together
        assert any("quantum" in c.lower() or "particle" in c.lower() for c in result)

    def test_similar_text_stays_together(self):
        embed_fn = self._mock_embed_fn()
        text = "The cat sat on the mat. It was a fluffy cat. The cat liked to nap."
        result = asyncio.run(
            semantic_chunk_text(text, embed_fn=embed_fn, threshold=0.5)
        )
        # All cat sentences are similar — should stay as 1 chunk
        assert len(result) == 1

    def test_empty_text_returns_empty(self):
        async def embed_fn(texts):
            return [[0.0] * 3 for _ in texts]

        result = asyncio.run(
            semantic_chunk_text("", embed_fn=embed_fn)
        )
        assert result == []

    def test_single_sentence_returns_single_chunk(self):
        async def embed_fn(texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

        result = asyncio.run(
            semantic_chunk_text("Just one sentence.", embed_fn=embed_fn)
        )
        assert len(result) == 1
        assert "Just one sentence." in result[0]

    def test_low_threshold_merges_everything(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. "
            "Quantum physics is complex. Particles behave as waves."
        )
        result = asyncio.run(
            semantic_chunk_text(text, embed_fn=embed_fn, threshold=0.0)
        )
        # threshold=0.0 means everything merges
        assert len(result) == 1

    def test_high_threshold_splits_everything(self):
        embed_fn = self._mock_embed_fn()
        text = "The cat sat on the mat. It was a fluffy cat. The cat liked to nap."
        result = asyncio.run(
            semantic_chunk_text(text, embed_fn=embed_fn, threshold=0.99, min_chunk_size=0)
        )
        # Very high threshold should create many small chunks
        assert len(result) >= 2


from app.services.chunker import create_parent_child_chunks_semantic


class TestCreateParentChildChunksSemantic:
    def _mock_embed_fn(self):
        topic_vectors = {
            "The cat sat on the mat.": [1.0, 0.0, 0.0],
            "It was a fluffy cat.": [0.8, 0.5, 0.3],
            "The cat liked to nap.": [0.6, 0.3, 0.7],
            "Quantum physics is complex.": [0.0, 1.0, 0.0],
            "Particles behave as waves.": [0.0, 0.9, 0.1],
            "The observer effect is real.": [0.0, 1.0, 0.1],
        }

        async def embed_fn(texts):
            return [topic_vectors.get(t, [0.5, 0.5, 0.0]) for t in texts]

        return embed_fn

    def test_returns_parents_and_children(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. The cat liked to nap. "
            "Quantum physics is complex. Particles behave as waves. The observer effect is real."
        )
        result = asyncio.run(
            create_parent_child_chunks_semantic(text, embed_fn=embed_fn, threshold=0.5)
        )
        assert "parents" in result
        assert "children" in result
        assert len(result["parents"]) >= 1
        assert len(result["children"]) >= 1

    def test_children_reference_valid_parent_ids(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. "
            "Quantum physics is complex. Particles behave as waves."
        )
        result = asyncio.run(
            create_parent_child_chunks_semantic(text, embed_fn=embed_fn, threshold=0.5)
        )
        parent_ids = {p["id"] for p in result["parents"]}
        for child in result["children"]:
            assert child["parent_id"] in parent_ids

    def test_empty_text_returns_empty(self):
        async def embed_fn(texts):
            return [[0.0] * 3 for _ in texts]

        result = asyncio.run(
            create_parent_child_chunks_semantic("", embed_fn=embed_fn)
        )
        assert result == {"parents": [], "children": []}
