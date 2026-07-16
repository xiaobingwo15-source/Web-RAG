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

    async def test_hybrid_cache_hit_skips_vector_search_and_reranking_but_logs_request(self):
        embedding = AsyncMock(return_value=[0.1, 0.2])
        fts_search = Mock(return_value=[])
        vector_search = AsyncMock(return_value=[{
            "id": "chunk-a",
            "document_id": "doc-a",
            "content": "The cached passphrase is atlas-77.",
            "similarity": 0.8,
        }])
        rerank = AsyncMock(return_value=[{"index": 0, "score": 0.99}])
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=embedding),
            patch.object(retrieval, "search_similar_chunks", new=vector_search),
            patch.object(retrieval, "search_chunks_fts", new=fts_search),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "fixture.md", "status": "processed"}},
            ),
            patch.object(retrieval, "rerank_with_cohere", new=rerank),
            patch.object(
                retrieval,
                "log_retrieval",
                side_effect=[{"id": "log-first"}, {"id": "log-cached"}],
            ) as log_retrieval,
        ):
            first = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the cached passphrase?",
                mode="hybrid",
            )
            cached = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="What is the cached passphrase?",
                mode="hybrid",
            )

        self.assertEqual(first["chunks"], cached["chunks"])
        self.assertEqual(cached["retrieval_log_ids"], ["log-cached"])
        embedding.assert_awaited_once()
        fts_search.assert_called_once()
        vector_search.assert_awaited_once()
        rerank.assert_awaited_once()
        self.assertEqual(log_retrieval.call_count, 2)
        cached_log = log_retrieval.call_args_list[1].kwargs
        self.assertTrue(cached_log["diagnostics"]["cache_hit"])

    async def test_hybrid_retrieval_abstains_when_all_reranker_scores_are_low(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[{
                    "id": "chunk-a",
                    "document_id": "doc-a",
                    "content": "Weakly related content.",
                    "similarity": 0.4,
                }]),
            ),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(retrieval, "rerank_with_cohere", new=AsyncMock(return_value=[{"index": 0, "score": 0.2}])),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-low"}) as log_retrieval,
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="A question with no strong match",
                mode="hybrid",
            )

        self.assertEqual(result["chunks"], [])
        self.assertEqual(result["sources"], [])
        diagnostics = log_retrieval.call_args.kwargs["diagnostics"]
        self.assertEqual(diagnostics["fallback_reason"], "all_chunks_filtered_by_rerank_threshold")
        self.assertEqual(diagnostics["score_family"], "cohere_rerank")

    async def test_hybrid_retrieval_caps_remote_rerank_candidates(self):
        vector_results = [
            {
                "id": f"chunk-{index}",
                "document_id": "doc-a",
                "content": f"Candidate document {index}",
                "similarity": 0.9 - index / 100,
            }
            for index in range(16)
        ]

        async def rerank(_query, documents, **_kwargs):
            self.assertEqual(len(documents), retrieval.MAX_RERANK_CANDIDATES)
            return [{"index": 0, "score": 0.99}]

        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(retrieval, "search_similar_chunks", new=AsyncMock(return_value=vector_results)),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(
                retrieval,
                "get_documents_by_ids",
                return_value={"doc-a": {"id": "doc-a", "filename": "fixture.md", "status": "processed"}},
            ),
            patch.object(retrieval, "rerank_with_cohere", new=rerank),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-capped"}),
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="Compare every relevant candidate",
                mode="hybrid",
                match_count=8,
            )

        self.assertEqual(len(result["sources"]), 1)

    async def test_hybrid_retrieval_abstains_from_weak_timeout_fallback(self):
        with (
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(
                retrieval,
                "search_similar_chunks",
                new=AsyncMock(return_value=[{
                    "id": "chunk-a",
                    "document_id": "doc-a",
                    "content": "Semantically weak fallback content.",
                    "similarity": 0.4,
                }]),
            ),
            patch.object(retrieval, "search_chunks_fts", return_value=[]),
            patch.object(
                retrieval,
                "rerank_with_cohere",
                new=AsyncMock(return_value=[{"index": 0, "score": 0.011, "fallback": True}]),
            ),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-fallback"}) as log_retrieval,
        ):
            result = await retrieval.retrieve_context(
                token="token",
                user_id="user-a",
                target_user_id="admin-a",
                tenant_id="tenant-a",
                message="Question during reranker timeout",
                mode="hybrid",
            )

        self.assertEqual(result["sources"], [])
        diagnostics = log_retrieval.call_args.kwargs["diagnostics"]
        self.assertEqual(diagnostics["fallback_reason"], "weak_local_rerank_fallback")

    async def test_client_without_explicit_target_searches_tenant_admin_knowledge_base(self):
        profile_response = Mock(data={"role": "client"})
        db = Mock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = profile_response
        vector_search = AsyncMock(return_value=[])

        with (
            patch("app.services.supabase.get_supabase_client_with_token", return_value=db),
            patch("app.services.database.get_tenant_admin_user_id", return_value="admin-a"),
            patch.object(retrieval, "get_embedding_client", return_value=Mock()),
            patch.object(retrieval, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])),
            patch.object(retrieval, "search_similar_chunks", new=vector_search),
            patch.object(retrieval, "log_retrieval", return_value={"id": "log-target"}),
        ):
            await retrieval.retrieve_context(
                token="token",
                user_id="client-a",
                tenant_id="tenant-a",
                message="Search the shared knowledge base",
                mode="vector",
            )

        vector_search.assert_awaited_once_with(
            "admin-a",
            [0.1, 0.2],
            5,
            similarity_threshold=retrieval.VECTOR_SIMILARITY_THRESHOLD,
            tenant_id="tenant-a",
        )

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
