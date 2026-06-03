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
