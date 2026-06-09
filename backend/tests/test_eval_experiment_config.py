"""Tests for experiment tracking with parameter versioning in eval pipeline."""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.routers.eval import RunEvalRequest
from app.services.eval_pipeline import (
    EvalResult,
    EvalSuiteResult,
    EvalTestCase,
    MetricScore,
    save_eval_run,
)


class RunEvalRequestConfigTests(unittest.TestCase):
    """Test RunEvalRequest accepts and validates new config fields."""

    def test_request_with_defaults(self):
        """New config fields default to None/empty when not provided."""
        req = RunEvalRequest()
        self.assertIsNone(req.chunk_size)
        self.assertIsNone(req.top_k)
        self.assertIsNone(req.reranker_model)
        self.assertIsNone(req.embedding_model)
        self.assertEqual(req.notes, "")

    def test_request_with_all_config_fields(self):
        """All config fields can be set explicitly."""
        req = RunEvalRequest(
            retrieval_mode="vector",
            chunk_size=500,
            top_k=10,
            reranker_model="rerank-v3.5",
            embedding_model="gemini-embedding-001",
            notes="Testing smaller chunks",
        )
        self.assertEqual(req.chunk_size, 500)
        self.assertEqual(req.top_k, 10)
        self.assertEqual(req.reranker_model, "rerank-v3.5")
        self.assertEqual(req.embedding_model, "gemini-embedding-001")
        self.assertEqual(req.notes, "Testing smaller chunks")

    def test_chunk_size_must_be_at_least_100(self):
        with self.assertRaises(ValidationError):
            RunEvalRequest(chunk_size=50)

    def test_chunk_size_must_be_at_most_5000(self):
        with self.assertRaises(ValidationError):
            RunEvalRequest(chunk_size=10000)

    def test_top_k_must_be_at_least_1(self):
        with self.assertRaises(ValidationError):
            RunEvalRequest(top_k=0)

    def test_top_k_must_be_at_most_50(self):
        with self.assertRaises(ValidationError):
            RunEvalRequest(top_k=100)

    def test_notes_max_length(self):
        with self.assertRaises(ValidationError):
            RunEvalRequest(notes="x" * 1001)

    def test_notes_within_limit(self):
        req = RunEvalRequest(notes="x" * 1000)
        self.assertEqual(len(req.notes), 1000)


class EvalSuiteResultConfigTests(unittest.TestCase):
    """Test EvalSuiteResult carries config_json and includes it in serialization."""

    def test_config_json_defaults_to_empty_dict(self):
        suite = EvalSuiteResult()
        self.assertEqual(suite.config_json, {})

    def test_config_json_preserved(self):
        config = {"retrieval_mode": "hybrid", "chunk_size": 500, "top_k": 10}
        suite = EvalSuiteResult(config_json=config)
        self.assertEqual(suite.config_json, config)

    def test_to_dict_includes_config(self):
        config = {"retrieval_mode": "vector", "chunk_size": 800}
        suite = EvalSuiteResult(
            total_cases=1,
            avg_faithfulness=4.0,
            avg_answer_relevance=4.0,
            avg_context_precision=4.0,
            avg_context_recall=4.0,
            avg_overall=4.0,
            config_json=config,
        )
        d = suite.to_dict()
        self.assertIn("config", d)
        self.assertEqual(d["config"], config)

    def test_to_dict_config_defaults_to_empty(self):
        suite = EvalSuiteResult()
        d = suite.to_dict()
        self.assertEqual(d["config"], {})


class SaveEvalRunConfigTests(unittest.TestCase):
    """Test save_eval_run persists config_json to the database."""

    @patch("app.services.eval_pipeline.get_db")
    def test_save_eval_run_includes_config_json(self, mock_get_db):
        """config_json from suite_result is included in the insert payload."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Set up the chain: db.table().insert().execute() returns data
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "run-1"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_execute
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_db.table.return_value = mock_table

        config = {
            "retrieval_mode": "hybrid",
            "chunk_size": 500,
            "top_k": 10,
            "reranker_model": "rerank-v3.5",
            "embedding_model": "gemini-embedding-001",
            "notes": "Test run",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        suite = EvalSuiteResult(
            total_cases=2,
            avg_faithfulness=4.0,
            avg_answer_relevance=3.5,
            avg_context_precision=4.5,
            avg_context_recall=3.0,
            avg_overall=3.75,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            config_json=config,
        )

        save_eval_run("tenant-1", suite, "testset-1")

        # Verify the insert was called with config_json
        call_args = mock_table.insert.call_args[0][0]
        self.assertIn("config_json", call_args)
        self.assertEqual(call_args["config_json"], config)
        self.assertEqual(call_args["tenant_id"], "tenant-1")
        self.assertEqual(call_args["test_set_id"], "testset-1")

    @patch("app.services.eval_pipeline.get_db")
    def test_save_eval_run_omits_config_when_empty(self, mock_get_db):
        """config_json is not included in insert when empty (backward compat)."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_execute = MagicMock()
        mock_execute.data = [{"id": "run-2"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_execute
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_db.table.return_value = mock_table

        suite = EvalSuiteResult(
            total_cases=1,
            avg_faithfulness=4.0,
            avg_answer_relevance=4.0,
            avg_context_precision=4.0,
            avg_context_recall=4.0,
            avg_overall=4.0,
            config_json={},
        )

        save_eval_run("tenant-1", suite)

        call_args = mock_table.insert.call_args[0][0]
        self.assertNotIn("config_json", call_args)

    @patch("app.services.eval_pipeline.get_db")
    def test_save_eval_run_includes_results_json_with_config(self, mock_get_db):
        """Both results_json and config_json are present in the saved record."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_execute = MagicMock()
        mock_execute.data = [{"id": "run-3"}]
        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_execute
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_db.table.return_value = mock_table

        result = EvalResult(
            question="What is X?",
            expected_answer="X is Y",
            actual_answer="X is Y",
            contexts=["chunk1"],
            faithfulness=MetricScore("faithfulness", 5, "perfect"),
            answer_relevance=MetricScore("answer_relevance", 5, "relevant"),
            context_precision=MetricScore("context_precision", 5, "precise"),
            context_recall=MetricScore("context_recall", 5, "full recall"),
        )

        config = {"retrieval_mode": "hybrid", "chunk_size": 500}
        suite = EvalSuiteResult(
            total_cases=1,
            avg_faithfulness=5.0,
            avg_answer_relevance=5.0,
            avg_context_precision=5.0,
            avg_context_recall=5.0,
            avg_overall=5.0,
            results=[result],
            config_json=config,
        )

        save_eval_run("tenant-1", suite)

        call_args = mock_table.insert.call_args[0][0]
        self.assertIn("config_json", call_args)
        self.assertEqual(call_args["config_json"], config)
        self.assertEqual(len(call_args["results_json"]), 1)
        self.assertEqual(call_args["results_json"][0]["question"], "What is X?")


class ConfigBuildingTests(unittest.TestCase):
    """Test the config dict construction logic (mirrors eval.py endpoint)."""

    def _build_config(self, request, settings):
        """Mirror the config-building logic from the eval endpoint."""
        return {
            "retrieval_mode": request.retrieval_mode,
            "chunk_size": request.chunk_size if request.chunk_size is not None else settings.child_chunk_size,
            "top_k": request.top_k if request.top_k is not None else 5,
            "reranker_model": request.reranker_model or "rerank-v3.5",
            "embedding_model": request.embedding_model or settings.embedding_model,
            "notes": request.notes,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def test_config_uses_request_values_when_provided(self):
        """Explicit request values override defaults."""
        req = RunEvalRequest(
            retrieval_mode="vector",
            chunk_size=500,
            top_k=10,
            reranker_model="custom-reranker",
            embedding_model="custom-embedder",
            notes="custom test",
        )
        settings = MagicMock()
        settings.child_chunk_size = 1500
        settings.embedding_model = "gemini-embedding-001"

        config = self._build_config(req, settings)

        self.assertEqual(config["retrieval_mode"], "vector")
        self.assertEqual(config["chunk_size"], 500)
        self.assertEqual(config["top_k"], 10)
        self.assertEqual(config["reranker_model"], "custom-reranker")
        self.assertEqual(config["embedding_model"], "custom-embedder")
        self.assertEqual(config["notes"], "custom test")
        self.assertIn("timestamp", config)

    def test_config_falls_back_to_settings_defaults(self):
        """When request fields are None, falls back to Settings values."""
        req = RunEvalRequest(retrieval_mode="hybrid")
        settings = MagicMock()
        settings.child_chunk_size = 1500
        settings.embedding_model = "gemini-embedding-001"

        config = self._build_config(req, settings)

        self.assertEqual(config["retrieval_mode"], "hybrid")
        self.assertEqual(config["chunk_size"], 1500)  # from settings
        self.assertEqual(config["top_k"], 5)  # hardcoded default
        self.assertEqual(config["reranker_model"], "rerank-v3.5")  # hardcoded default
        self.assertEqual(config["embedding_model"], "gemini-embedding-001")  # from settings
        self.assertEqual(config["notes"], "")

    def test_config_has_required_keys(self):
        """Config dict always contains all required keys."""
        req = RunEvalRequest()
        settings = MagicMock()
        settings.child_chunk_size = 500
        settings.embedding_model = "gemini-embedding-001"

        config = self._build_config(req, settings)

        required_keys = {"retrieval_mode", "chunk_size", "top_k", "reranker_model", "embedding_model", "notes", "timestamp"}
        self.assertTrue(required_keys.issubset(set(config.keys())))


if __name__ == "__main__":
    unittest.main()
