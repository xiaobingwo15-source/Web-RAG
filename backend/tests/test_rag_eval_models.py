import unittest
from pydantic import ValidationError

from app.models.rag_eval import RagEvalCaseCreate, RagEvalCaseUpdate


class RagEvalModelTests(unittest.TestCase):
    def test_expected_document_id_must_be_uuid_when_present(self):
        with self.assertRaises(ValidationError):
            RagEvalCaseCreate(
                question="What is the verification passphrase?",
                expected_facts=["atlas-77"],
                expected_document_id="55555",
            )

    def test_expected_document_id_accepts_uuid_string(self):
        case = RagEvalCaseCreate(
            question="What is the verification passphrase?",
            expected_facts=["atlas-77"],
            expected_document_id="550e8400-e29b-41d4-a716-446655440000",
        )

        self.assertEqual(
            case.model_dump(mode="json")["expected_document_id"],
            "550e8400-e29b-41d4-a716-446655440000",
        )

    def test_active_enabled_case_requires_expected_facts(self):
        with self.assertRaises(ValidationError):
            RagEvalCaseCreate(question="What should be covered?")

    def test_draft_case_can_wait_for_expected_facts(self):
        case = RagEvalCaseCreate(
            question="What should be covered?",
            status="draft",
            enabled=False,
            source_type="thumbs_down_feedback",
            source_ref_id="feedback-1",
        )

        self.assertEqual(case.status, "draft")
        self.assertEqual(case.expected_facts, [])

    def test_update_expected_document_id_must_be_uuid_when_present(self):
        with self.assertRaises(ValidationError):
            RagEvalCaseUpdate(expected_document_id="55555")

    def test_update_can_toggle_enabled_only(self):
        case = RagEvalCaseUpdate(enabled=False)

        self.assertEqual(case.model_dump(exclude_unset=True), {"enabled": False})


if __name__ == "__main__":
    unittest.main()
