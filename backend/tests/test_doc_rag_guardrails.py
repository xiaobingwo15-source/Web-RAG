import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.agents import doc_rag_agent


async def _answer_stream(*args, **kwargs):
    yield "The current Atlas status is available from the web result."


class DocRagGuardrailTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_document_results_use_web_fallback_when_allowed(self):
        search_web = AsyncMock(return_value=[{
            "title": "Current Atlas status",
            "content": "The current Atlas status is operational.",
            "url": "https://example.com/atlas",
        }])
        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=object()),
            patch.object(doc_rag_agent, "rewrite_query", new=AsyncMock(return_value="current Atlas status")),
            patch.object(doc_rag_agent, "expand_queries", new=AsyncMock(return_value=[])),
            patch.object(doc_rag_agent, "retrieve_context", new=AsyncMock(return_value={
                "chunks": [],
                "sources": [],
                "retrieval_log_ids": ["log-initial"],
            })),
            patch.object(doc_rag_agent, "_try_clarification", new=AsyncMock(return_value=None)),
            patch.object(doc_rag_agent, "_is_meta_query", new=AsyncMock(return_value=False)),
            patch.object(doc_rag_agent, "search_web", new=search_web),
            patch.object(doc_rag_agent, "generate_chat_response_stream", new=_answer_stream),
        ):
            events = [
                event
                async for event in doc_rag_agent.execute(
                    token="token",
                    user_id="user-a",
                    message="What is the current Atlas status?",
                    history=[],
                    target_user_id="admin-a",
                    tenant_id="tenant-a",
                    enable_hyde=False,
                    allow_web_fallback=True,
                )
            ]

        search_web.assert_awaited_once_with("current Atlas status", max_results=5)
        quality = [event for event in events if event.get("type") == "rag_quality"][-1]
        self.assertEqual(quality["retrieval_log_ids"], ["log-initial"])
        self.assertEqual(quality["retrieval_quality"], "no_sources_web_fallback")
        self.assertTrue(quality["diagnostics"]["web_fallback_allowed"])
        self.assertEqual(quality["diagnostics"]["web_result_count"], 1)

    async def test_ungrounded_retry_deduplicates_sources_and_aggregates_logs(self):
        source_a = {
            "chunk_id": "chunk-a",
            "document_id": "doc-a",
            "filename": "a.md",
            "content": "Atlas baseline context.",
            "score": 0.9,
        }
        source_b = {
            "chunk_id": "chunk-b",
            "document_id": "doc-b",
            "filename": "b.md",
            "content": "Atlas retry context.",
            "score": 0.85,
        }
        retrieve_context = AsyncMock(side_effect=[
            {
                "chunks": ["Atlas baseline context."],
                "sources": [source_a],
                "retrieval_log_ids": ["log-initial"],
            },
            {
                "chunks": ["Atlas baseline context.", "Atlas retry context."],
                "sources": [source_a, source_b],
                "retrieval_log_ids": ["log-retry"],
            },
        ])
        client = Mock()
        hyde_response = Mock()
        hyde_response.choices = [Mock(message=Mock(content=""))]
        client.chat.completions.create = AsyncMock(return_value=hyde_response)

        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=client),
            patch.object(doc_rag_agent, "rewrite_query", new=AsyncMock(return_value="Atlas question")),
            patch.object(doc_rag_agent, "expand_queries", new=AsyncMock(return_value=[])),
            patch.object(doc_rag_agent, "retrieve_context", new=retrieve_context),
            patch.object(doc_rag_agent, "_is_meta_query", new=AsyncMock(return_value=False)),
            patch.object(doc_rag_agent, "_refine_query_for_retry", new=AsyncMock(return_value="refined Atlas question")),
            patch.object(
                doc_rag_agent,
                "check_groundedness_with_llm",
                new=AsyncMock(side_effect=[(0.1, False), (0.1, False), (0.1, False)]),
            ),
            patch.object(doc_rag_agent, "generate_chat_response_stream", new=_answer_stream),
        ):
            events = [
                event
                async for event in doc_rag_agent.execute(
                    token="token",
                    user_id="user-a",
                    message="Explain Atlas",
                    history=[],
                    target_user_id="admin-a",
                    tenant_id="tenant-a",
                    enable_hyde=False,
                    allow_web_fallback=False,
                )
            ]

        source_events = [event for event in events if event.get("type") == "sources"]
        final_document_ids = [source["document_id"] for source in source_events[-1]["sources"]]
        self.assertEqual(final_document_ids, ["doc-a", "doc-b"])

        token_text = "".join(event.get("content", "") for event in events if event.get("type") == "token")
        self.assertIn("Parts of this answer may not be directly sourced", token_text)

        quality = [event for event in events if event.get("type") == "rag_quality"][-1]
        self.assertEqual(quality["retrieval_log_ids"], ["log-initial", "log-retry"])
        self.assertTrue(quality["groundedness_flag"])
        self.assertTrue(quality["retried"])

    async def test_failed_candidate_is_not_streamed_before_successful_retry(self):
        source = {
            "chunk_id": "chunk-a",
            "document_id": "doc-a",
            "filename": "a.md",
            "content": "Atlas is operational.",
            "score": 0.9,
        }
        retrieve_context = AsyncMock(side_effect=[
            {
                "chunks": ["Atlas is operational."],
                "sources": [source],
                "retrieval_log_ids": ["log-initial"],
            },
            {
                "chunks": ["Atlas is operational."],
                "sources": [source],
                "retrieval_log_ids": ["log-retry"],
            },
        ])
        answers = iter([
            ["Unsupported first draft."],
            ["Atlas is ", "operational."],
        ])

        async def answer_stream(*_args, **_kwargs):
            for chunk in next(answers):
                yield chunk

        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=Mock()),
            patch.object(doc_rag_agent, "rewrite_query", new=AsyncMock(return_value="Atlas status")),
            patch.object(doc_rag_agent, "expand_queries", new=AsyncMock(return_value=[])),
            patch.object(doc_rag_agent, "retrieve_context", new=retrieve_context),
            patch.object(doc_rag_agent, "_is_meta_query", new=AsyncMock(return_value=False)),
            patch.object(doc_rag_agent, "_refine_query_for_retry", new=AsyncMock(return_value="refined Atlas status")),
            patch.object(
                doc_rag_agent,
                "check_groundedness_with_llm",
                new=AsyncMock(side_effect=[(0.1, False), (0.95, True)]),
            ),
            patch.object(
                doc_rag_agent,
                "chain_of_verification",
                new=AsyncMock(return_value={
                    "verified": True,
                    "skipped": False,
                    "verification_questions": ["What is the Atlas status?"],
                    "verification_results": [],
                    "unsupported_claims": [],
                }),
            ),
            patch.object(doc_rag_agent, "generate_chat_response_stream", new=answer_stream),
        ):
            events = [
                event
                async for event in doc_rag_agent.execute(
                    token="token",
                    user_id="user-a",
                    message="What is the Atlas status?",
                    history=[],
                    target_user_id="admin-a",
                    tenant_id="tenant-a",
                    enable_hyde=False,
                    allow_web_fallback=False,
                )
            ]

        token_text = "".join(
            event.get("content", "")
            for event in events
            if event.get("type") == "token"
        )
        self.assertEqual(token_text, "Atlas is operational.")
        self.assertTrue(any(
            event.get("type") == "thought"
            and event.get("action_type") == "retrying"
            for event in events
        ))

        quality = [event for event in events if event.get("type") == "rag_quality"][-1]
        self.assertEqual(quality["groundedness"], 0.95)
        self.assertTrue(quality["retried"])


if __name__ == "__main__":
    unittest.main()
