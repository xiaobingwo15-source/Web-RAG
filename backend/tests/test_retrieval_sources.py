import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services import retrieval
from app.services.semantic_cache import get_semantic_cache


class RetrievalSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_semantic_cache().clear()

    def tearDown(self):
        get_semantic_cache().clear()

    async def test_hybrid_retrieval_returns_public_source_metadata(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[
                    {
                        "id": "chunk-a",
                        "document_id": "doc-a",
                        "content": "The verification passphrase is atlas-77.",
                        "similarity": 0.8,
                    }
                ]),
            ),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "fixture.md", "status": "processed"}},
            ),
            patch.object(retrieval, "rerank_with_cohere", new=AsyncMock(return_value=[{"index": 0, "score": 0.99}])),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-a"}) as log_retrieval,
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the verification passphrase?",
                mode="hybrid",
            )

        self.assertEqual(result["chunks"], ["The verification passphrase is atlas-77."])
        self.assertEqual(result["retrieval_log_ids"], ["log-a"])
        self.assertNotIn("retrieval_log_id", result)
        self.assertEqual(result["sources"][0]["chunk_id"], "chunk-a")
        self.assertEqual(result["sources"][0]["document_id"], "doc-a")
        self.assertEqual(result["sources"][0]["filename"], "fixture.md")
        self.assertEqual(result["sources"][0]["retrieval_mode"], "hybrid")
        self.assertEqual(result["sources"][0]["score_family"], "cohere_rerank")
        self.assertIn("atlas-77", result["sources"][0]["snippet"])
        log_payload = log_retrieval.call_args.kwargs
        self.assertEqual(log_payload["chunks"], ["The verification passphrase is atlas-77."])
        self.assertIn("atlas-77", log_payload["sources"][0]["content"])
        self.assertEqual(log_payload["sources"][0]["score_family"], "cohere_rerank")
        self.assertEqual(log_payload["diagnostics"]["score_family"], "cohere_rerank")
        self.assertEqual(log_payload["diagnostics"]["channel"], "authenticated")
        self.assertIn("stage_timings_ms", log_payload["diagnostics"])
        self.assertIn("top_fused_score", log_payload["diagnostics"])

    async def test_hybrid_retrieval_logs_rrf_fallback_score_family(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[
                    {
                        "id": "chunk-a",
                        "document_id": "doc-a",
                        "content": "The fallback-ranked passphrase is atlas-77.",
                        "similarity": 0.8,
                    }
                ]),
            ),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "fixture.md", "status": "processed"}},
            ),
            patch.object(
                retrieval,
                "rerank_with_cohere",
                new=AsyncMock(return_value=[{"index": 0, "score": 0.02, "fallback": True}]),
            ),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-a"}) as log_retrieval,
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the fallback-ranked passphrase?",
                mode="hybrid",
                diagnostics={"channel": "widget"},
            )

        self.assertEqual(result["sources"][0]["score_family"], "rrf_fallback")
        log_payload = log_retrieval.call_args.kwargs
        self.assertEqual(log_payload["sources"][0]["score_family"], "rrf_fallback")
        self.assertEqual(log_payload["diagnostics"]["score_family"], "rrf_fallback")
        self.assertEqual(log_payload["diagnostics"]["channel"], "widget")

    def test_loggable_retrieval_evidence_is_bounded(self):
        long_text = "x" * 2500
        sources = [
            {
                "document_id": f"doc-{i}",
                "chunk_id": f"chunk-{i}",
                "filename": "fixture.md",
                "score": 0.9,
                "snippet": long_text,
                "content": long_text,
                "retrieval_mode": "hybrid",
                "score_family": "cohere_rerank",
                "ignored": "not persisted",
            }
            for i in range(12)
        ]
        chunks = [long_text for _ in range(12)]

        log_sources, log_chunks = retrieval._loggable_retrieval_evidence(sources, chunks)

        self.assertEqual(len(log_sources), 10)
        self.assertEqual(len(log_chunks), 10)
        self.assertLessEqual(len(log_sources[0]["content"]), 2000)
        self.assertLessEqual(len(log_sources[0]["snippet"]), 2000)
        self.assertLessEqual(len(log_chunks[0]), 2000)
        self.assertEqual(log_sources[0]["score_family"], "cohere_rerank")
        self.assertNotIn("ignored", log_sources[0])

    async def test_archived_documents_are_excluded_from_sources(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[
                    {
                        "id": "chunk-a",
                        "document_id": "doc-a",
                        "content": "Archived content",
                        "similarity": 0.8,
                    }
                ]),
            ),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "old.md", "status": "archived"}},
            ),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-archived"}),
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="Question",
                mode="vector",
            )

        self.assertEqual(result["chunks"], [])
        self.assertEqual(result["sources"], [])

    async def test_vector_retrieval_expands_child_hit_to_parent_source(self):
        parent_content = "## Page 1\n\nElectronics Technology Semester 1 Basic Electronics Chapter 1 Resistor Color Code."
        parent_metadata = {"pdf_parser": "pypdfium", "pdf_parser_planned": "unstructured"}

        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[
                    {
                        "id": "child-a",
                        "document_id": "doc-a",
                        "content": "Resistor Color Code",
                        "similarity": 0.8,
                        "metadata": {"pdf_parser": "pypdfium"},
                        "parent_id": "parent-a",
                    }
                ]),
            ),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "problem.pdf", "status": "processed"}},
            ),
            patch.object(
                retrieval,
                "get_parent_chunks_by_ids",
                new=AsyncMock(return_value={
                    "parent-a": {
                        "content": parent_content,
                        "document_id": "doc-a",
                        "metadata": parent_metadata,
                    }
                }),
            ) as parents,
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-parent"}),
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What subject and chapter is this PDF about?",
                mode="vector",
            )

        parents.assert_awaited_once_with(["parent-a"])
        self.assertEqual(result["chunks"], [parent_content])
        self.assertEqual(result["sources"][0]["chunk_id"], "parent-a")
        self.assertEqual(result["sources"][0]["document_id"], "doc-a")
        self.assertEqual(result["sources"][0]["filename"], "problem.pdf")
        self.assertEqual(result["sources"][0]["retrieval_mode"], "vector")
        self.assertEqual(result["sources"][0]["score_family"], "vector_similarity")
        self.assertEqual(result["sources"][0]["metadata"], parent_metadata)
        self.assertIn("Electronics Technology", result["sources"][0]["snippet"])


if __name__ == "__main__":
    unittest.main()
