import unittest
from unittest.mock import patch, call

from app.services import rag_quality_loop


class RagQualityLoopTests(unittest.TestCase):
    def test_sync_promotes_feedback_and_fallback_groups_to_drafts(self):
        created_payloads = []

        def create_case(tenant_id, payload):
            created_payloads.append(payload)
            return {
                "id": f"case-{len(created_payloads)}",
                "tenant_id": tenant_id,
                **payload,
            }

        feedback_item = {
            "feedback_id": "feedback-1",
            "feedback_created_at": "2026-06-12T00:10:00Z",
            "feedback_comment": "Wrong source",
            "rating": -1,
            "thread_id": "thread-1",
            "thread_title": "Benefits policy",
            "client_email": "client@example.com",
            "question": "What is the PTO rollover limit?",
            "question_message_id": "question-1",
            "resolved_message_id": "answer-1",
            "answer": "The old answer.",
            "answer_created_at": "2026-06-12T00:09:00Z",
            "retrieval_logs": [{
                "id": "log-feedback",
                "query": "What is the PTO rollover limit?",
                "retrieval_mode": "hybrid",
                "chunk_count": 1,
                "source_count": 1,
                "top_score": 0.31,
                "created_at": "2026-06-12T00:08:00Z",
                "retrieval_quality": "weak_sources",
                "diagnostics": {"channel": "chat"},
                "sources": [{
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "filename": "benefits.md",
                    "score": 0.31,
                    "score_family": "cohere_rerank",
                    "snippet": "Rollover details",
                }],
            }],
            "summary": {"source_count": 1, "top_score": 0.31},
        }
        fallback_logs = [
            {
                "id": "fallback-1",
                "query": "Where is the escalation policy?",
                "retrieval_mode": "hybrid",
                "chunk_count": 0,
                "source_count": 0,
                "top_score": None,
                "created_at": "2026-06-12T00:11:00Z",
                "retrieval_quality": "no_sources_web_fallback",
                "diagnostics": {"fallback_reason": "no_sources", "web_result_count": 3},
                "sources": [],
                "chunks": [],
            },
            {
                "id": "fallback-2",
                "query": "where is the escalation policy? ",
                "retrieval_mode": "hybrid",
                "chunk_count": 1,
                "source_count": 1,
                "top_score": 0.22,
                "created_at": "2026-06-12T00:12:00Z",
                "retrieval_quality": "low_quality_web_fallback",
                "diagnostics": {"fallback_reason": "low_quality", "web_result_count": 2},
                "sources": [{
                    "filename": "ops.md",
                    "score": 0.22,
                    "score_family": "rrf_fallback",
                    "snippet": "Escalation",
                }],
                "chunks": ["Escalation"],
            },
        ]

        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[feedback_item]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=fallback_logs),
            patch.object(rag_quality_loop.database, "create_rag_eval_case", side_effect=create_case),
            patch.object(rag_quality_loop.database, "update_rag_eval_case", return_value=None),
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        self.assertEqual(result["created_count"], 2)
        feedback_payload = created_payloads[0]
        fallback_payload = created_payloads[1]
        self.assertEqual(feedback_payload["status"], "draft")
        self.assertFalse(feedback_payload["enabled"])
        self.assertEqual(feedback_payload["source_type"], "thumbs_down_feedback")
        self.assertEqual(feedback_payload["source_ref_id"], "feedback-1")
        self.assertEqual(
            feedback_payload["retrieval_metadata"]["retrieval"]["logs"][0]["diagnostics"]["channel"],
            "chat",
        )
        self.assertEqual(
            feedback_payload["retrieval_metadata"]["retrieval"]["logs"][0]["sources"][0]["score_family"],
            "cohere_rerank",
        )
        self.assertEqual(fallback_payload["source_type"], "fallback_retrieval")
        self.assertTrue(fallback_payload["source_ref_id"].startswith("fallback:"))
        self.assertEqual(fallback_payload["retrieval_metadata"]["fallback"]["fallback_count"], 2)
        self.assertEqual(
            fallback_payload["retrieval_metadata"]["retrieval"]["logs"][0]["sources"][0]["score_family"],
            "rrf_fallback",
        )
        self.assertIn("fallback-heavy", fallback_payload["tags"])

    def test_sync_skips_existing_quality_loop_sources(self):
        feedback_item = {
            "feedback_id": "feedback-1",
            "thread_title": "Existing",
            "question": "Existing question?",
            "retrieval_logs": [],
        }

        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[{
                "source_type": "thumbs_down_feedback",
                "source_ref_id": "feedback-1",
            }]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[feedback_item]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=[]),
            patch.object(rag_quality_loop.database, "create_rag_eval_case") as create_case,
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        create_case.assert_not_called()
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["skipped_existing_count"], 1)

    def test_quality_gate_skips_similar_query(self):
        """Cases with a normalized query matching an existing case are skipped."""
        feedback_item = {
            "feedback_id": "feedback-dup",
            "question": "What is the PTO policy?",
            "thread_title": "PTO",
            "retrieval_logs": [],
        }

        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[{
                "id": "existing-case-1",
                "source_type": "manual",
                "source_ref_id": "manual-1",
                "question": "What is the PTO policy?",
            }]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[feedback_item]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=[]),
            patch.object(rag_quality_loop.database, "create_rag_eval_case") as create_case,
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        create_case.assert_not_called()
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["skipped_similar_count"], 1)

    def test_auto_promotes_fallback_case_with_2_plus_signals(self):
        """Fallback groups with >= 2 events are auto-promoted to active."""
        created_payloads = []
        updated_cases = []

        def create_case(tenant_id, payload):
            created_payloads.append(payload)
            return {
                "id": f"case-{len(created_payloads)}",
                "tenant_id": tenant_id,
                **payload,
            }

        def update_case(tenant_id, case_id, payload):
            updated_cases.append({"tenant_id": tenant_id, "case_id": case_id, **payload})
            return {"id": case_id, **payload}

        fallback_logs = [
            {
                "id": "fb-1",
                "query": "What is the safety protocol?",
                "retrieval_mode": "hybrid",
                "chunk_count": 0,
                "source_count": 0,
                "top_score": None,
                "created_at": "2026-06-12T00:11:00Z",
                "retrieval_quality": "no_sources_web_fallback",
                "diagnostics": {"fallback_reason": "no_sources", "web_result_count": 3},
                "sources": [],
                "chunks": [],
            },
            {
                "id": "fb-2",
                "query": "What is the safety protocol?",
                "retrieval_mode": "hybrid",
                "chunk_count": 0,
                "source_count": 0,
                "top_score": None,
                "created_at": "2026-06-12T00:12:00Z",
                "retrieval_quality": "no_sources_web_fallback",
                "diagnostics": {"fallback_reason": "no_sources", "web_result_count": 2},
                "sources": [],
                "chunks": [],
            },
        ]

        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=fallback_logs),
            patch.object(rag_quality_loop.database, "create_rag_eval_case", side_effect=create_case),
            patch.object(rag_quality_loop.database, "update_rag_eval_case", side_effect=update_case),
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(result["created"][0]["status"], "draft")
        self.assertEqual(len(updated_cases), 1)
        self.assertTrue(updated_cases[0]["enabled"])
        self.assertEqual(updated_cases[0]["status"], "active")

    def test_single_feedback_not_auto_promoted(self):
        """Single thumbs-down feedback (1 signal) stays as draft, not promoted."""
        created_payloads = []

        def create_case(tenant_id, payload):
            created_payloads.append(payload)
            return {
                "id": f"case-{len(created_payloads)}",
                "tenant_id": tenant_id,
                **payload,
            }

        feedback_item = {
            "feedback_id": "feedback-single",
            "question": "What are the holiday hours?",
            "thread_title": "Hours",
            "retrieval_logs": [],
        }

        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[feedback_item]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=[]),
            patch.object(rag_quality_loop.database, "create_rag_eval_case", side_effect=create_case),
            patch.object(rag_quality_loop.database, "update_rag_eval_case") as update_case,
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["promoted_count"], 0)
        self.assertEqual(created_payloads[0]["status"], "draft")
        self.assertFalse(created_payloads[0]["enabled"])
        update_case.assert_not_called()

    def test_result_includes_new_fields(self):
        """Return dict includes promoted_count and skipped_similar_count."""
        with (
            patch.object(rag_quality_loop.database, "list_rag_eval_cases", return_value=[]),
            patch.object(rag_quality_loop.database, "list_rag_quality_thumbs_down", return_value=[]),
            patch.object(rag_quality_loop.database, "list_recent_retrieval_logs", return_value=[]),
        ):
            result = rag_quality_loop.sync_quality_loop_eval_drafts("tenant-1")

        self.assertIn("promoted_count", result)
        self.assertIn("skipped_similar_count", result)
        self.assertEqual(result["promoted_count"], 0)
        self.assertEqual(result["skipped_similar_count"], 0)

    def test_count_negative_signals_thumbs_down(self):
        payload = {"source_type": "thumbs_down_feedback", "retrieval_metadata": {}}
        self.assertEqual(rag_quality_loop._count_negative_signals(payload), 1)

    def test_count_negative_signals_fallback(self):
        payload = {
            "source_type": "fallback_retrieval",
            "retrieval_metadata": {"fallback": {"fallback_count": 3}},
        }
        self.assertEqual(rag_quality_loop._count_negative_signals(payload), 3)

    def test_has_similar_case_exact_match(self):
        index = {"what is the pto policy?": "case-1"}
        self.assertTrue(rag_quality_loop._has_similar_case("what is the pto policy?", index))

    def test_has_similar_case_no_match(self):
        index = {"what is the pto policy?": "case-1"}
        self.assertFalse(rag_quality_loop._has_similar_case("what are the holiday hours?", index))

    def test_has_similar_case_empty_query(self):
        index = {"what is the pto policy?": "case-1"}
        self.assertFalse(rag_quality_loop._has_similar_case("", index))


if __name__ == "__main__":
    unittest.main()
