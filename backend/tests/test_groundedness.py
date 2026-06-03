import unittest

from app.services.groundedness import GROUNDEDNESS_THRESHOLD, check_groundedness
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


if __name__ == "__main__":
    unittest.main()
