"""Tests for contextual retrieval (LLM-generated chunk prefixes)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.contextual_retrieval import (
    _format_chunks_for_prompt,
    _parse_context_sentences,
    _prepend_context_to_chunk,
    _generate_batch_context,
    add_contextual_prefixes,
)


# ---------------------------------------------------------------------------
# Tests for _format_chunks_for_prompt
# ---------------------------------------------------------------------------

class TestFormatChunksForPrompt:
    def test_single_chunk(self):
        result = _format_chunks_for_prompt(["Hello world"], max_chars=300)
        assert result == "1. Hello world"

    def test_multiple_chunks(self):
        chunks = ["First chunk", "Second chunk", "Third chunk"]
        result = _format_chunks_for_prompt(chunks)
        assert "1. First chunk" in result
        assert "2. Second chunk" in result
        assert "3. Third chunk" in result

    def test_truncation(self):
        long_text = "A" * 500
        result = _format_chunks_for_prompt([long_text], max_chars=100)
        # Should be truncated to 100 chars
        assert len(result) < 500
        assert result.startswith("1. " + "A" * 100)

    def test_empty_list(self):
        result = _format_chunks_for_prompt([])
        assert result == ""


# ---------------------------------------------------------------------------
# Tests for _parse_context_sentences
# ---------------------------------------------------------------------------

class TestParseContextSentences:
    def test_plain_sentences(self):
        raw = "This is about cats.\nThis is about dogs."
        result = _parse_context_sentences(raw, 2)
        assert result == ["This is about cats.", "This is about dogs."]

    def test_numbered_sentences(self):
        raw = "1. This is about cats.\n2. This is about dogs."
        result = _parse_context_sentences(raw, 2)
        assert result == ["This is about cats.", "This is about dogs."]

    def test_numbered_with_parenthesis(self):
        raw = "1) This is about cats.\n2) This is about dogs."
        result = _parse_context_sentences(raw, 2)
        assert result == ["This is about cats.", "This is about dogs."]

    def test_blank_lines_skipped(self):
        raw = "First line.\n\n\nSecond line."
        result = _parse_context_sentences(raw, 2)
        assert result == ["First line.", "Second line."]

    def test_pads_with_empty_when_too_few(self):
        raw = "Only one sentence."
        result = _parse_context_sentences(raw, 3)
        assert result == ["Only one sentence.", "", ""]

    def test_truncates_when_too_many(self):
        raw = "A.\nB.\nC.\nD."
        result = _parse_context_sentences(raw, 2)
        assert result == ["A.", "B."]

    def test_dash_prefix_stripped(self):
        raw = "- First item.\n- Second item."
        result = _parse_context_sentences(raw, 2)
        assert result == ["First item.", "Second item."]

    def test_empty_raw(self):
        result = _parse_context_sentences("", 3)
        assert result == ["", "", ""]


# ---------------------------------------------------------------------------
# Tests for _prepend_context_to_chunk
# ---------------------------------------------------------------------------

class TestPrependContextToChunk:
    def test_basic_prepend(self):
        result = _prepend_context_to_chunk("Original text.", "This chunk discusses cats")
        assert result == "This chunk discusses cats. Original text."

    def test_empty_context_returns_unchanged(self):
        result = _prepend_context_to_chunk("Original text.", "")
        assert result == "Original text."

    def test_context_already_ends_with_period(self):
        result = _prepend_context_to_chunk("Text.", "Context sentence.")
        # Should not double-period
        assert result == "Context sentence. Text."

    def test_context_without_period(self):
        result = _prepend_context_to_chunk("Text", "No period here")
        assert result == "No period here. Text"


# ---------------------------------------------------------------------------
# Tests for _generate_batch_context
# ---------------------------------------------------------------------------

class TestGenerateBatchContext:
    def test_success(self):
        mock_client = MagicMock()
        mock_response = "This chunk is about cats.\nThis chunk is about dogs."

        with patch("app.services.gemini.generate_chat_response", new_callable=AsyncMock, return_value=mock_response):
            result = asyncio.run(
                _generate_batch_context(mock_client, ["chunk1", "chunk2"], "Title", "Summary")
            )
            assert result == ["This chunk is about cats.", "This chunk is about dogs."]

    def test_llm_failure_returns_empty_strings(self):
        mock_client = MagicMock()

        with patch("app.services.gemini.generate_chat_response", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = asyncio.run(
                _generate_batch_context(mock_client, ["chunk1", "chunk2"], "Title", "Summary")
            )
            assert result == ["", ""]


# ---------------------------------------------------------------------------
# Tests for add_contextual_prefixes
# ---------------------------------------------------------------------------

class TestAddContextualPrefixes:
    def test_empty_children_returns_empty(self):
        result = asyncio.run(add_contextual_prefixes([]))
        assert result == []

    def test_disabled_flag_returns_unchanged(self):
        """When contextual_retrieval is disabled, children should be unchanged."""
        children = [{"text": "Original text", "parent_id": "p1", "id": "c1"}]

        with patch("app.services.contextual_retrieval.Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.get_contextual_retrieval_batch_size = 10
            mock_settings_cls.return_value = mock_settings

            with patch("app.services.contextual_retrieval.get_llm_client") as mock_client:
                # The function should not call the LLM if there are no chunks to process
                # But it will be called because we have 1 child. Let's mock it.
                with patch("app.services.contextual_retrieval._generate_batch_context", new_callable=AsyncMock, return_value=[""]):
                    result = asyncio.run(add_contextual_prefixes(children, doc_title="Title"))

        assert result[0]["text"] == "Original text"

    def test_context_prefix_prepended(self):
        children = [
            {"text": "Original text 1", "parent_id": "p1", "id": "c1"},
            {"text": "Original text 2", "parent_id": "p1", "id": "c2"},
        ]

        with patch("app.services.contextual_retrieval.get_llm_client") as mock_client:
            with patch("app.services.contextual_retrieval._generate_batch_context", new_callable=AsyncMock, return_value=["This chunk discusses topic A", "This chunk discusses topic B"]):
                result = asyncio.run(add_contextual_prefixes(children, doc_title="Title"))

        assert "This chunk discusses topic A. Original text 1" == result[0]["text"]
        assert "This chunk discusses topic B. Original text 2" == result[1]["text"]

    def test_partial_failure_keeps_unchanged_chunks(self):
        """If LLM returns empty for some chunks, those stay unchanged."""
        children = [
            {"text": "Text A", "parent_id": "p1", "id": "c1"},
            {"text": "Text B", "parent_id": "p1", "id": "c2"},
        ]

        with patch("app.services.contextual_retrieval.get_llm_client") as mock_client:
            with patch("app.services.contextual_retrieval._generate_batch_context", new_callable=AsyncMock, return_value=["Context for A", ""]):
                result = asyncio.run(add_contextual_prefixes(children, doc_title="Title"))

        assert "Context for A. Text A" == result[0]["text"]
        assert "Text B" == result[1]["text"]  # unchanged

    def test_batching_works(self):
        """Multiple batches are processed correctly."""
        children = [{"text": f"Chunk {i}", "parent_id": "p1", "id": f"c{i}"} for i in range(5)]

        batch_results = []

        async def mock_batch_context(client, chunks, doc_title, doc_summary):
            # Return a context sentence for each chunk in the batch
            return [f"Context for chunk" for _ in chunks]

        with patch("app.services.contextual_retrieval.get_llm_client") as mock_client:
            with patch("app.services.contextual_retrieval._generate_batch_context", side_effect=mock_batch_context):
                result = asyncio.run(add_contextual_prefixes(children, batch_size=2, doc_title="Title"))

        # All 5 chunks should have context prefixes
        for child in result:
            assert child["text"].startswith("Context for chunk.")

    def test_llm_error_returns_children_unchanged(self):
        """If the entire LLM call fails, children should be returned unchanged."""
        children = [{"text": "Original", "parent_id": "p1", "id": "c1"}]

        with patch("app.services.contextual_retrieval.get_llm_client") as mock_client:
            with patch("app.services.contextual_retrieval._generate_batch_context", new_callable=AsyncMock, side_effect=Exception("Total failure")):
                # The exception should propagate (caller handles it)
                with pytest.raises(Exception, match="Total failure"):
                    asyncio.run(add_contextual_prefixes(children, doc_title="Title"))
