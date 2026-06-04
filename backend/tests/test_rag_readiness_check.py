import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import rag_readiness_check as readiness  # noqa: E402


class RagReadinessValidationTests(unittest.TestCase):
    def test_assert_answer_requires_document_source(self):
        result = readiness.StreamResult(
            answer="The canonical support color is cobalt blue.",
            sources=[],
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            completed=True,
        )

        with self.assertRaisesRegex(AssertionError, "document source"):
            readiness.assert_answer(result, "cobalt blue", "doc-a")

    def test_assert_answer_rejects_web_only_sources(self):
        result = readiness.StreamResult(
            answer="The canonical support color is cobalt blue.",
            sources=[{"document_id": "web_search"}],
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            completed=True,
        )

        with self.assertRaisesRegex(AssertionError, "document source"):
            readiness.assert_answer(result, "cobalt blue", "doc-a")

    def test_assert_answer_requires_expected_document_id(self):
        result = readiness.StreamResult(
            answer="The canonical support color is cobalt blue.",
            sources=[{"document_id": "doc-other"}],
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            completed=True,
        )

        with self.assertRaisesRegex(AssertionError, "Expected document doc-a"):
            readiness.assert_answer(result, "cobalt blue", "doc-a")

    def test_assert_answer_requires_done_event(self):
        result = readiness.StreamResult(
            answer="The canonical support color is cobalt blue.",
            sources=[{"document_id": "doc-a"}],
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            completed=False,
        )

        with self.assertRaisesRegex(AssertionError, "done event"):
            readiness.assert_answer(result, "cobalt blue", "doc-a")

    def test_assert_answer_rejects_fallback_wording(self):
        result = readiness.StreamResult(
            answer="I didn't find relevant documents, so I searched the web. The answer is cobalt blue.",
            sources=[{"document_id": "doc-a"}],
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            completed=True,
        )

        with self.assertRaisesRegex(AssertionError, "fallback marker"):
            readiness.assert_answer(result, "cobalt blue", "doc-a")


class RagReadinessArgumentTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_requires_widget_slug_unless_skip_widget_is_set(self):
        with patch.object(sys, "argv", ["rag_readiness_check.py", "--admin-token", "admin", "--chat-token", "chat"]):
            self.assertEqual(await readiness.main(), 2)

    async def test_main_allows_missing_widget_slug_when_skip_widget_is_set(self):
        class DummyClient:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        case = readiness.CaseResult(
            channel="authenticated",
            question="What is the canonical support color?",
            thread_id="thread-a",
            first_token_ms=10,
            full_answer_ms=20,
            source_ids=["doc-a"],
            passed=True,
        )

        with (
            patch.object(sys, "argv", ["rag_readiness_check.py", "--admin-token", "admin", "--chat-token", "chat", "--skip-widget"]),
            patch.object(readiness.httpx, "AsyncClient", return_value=DummyClient()),
            patch.object(readiness, "upload_fixture", new=AsyncMock(return_value="doc-a")),
            patch.object(readiness, "wait_for_document", new=AsyncMock(return_value={"status": "processed"})),
            patch.object(readiness, "check_qdrant", new=AsyncMock(return_value={"chunk_count": 1, "samples": []})),
            patch.object(readiness, "run_case", new=AsyncMock(return_value=case)),
            patch.object(readiness, "create_widget_session", new=AsyncMock()) as create_widget_session,
        ):
            self.assertEqual(await readiness.main(), 0)

        create_widget_session.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
