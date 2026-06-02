import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.agents import doc_rag_agent


async def _fake_stream(*args, **kwargs):
    yield "The verification passphrase is atlas-77."


class RagAnswerQualityEvalTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_grounded_answer_contains_expected_fact_and_sources(self):
        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=Mock()),
            patch.object(doc_rag_agent, "rewrite_query", new=AsyncMock(return_value="verification passphrase")),
            patch.object(
                doc_rag_agent,
                "retrieve_context",
                new=AsyncMock(return_value={
                    "chunks": ["The verification passphrase is atlas-77."],
                    "sources": [{
                        "chunk_id": "chunk-a",
                        "document_id": "doc-a",
                        "filename": "eval-fixture.md",
                        "score": 0.99,
                        "snippet": "The verification passphrase is atlas-77.",
                        "retrieval_mode": "hybrid",
                        "content": "The verification passphrase is atlas-77.",
                    }],
                }),
            ),
            patch.object(doc_rag_agent, "generate_chat_response_stream", new=_fake_stream),
        ):
            events = [
                event
                async for event in doc_rag_agent.execute(
                    token="token",
                    user_id="user-a",
                    message="What is the verification passphrase?",
                    history=[],
                    retrieval_mode="hybrid",
                    target_user_id="admin-a",
                    tenant_id="tenant-a",
                )
            ]

        answer = "".join(event["content"] for event in events if event["type"] == "token")
        sources = [event for event in events if event["type"] == "sources"]

        self.assertIn("atlas-77", answer)
        self.assertEqual(sources[0]["sources"][0]["filename"], "eval-fixture.md")
        self.assertNotIn("content", sources[0]["sources"][0])


if __name__ == "__main__":
    unittest.main()
