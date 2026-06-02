import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services import rag_eval


class RagEvalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_rag_eval_creates_run_and_result_rows(self):
        case = {
            "id": "case-a",
            "question": "What is the verification passphrase?",
            "expected_facts": ["atlas-77"],
        }
        inserted_results = []

        def insert_result(**kwargs):
            inserted = {
                "id": "result-a",
                "tenant_id": kwargs["tenant_id"],
                "run_id": kwargs["run_id"],
                "case_id": kwargs["case"]["id"],
                "question": kwargs["case"]["question"],
                "expected_facts": kwargs["case"]["expected_facts"],
                "answer": kwargs["answer"],
                "sources": kwargs["sources"],
                "context_relevance_score": kwargs["score"].context_relevance_score,
                "groundedness_score": kwargs["score"].groundedness_score,
                "answer_relevance_score": kwargs["score"].answer_relevance_score,
                "passed": kwargs["score"].passed,
                "failure_reason": kwargs["score"].failure_reason,
                "created_at": "now",
            }
            inserted_results.append(inserted)
            return inserted

        with (
            patch.object(rag_eval.database, "get_or_create_default_eval_suite", return_value={"id": "suite-a"}),
            patch.object(rag_eval.database, "list_rag_eval_cases", return_value=[case]) as list_cases,
            patch.object(rag_eval.database, "create_rag_eval_run", return_value={
                "id": "run-a",
                "tenant_id": "tenant-a",
                "suite_id": "suite-a",
                "status": "running",
                "retrieval_mode": "hybrid",
                "model_provider": "mistral",
                "model_name": "mistral-large-latest",
                "total_cases": 1,
                "passed_cases": 0,
                "avg_context_relevance_score": 0,
                "avg_groundedness_score": 0,
                "avg_answer_relevance_score": 0,
                "created_at": "now",
            }) as create_run,
            patch.object(rag_eval.database, "insert_rag_eval_result", side_effect=insert_result) as insert_row,
            patch.object(rag_eval.database, "update_rag_eval_run", return_value={
                "id": "run-a",
                "tenant_id": "tenant-a",
                "suite_id": "suite-a",
                "status": "completed",
                "retrieval_mode": "hybrid",
                "model_provider": "mistral",
                "model_name": "mistral-large-latest",
                "total_cases": 1,
                "passed_cases": 1,
                "avg_context_relevance_score": 1,
                "avg_groundedness_score": 1,
                "avg_answer_relevance_score": 1,
                "created_at": "now",
            }) as update_run,
            patch.object(rag_eval, "get_model_provider", return_value="mistral"),
            patch.object(rag_eval, "get_primary_model", return_value="mistral-large-latest"),
            patch.object(rag_eval, "get_llm_client", return_value=Mock()),
            patch.object(rag_eval, "retrieve_context", new=AsyncMock(return_value={
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
            })),
            patch.object(rag_eval, "generate_chat_response", new=AsyncMock(return_value="The verification passphrase is atlas-77.")),
        ):
            detail = await rag_eval.run_rag_eval("tenant-a", "admin-a", "token-a", "hybrid")

        create_run.assert_called_once()
        list_cases.assert_called_once_with("tenant-a", enabled_only=True)
        insert_row.assert_called_once()
        update_run.assert_called()
        self.assertEqual(detail["run"]["status"], "completed")
        self.assertEqual(inserted_results[0]["tenant_id"], "tenant-a")
        self.assertTrue(inserted_results[0]["passed"])
        self.assertNotIn("content", inserted_results[0]["sources"][0])


if __name__ == "__main__":
    unittest.main()
