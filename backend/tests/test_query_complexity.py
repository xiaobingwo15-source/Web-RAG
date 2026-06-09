"""Tests for classify_query_complexity in doc_rag_agent."""

import pytest
from app.services.agents.doc_rag_agent import classify_query_complexity


class TestClassifyQueryComplexity:
    """Validate each tier of the heuristic classifier."""

    # --- Simple factual (3) ---------------------------------------------------

    @pytest.mark.parametrize(
        "query",
        [
            "What is RAG?",
            "Who is the CEO?",
            "When was it released?",
            "Define embedding",
            "Meaning of token",
        ],
    )
    def test_simple_factual_returns_3(self, query: str) -> None:
        assert classify_query_complexity(query) == 3

    # --- Standard (5) ---------------------------------------------------------

    @pytest.mark.parametrize(
        "query",
        [
            "How does the retrieval pipeline work in this system?",
            "Explain the chunking strategy used for PDFs",
            "What are the main components of the RAG architecture?",
            "Tell me about the embedding model configuration",
        ],
    )
    def test_standard_returns_5(self, query: str) -> None:
        assert classify_query_complexity(query) == 5

    # --- Comparative / complex (8) --------------------------------------------

    @pytest.mark.parametrize(
        "query",
        [
            "Compare Qdrant and Pinecone for vector storage",
            "What is the difference between hybrid and semantic search?",
            "RAG vs fine-tuning: which is better?",
            "What are the pros and cons of using Gemini embeddings?",
            "What are the advantages and disadvantages of chunk overlap?",
            "Contrast the two retrieval strategies",
            "Distinguish between FTS and vector search",
        ],
    )
    def test_comparative_returns_8(self, query: str) -> None:
        assert classify_query_complexity(query) == 8

    def test_multiple_question_marks_returns_8(self) -> None:
        assert classify_query_complexity("What is RAG? How does it work?") == 8

    def test_and_connecting_questions_returns_8(self) -> None:
        assert classify_query_complexity("What is RAG and how does it improve search?") == 8

    # --- Multi-context (10) ---------------------------------------------------

    @pytest.mark.parametrize(
        "query",
        [
            "List all the retrieval modes available in the system",
            "Summarize all the benefits of the RAG pipeline",
            "Give me an overview of the document ingestion process",
            "Provide a comprehensive list of all supported file types",
        ],
    )
    def test_multi_context_returns_10(self, query: str) -> None:
        assert classify_query_complexity(query) == 10

    def test_very_long_query_returns_10(self) -> None:
        long_query = "I need detailed information about " * 10  # > 150 chars
        assert classify_query_complexity(long_query) == 10

    # --- Edge cases -----------------------------------------------------------

    def test_empty_string_returns_5(self) -> None:
        assert classify_query_complexity("") == 5

    def test_whitespace_only_returns_5(self) -> None:
        assert classify_query_complexity("   ") == 5

    def test_single_word_returns_5(self) -> None:
        # Short but not a question word → standard
        assert classify_query_complexity("embeddings") == 5

    def test_short_non_question_returns_5(self) -> None:
        assert classify_query_complexity("chunking overlap") == 5
