import unittest
from unittest.mock import AsyncMock, patch

from app.models.rag_quality import RagQualityRetrievalLog
from app.routers import admin
from app.services import rag_quality_policy
from app.services.agents import doc_rag_agent
from app.services.semantic_cache import clear_semantic_cache, get_semantic_cache


class RagQualityPolicyTests(unittest.TestCase):
    def test_builds_split_signals_from_retrieval_and_feedback_rows(self):
        retrieval_logs = [
            {
                "id": "zero-1",
                "query": "missing answer",
                "retrieval_mode": "hybrid",
                "source_count": 0,
                "chunk_count": 0,
                "top_score": None,
                "duration_ms": 120,
                "created_at": "2026-06-12T00:00:00Z",
                "thread_id": "thread-zero",
                "answer_message_id": "answer-zero",
                "diagnostics": {"channel": "widget", "score_family": "cohere_rerank"},
            },
            {
                "id": "weak-1",
                "query": "weak answer",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.2,
                "duration_ms": 3500,
                "created_at": "2026-06-12T00:01:00Z",
                "diagnostics": {
                    "channel": "authenticated",
                    "score_family": "cohere_rerank",
                    "stage_timings_ms": {"qdrant_ms": 100, "rerank_ms": 200, "total_ms": 3500},
                },
            },
            {
                "id": "ground-1",
                "query": "ungrounded answer",
                "retrieval_mode": "hybrid",
                "source_count": 2,
                "chunk_count": 2,
                "top_score": 0.8,
                "duration_ms": 140,
                "groundedness_flag": True,
                "created_at": "2026-06-12T00:02:00Z",
                "diagnostics": {"channel": "authenticated", "score_family": "cohere_rerank"},
            },
            {
                "id": "fallback-1",
                "query": "fallback answer",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.7,
                "duration_ms": 150,
                "retrieval_quality": "no_sources_web_fallback",
                "created_at": "2026-06-12T00:03:00Z",
                "diagnostics": {
                    "channel": "authenticated",
                    "score_family": "cohere_rerank",
                    "web_result_count": 3,
                    "used_web_fallback": True,
                    "fallback_reason": "no_doc_results",
                },
            },
        ]
        feedback_rows = [
            {"id": "fb-1", "rating": -1, "comment": "wrong", "created_at": "2026-06-12T01:00:00Z"},
            {"id": "fb-2", "rating": 1, "created_at": "2026-06-12T01:01:00Z"},
        ]

        result = rag_quality_policy.build_rag_quality_signals(
            retrieval_logs=retrieval_logs,
            feedback_rows=feedback_rows,
            window_hours=168,
            limit=50,
        )

        signals = {signal["id"]: signal for signal in result["signals"]}
        expected_base = {
            "zero_sources",
            "weak_sources",
            "groundedness",
            "completion_latency",
            "negative_feedback",
            "web_fallback",
            "widget_policy_violation",
            "data_staleness",
        }
        self.assertTrue(expected_base.issubset(set(signals)), f"Missing base signals: {expected_base - set(signals)}")
        self.assertNotIn("feedback_fallback", signals)
        self.assertEqual(signals["zero_sources"]["count"], 1)
        self.assertEqual(signals["weak_sources"]["count"], 1)
        self.assertEqual(signals["groundedness"]["count"], 1)
        self.assertEqual(signals["completion_latency"]["value"], 3500)
        self.assertEqual(signals["negative_feedback"]["count"], 1)
        self.assertEqual(signals["web_fallback"]["count"], 1)
        self.assertEqual(signals["widget_policy_violation"]["count"], 0)
        self.assertEqual(result["totals"]["thumbs_down_count"], 1)
        self.assertEqual(result["totals"]["fallback_count"], 1)
        self.assertEqual(result["totals"]["channel_breakdown"]["widget"]["retrieval_count"], 1)
        self.assertEqual(result["totals"]["channel_breakdown"]["authenticated"]["retrieval_count"], 3)

        weak_example = signals["weak_sources"]["examples"][0]
        self.assertEqual(weak_example["details"]["channel"], "authenticated")
        self.assertEqual(weak_example["details"]["score_family"], "cohere_rerank")
        self.assertEqual(weak_example["details"]["stage_timings_ms"]["rerank_ms"], 200)

    def test_near_random_signal_detected(self):
        """Logs with top_score < 0.15 are flagged as near-random."""
        retrieval_logs = [
            {
                "id": f"nr-{i}",
                "query": f"near random query {i}",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.05,
                "duration_ms": 500,
                "created_at": f"2026-06-12T00:{i:02d}:00Z",
                "diagnostics": {"score_family": "cohere_rerank"},
            }
            for i in range(5)
        ]
        result = rag_quality_policy.build_rag_quality_signals(
            retrieval_logs=retrieval_logs,
            feedback_rows=[],
        )
        signals = {s["id"]: s for s in result["signals"]}
        self.assertIn("weak_sources", signals)
        self.assertEqual(result["totals"]["near_random_count"], 5)
        # Near-random count is mentioned in weak_sources description
        self.assertIn("Near-random", signals["weak_sources"]["description"])

    def test_rrf_fallback_uses_rrf_score_thresholds(self):
        retrieval_logs = [
            {
                "id": "rrf-ok",
                "query": "fallback score should not use rerank threshold",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.02,
                "duration_ms": 200,
                "created_at": "2026-06-12T00:00:00Z",
                "diagnostics": {"score_family": "rrf_fallback"},
            },
            {
                "id": "rrf-weak",
                "query": "fallback score below rrf threshold",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.012,
                "duration_ms": 200,
                "created_at": "2026-06-12T00:01:00Z",
                "diagnostics": {"score_family": "rrf_fallback"},
            },
            {
                "id": "fts-skip",
                "query": "fts scores are not normalized",
                "retrieval_mode": "fts",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.001,
                "duration_ms": 200,
                "created_at": "2026-06-12T00:02:00Z",
                "diagnostics": {"score_family": "fts_rank"},
            },
        ]

        result = rag_quality_policy.build_rag_quality_signals(
            retrieval_logs=retrieval_logs,
            feedback_rows=[],
        )

        signals = {s["id"]: s for s in result["signals"]}
        self.assertEqual(signals["weak_sources"]["count"], 1)
        self.assertEqual(signals["weak_sources"]["examples"][0]["id"], "rrf-weak")

    def test_widget_policy_violation_is_critical_when_widget_uses_web_fallback(self):
        retrieval_logs = [
            {
                "id": "widget-violation",
                "query": "public widget should not use web",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.8,
                "duration_ms": 200,
                "created_at": "2026-06-12T00:00:00Z",
                "diagnostics": {
                    "channel": "widget",
                    "score_family": "cohere_rerank",
                    "web_fallback_allowed": True,
                    "used_web_fallback": True,
                },
            }
        ]

        result = rag_quality_policy.build_rag_quality_signals(
            retrieval_logs=retrieval_logs,
            feedback_rows=[],
        )

        signals = {s["id"]: s for s in result["signals"]}
        self.assertEqual(signals["widget_policy_violation"]["status"], "critical")
        self.assertEqual(signals["widget_policy_violation"]["count"], 1)

    def test_staleness_signal_fires_on_score_degradation(self):
        """When recent scores drop significantly vs older scores, staleness signal fires."""
        # 20 logs: first 10 with score 0.8, last 10 with score 0.05
        retrieval_logs = []
        for i in range(10):
            retrieval_logs.append({
                "id": f"old-{i}",
                "query": f"old query {i}",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.8,
                "duration_ms": 500,
                "created_at": f"2026-06-01T00:{i:02d}:00Z",
                "diagnostics": {"score_family": "cohere_rerank"},
            })
        for i in range(10):
            retrieval_logs.append({
                "id": f"new-{i}",
                "query": f"new query {i}",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.05,
                "duration_ms": 500,
                "created_at": f"2026-06-12T00:{i:02d}:00Z",
                "diagnostics": {"score_family": "cohere_rerank"},
            })
        for i in range(20):
            retrieval_logs.append({
                "id": f"rrf-{i}",
                "query": f"rrf query {i}",
                "retrieval_mode": "hybrid",
                "source_count": 1,
                "chunk_count": 1,
                "top_score": 0.02,
                "duration_ms": 500,
                "created_at": f"2026-06-{1 + i // 10:02d}T01:{i % 10:02d}:00Z",
                "diagnostics": {"score_family": "rrf_fallback"},
            })
        result = rag_quality_policy.build_rag_quality_signals(
            retrieval_logs=retrieval_logs,
            feedback_rows=[],
        )
        signals = {s["id"]: s for s in result["signals"]}
        self.assertIn("data_staleness", signals)
        self.assertEqual(signals["data_staleness"]["status"], "critical")
        self.assertIn("staleness_ratio", result["totals"])
        self.assertEqual(result["totals"]["staleness_score_family"], "cohere_rerank")

    def test_retrieval_log_model_accepts_diagnostics(self):
        log = RagQualityRetrievalLog(
            id="log-1",
            query="q",
            retrieval_mode="hybrid",
            created_at="2026-06-12T00:00:00Z",
            diagnostics={"vector_result_count": 3},
        )

        self.assertEqual(log.diagnostics["vector_result_count"], 3)

    def test_clear_semantic_cache_removes_cached_retrievals(self):
        cache = get_semantic_cache()
        cache.clear()
        embedding = [1.0, 0.0, 0.0]
        cache.store(embedding, {"chunks": ["stale"], "sources": []}, namespace="test")
        self.assertIsNotNone(cache.lookup(embedding, namespace="test"))

        clear_semantic_cache("test")

        self.assertIsNone(cache.lookup(embedding, namespace="test"))


class RagQualityAdminEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_eval_cases_endpoint_syncs_quality_loop_drafts(self):
        class User:
            role = "admin"
            tenant_id = "tenant-1"
            status = "approved"

        cases = [{
            "id": "case-1",
            "tenant_id": "tenant-1",
            "question": "Draft question?",
            "expected_facts": [],
            "tags": ["quality-loop"],
            "enabled": False,
            "status": "draft",
            "created_at": "2026-06-12T00:00:00Z",
            "updated_at": "2026-06-12T00:00:00Z",
        }]
        with (
            patch.object(admin, "sync_quality_loop_eval_drafts", return_value={"created_count": 1}) as sync,
            patch.object(admin, "list_rag_eval_cases", return_value=cases) as list_cases,
        ):
            result = await admin.get_rag_eval_cases(user=User())

        sync.assert_called_once_with("tenant-1")
        list_cases.assert_called_once_with("tenant-1")
        self.assertEqual(result, cases)

    async def test_admin_signal_endpoint_uses_policy_service(self):
        class User:
            role = "admin"
            tenant_id = "tenant-1"
            status = "approved"

        payload = {"window_hours": 168, "limit": 50, "totals": {}, "signals": []}
        with patch.object(admin, "list_rag_quality_signals", return_value=payload) as mock:
            result = await admin.get_rag_quality_signals(window_hours=24, limit=10, user=User())

        self.assertEqual(result, payload)
        mock.assert_called_once_with("tenant-1", window_hours=24, limit=10)


class DocRagFallbackPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_sources_does_not_search_web_when_fallback_disabled(self):
        search_web = AsyncMock(return_value=[{"title": "web", "content": "web", "url": "https://example.com"}])
        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=object()),
            patch.object(doc_rag_agent, "rewrite_query", AsyncMock(return_value="Unknown?")),
            patch.object(doc_rag_agent, "expand_queries", AsyncMock(return_value=[])),
            patch.object(doc_rag_agent, "retrieve_context", AsyncMock(return_value={
                "chunks": [],
                "sources": [],
                "retrieval_log_ids": ["log-1"],
            })),
            patch.object(doc_rag_agent, "search_web", search_web),
            patch.object(doc_rag_agent, "_try_clarification", AsyncMock(return_value=None)),
            patch.object(doc_rag_agent, "_is_meta_query", AsyncMock(return_value=False)),
        ):
            events = [
                event async for event in doc_rag_agent.execute(
                    token="",
                    user_id="session-1",
                    message="Unknown?",
                    history=[],
                    tenant_id="tenant-1",
                    target_user_id="admin-1",
                    allow_web_fallback=False,
                )
            ]

        search_web.assert_not_awaited()
        quality_events = [event for event in events if event.get("type") == "rag_quality"]
        self.assertEqual(quality_events[-1]["retrieval_quality"], "no_sources")
        self.assertFalse(quality_events[-1]["diagnostics"]["web_fallback_allowed"])
        self.assertTrue(any(
            event.get("type") == "token" and "knowledge base" in event.get("content", "")
            for event in events
        ))

    async def test_low_sources_return_gap_when_fallback_disabled(self):
        search_web = AsyncMock(return_value=[])
        with (
            patch.object(doc_rag_agent, "get_llm_client", return_value=object()),
            patch.object(doc_rag_agent, "rewrite_query", AsyncMock(return_value="Unknown?")),
            patch.object(doc_rag_agent, "expand_queries", AsyncMock(return_value=[])),
            patch.object(doc_rag_agent, "retrieve_context", AsyncMock(return_value={
                "chunks": ["weak context"],
                "sources": [{"content": "weak context", "score": 0.1, "document_id": "doc-1"}],
                "retrieval_log_ids": ["log-1"],
            })),
            patch.object(doc_rag_agent, "search_web", search_web),
            patch.object(doc_rag_agent, "_try_clarification", AsyncMock(return_value=None)),
            patch.object(doc_rag_agent, "_is_meta_query", AsyncMock(return_value=False)),
        ):
            events = [
                event async for event in doc_rag_agent.execute(
                    token="",
                    user_id="session-1",
                    message="Unknown?",
                    history=[],
                    tenant_id="tenant-1",
                    target_user_id="admin-1",
                    allow_web_fallback=False,
                )
            ]

        search_web.assert_not_awaited()
        quality_events = [event for event in events if event.get("type") == "rag_quality"]
        self.assertEqual(quality_events[-1]["retrieval_quality"], "low_no_web")
        self.assertEqual(quality_events[-1]["diagnostics"]["fallback_reason"], "low_quality_no_web")


if __name__ == "__main__":
    unittest.main()
