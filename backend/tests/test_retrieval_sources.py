import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services import retrieval


class RetrievalSourceTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertIn("atlas-77", result["sources"][0]["snippet"])
        log_payload = log_retrieval.call_args.kwargs
        self.assertEqual(log_payload["chunks"], ["The verification passphrase is atlas-77."])
        self.assertIn("atlas-77", log_payload["sources"][0]["content"])

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


if __name__ == "__main__":
    unittest.main()
