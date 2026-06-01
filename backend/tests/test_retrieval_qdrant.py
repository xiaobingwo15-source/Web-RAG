import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services import retrieval


class RetrievalQdrantThresholdTests(unittest.IsolatedAsyncioTestCase):
    async def test_hybrid_retrieval_uses_low_vector_similarity_threshold(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(retrieval, "search_similar_chunks", new=AsyncMock(return_value=[])) as search,
        ):
            await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the verification passphrase?",
                mode="hybrid",
            )

        search.assert_awaited_once()
        self.assertEqual(search.await_args.kwargs["similarity_threshold"], 0.1)

    async def test_vector_retrieval_uses_low_vector_similarity_threshold(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(retrieval, "search_similar_chunks", new=AsyncMock(return_value=[])) as search,
        ):
            await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the verification passphrase?",
                mode="vector",
            )

        search.assert_awaited_once()
        self.assertEqual(search.await_args.kwargs["similarity_threshold"], 0.1)


if __name__ == "__main__":
    unittest.main()
