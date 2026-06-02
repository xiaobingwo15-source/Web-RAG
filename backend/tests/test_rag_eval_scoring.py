import unittest

from app.services.rag_eval import score_eval_case


class RagEvalScoringTests(unittest.TestCase):
    def test_scoring_passes_when_facts_and_sources_match(self):
        score = score_eval_case(
            question="What is the verification code?",
            expected_facts=["atlas-77"],
            answer="The verification code is atlas-77.",
            sources=[{"snippet": "The verification code is atlas-77."}],
        )

        self.assertTrue(score.passed)
        self.assertEqual(score.answer_relevance_score, 1.0)
        self.assertEqual(score.groundedness_score, 1.0)

    def test_scoring_fails_when_no_sources_return(self):
        score = score_eval_case(
            question="What is the verification code?",
            expected_facts=["atlas-77"],
            answer="The verification code is atlas-77.",
            sources=[],
        )

        self.assertFalse(score.passed)
        self.assertIn("no sources returned", score.failure_reason)

    def test_scoring_fails_when_answer_misses_expected_fact(self):
        score = score_eval_case(
            question="What is the verification code?",
            expected_facts=["atlas-77"],
            answer="The verification code is unknown.",
            sources=[{"snippet": "The verification code is atlas-77."}],
        )

        self.assertFalse(score.passed)
        self.assertIn("missing expected facts", score.failure_reason)

    def test_archived_sources_are_not_valid_for_grounding(self):
        score = score_eval_case(
            question="What is the verification code?",
            expected_facts=["atlas-77"],
            answer="The verification code is atlas-77.",
            sources=[{"snippet": "The verification code is atlas-77.", "status": "archived"}],
        )

        self.assertFalse(score.passed)
        self.assertIn("no sources returned", score.failure_reason)

    def test_expected_document_id_must_match_when_present(self):
        score = score_eval_case(
            question="What is the verification code?",
            expected_facts=["atlas-77"],
            answer="The verification code is atlas-77.",
            sources=[{"document_id": "doc-b", "snippet": "The verification code is atlas-77."}],
            expected_document_id="doc-a",
        )

        self.assertFalse(score.passed)
        self.assertIn("expected document was not retrieved", score.failure_reason)


if __name__ == "__main__":
    unittest.main()
