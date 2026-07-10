import unittest
from unittest.mock import AsyncMock, Mock

from app.services.groundedness import (
    GROUNDEDNESS_CHECK_PROMPT,
    GROUNDEDNESS_CHECK_PROMPT_WEB,
    GROUNDEDNESS_THRESHOLD,
    check_groundedness,
    check_groundedness_with_llm,
)
from app.services.agents import doc_rag_agent
from app.routers import chat


class GroundednessTests(unittest.TestCase):
    def test_shared_groundedness_scores_context_overlap(self):
        score = check_groundedness(
            "The verification passphrase is atlas-77.",
            ["The verification passphrase is atlas-77."],
        )

        self.assertGreaterEqual(score, GROUNDEDNESS_THRESHOLD)

    def test_doc_rag_agent_uses_shared_groundedness_symbols(self):
        self.assertIs(doc_rag_agent.check_groundedness, check_groundedness)
        self.assertEqual(doc_rag_agent.GROUNDEDNESS_THRESHOLD, GROUNDEDNESS_THRESHOLD)

    def test_chat_route_uses_shared_groundedness_symbols(self):
        self.assertIs(chat.check_groundedness, check_groundedness)
        self.assertEqual(chat.GROUNDEDNESS_THRESHOLD, GROUNDEDNESS_THRESHOLD)


class GroundednessLlmTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _client_with_response(content: str) -> Mock:
        response = Mock()
        response.choices = [Mock(message=Mock(content=content))]
        client = Mock()
        client.chat.completions.create = AsyncMock(return_value=response)
        return client

    async def test_standard_verifier_runs_for_low_overlap_answer(self):
        client = self._client_with_response("no")

        score, is_grounded = await check_groundedness_with_llm(
            "A paraphrased answer with different wording.",
            ["The reference states the same underlying fact."],
            client,
            "test-model",
        )

        self.assertEqual(score, 0.0)
        self.assertTrue(is_grounded)
        client.chat.completions.create.assert_awaited_once()
        messages = client.chat.completions.create.await_args.kwargs["messages"]
        self.assertEqual(messages[0]["content"], GROUNDEDNESS_CHECK_PROMPT)

    async def test_standard_verifier_flags_unsupported_answer(self):
        client = self._client_with_response("yes")

        _, is_grounded = await check_groundedness_with_llm(
            "An unsupported answer.",
            ["Unrelated reference context."],
            client,
            "test-model",
        )

        self.assertFalse(is_grounded)

    async def test_web_mode_uses_document_only_grounding_prompt(self):
        client = self._client_with_response("yes")

        _, is_grounded = await check_groundedness_with_llm(
            "A claim found only on the web.",
            ["[Document] Internal facts.", "[Web] The external claim."],
            client,
            "test-model",
            web_mode=True,
        )

        self.assertFalse(is_grounded)
        messages = client.chat.completions.create.await_args.kwargs["messages"]
        self.assertEqual(messages[0]["content"], GROUNDEDNESS_CHECK_PROMPT_WEB)

    async def test_verifier_error_falls_back_to_token_overlap(self):
        client = Mock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("provider unavailable"))

        grounded_score, grounded = await check_groundedness_with_llm(
            "The verification passphrase is atlas-77.",
            ["The verification passphrase is atlas-77."],
            client,
            "test-model",
        )
        unsupported_score, unsupported = await check_groundedness_with_llm(
            "An unsupported answer.",
            ["Unrelated reference context."],
            client,
            "test-model",
        )

        self.assertGreaterEqual(grounded_score, GROUNDEDNESS_THRESHOLD)
        self.assertTrue(grounded)
        self.assertLess(unsupported_score, GROUNDEDNESS_THRESHOLD)
        self.assertFalse(unsupported)


if __name__ == "__main__":
    unittest.main()
