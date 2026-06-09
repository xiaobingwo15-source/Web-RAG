"""Tests for load_golden_test_set() in eval_pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from app.services.eval_pipeline import EvalTestCase, load_golden_test_set


class LoadGoldenTestSetTests(unittest.TestCase):

    def _write_fixture(self, data: dict, path: Path) -> Path:
        """Write a JSON fixture to a temp file and return its path."""
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def test_load_valid_fixture(self):
        """Loading a well-formed fixture returns the correct EvalTestCase list."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 2,
            "test_cases": [
                {
                    "question": "What is X?",
                    "expected_answer": "X is Y.",
                    "context": "Some context about X.",
                    "tags": ["factual"],
                    "validated": True,
                },
                {
                    "question": "How does Z work?",
                    "expected_answer": "Z works by doing W.",
                    "context": "Details about Z.",
                    "tags": ["how-to"],
                    "validated": False,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], EvalTestCase)
        self.assertEqual(result[0].question, "What is X?")
        self.assertEqual(result[0].expected_answer, "X is Y.")
        self.assertEqual(result[0].context, "Some context about X.")
        self.assertEqual(result[0].tags, ["factual"])
        self.assertEqual(result[1].question, "How does Z work?")

    def test_load_with_missing_optional_fields(self):
        """Test cases without optional fields (context, tags) still load."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 1,
            "test_cases": [
                {
                    "question": "What is A?",
                    "expected_answer": "A is B.",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].context, "")
        self.assertEqual(result[0].tags, [])

    def test_load_skips_entries_missing_required_fields(self):
        """Entries missing question or expected_answer are skipped."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 3,
            "test_cases": [
                {"question": "Q1?", "expected_answer": "A1."},
                {"question": "Q2?"},  # missing expected_answer
                {"expected_answer": "A3."},  # missing question
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].question, "Q1?")

    def test_load_skips_non_dict_entries(self):
        """Non-dict entries in test_cases are skipped gracefully."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 2,
            "test_cases": [
                {"question": "Q1?", "expected_answer": "A1."},
                "not a dict",
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(len(result), 1)

    def test_load_raises_on_missing_file(self):
        """FileNotFoundError raised when the fixture file doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            load_golden_test_set("/nonexistent/path/golden_test_set.json")

    def test_load_raises_on_invalid_structure(self):
        """ValueError raised when JSON is not a dict with test_cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text('["not", "a", "dict"]', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_golden_test_set(path)

    def test_load_empty_test_cases(self):
        """Loading a fixture with zero test cases returns an empty list."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 0,
            "test_cases": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(len(result), 0)

    def test_load_preserves_all_tags(self):
        """All tags from the fixture are preserved in the EvalTestCase."""
        fixture = {
            "version": "1.0",
            "generated_at": "2026-06-09T00:00:00Z",
            "total_cases": 1,
            "test_cases": [
                {
                    "question": "Q?",
                    "expected_answer": "A.",
                    "context": "C.",
                    "tags": ["factual", "validated", "regression"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "golden_test_set.json"
            self._write_fixture(fixture, path)

            result = load_golden_test_set(path)

        self.assertEqual(result[0].tags, ["factual", "validated", "regression"])


if __name__ == "__main__":
    unittest.main()
