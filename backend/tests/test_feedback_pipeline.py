import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.models.chat import FeedbackRequest
from app.routers import chat, widget
from app.services import database


class FeedbackEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_feedback_reports_persistence_failure(self):
        user = SimpleNamespace(
            id="client-1",
            access_token="token-1",
            tenant_id="tenant-1",
            status="approved",
        )
        request = FeedbackRequest(
            thread_id="thread-1",
            message_id="answer-1",
            rating=-1,
            comment="Wrong fact",
        )

        with (
            patch.object(chat, "get_thread", return_value={"id": "thread-1"}),
            patch.object(chat, "get_thread_messages", return_value=[
                {"id": "answer-1", "role": "assistant"},
            ]),
            patch.object(chat, "save_message_feedback", return_value=None),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await chat.submit_feedback(request, user=user)

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Feedback could not be saved. Please try again.")

    async def test_submit_feedback_converts_database_error_to_retryable_response(self):
        user = SimpleNamespace(
            id="client-1",
            access_token="token-1",
            tenant_id="tenant-1",
            status="approved",
        )
        request = FeedbackRequest(
            thread_id="thread-1",
            message_id="answer-1",
            rating=-1,
        )

        with (
            patch.object(chat, "get_thread", return_value={"id": "thread-1"}),
            patch.object(chat, "get_thread_messages", return_value=[
                {"id": "answer-1", "role": "assistant"},
            ]),
            patch.object(chat, "save_message_feedback", side_effect=RuntimeError("write failed")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await chat.submit_feedback(request, user=user)

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Feedback could not be saved. Please try again.")

    async def test_submit_feedback_rejects_unowned_thread_before_writing(self):
        user = SimpleNamespace(
            id="client-1",
            access_token="token-1",
            tenant_id="tenant-1",
            status="approved",
        )
        request = FeedbackRequest(
            thread_id="thread-other",
            message_id="answer-other",
            rating=-1,
        )

        with (
            patch.object(chat, "get_thread", return_value=None),
            patch.object(chat, "save_message_feedback") as save_feedback,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await chat.submit_feedback(request, user=user)

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Conversation not found.")
        save_feedback.assert_not_called()

    async def test_submit_feedback_rejects_non_assistant_message_before_writing(self):
        user = SimpleNamespace(
            id="client-1",
            access_token="token-1",
            tenant_id="tenant-1",
            status="approved",
        )
        request = FeedbackRequest(
            thread_id="thread-1",
            message_id="question-1",
            rating=-1,
        )

        with (
            patch.object(chat, "get_thread", return_value={"id": "thread-1"}),
            patch.object(chat, "get_thread_messages", return_value=[
                {"id": "question-1", "role": "user"},
            ]),
            patch.object(chat, "save_message_feedback") as save_feedback,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await chat.submit_feedback(request, user=user)

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Assistant message not found.")
        save_feedback.assert_not_called()


class WidgetFeedbackEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_widget_feedback_rejects_thread_from_another_session(self):
        request = widget.WidgetFeedbackRequest(
            thread_id="thread-1",
            message_id="answer-1",
            rating=-1,
        )
        payload = {
            "tenant_id": "tenant-1",
            "session_id": "session-1",
            "origin": "https://client.example",
        }

        with (
            patch.object(widget, "verify_widget_token", return_value=payload),
            patch.object(widget, "get_thread_service", return_value={
                "id": "thread-1",
                "client_session_id": "session-other",
            }),
            patch.object(widget, "save_widget_feedback") as save_feedback,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await widget.submit_widget_feedback(
                    request,
                    authorization="Bearer token-1",
                    origin="https://client.example",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Conversation not found.")
        save_feedback.assert_not_called()

    async def test_widget_feedback_rejects_non_assistant_message(self):
        request = widget.WidgetFeedbackRequest(
            thread_id="thread-1",
            message_id="question-1",
            rating=-1,
        )
        payload = {
            "tenant_id": "tenant-1",
            "session_id": "session-1",
            "origin": "https://client.example",
        }

        with (
            patch.object(widget, "verify_widget_token", return_value=payload),
            patch.object(widget, "get_thread_service", return_value={
                "id": "thread-1",
                "client_session_id": "session-1",
            }),
            patch.object(widget, "get_thread_messages_service", return_value=[
                {"id": "question-1", "role": "user"},
            ]),
            patch.object(widget, "save_widget_feedback") as save_feedback,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await widget.submit_widget_feedback(
                    request,
                    authorization="Bearer token-1",
                    origin="https://client.example",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Assistant message not found.")
        save_feedback.assert_not_called()

    async def test_widget_feedback_converts_database_error_to_retryable_response(self):
        request = widget.WidgetFeedbackRequest(
            thread_id="thread-1",
            message_id="answer-1",
            rating=-1,
        )
        payload = {
            "tenant_id": "tenant-1",
            "session_id": "session-1",
            "origin": "https://client.example",
        }

        with (
            patch.object(widget, "verify_widget_token", return_value=payload),
            patch.object(widget, "get_thread_service", return_value={
                "id": "thread-1",
                "client_session_id": "session-1",
            }),
            patch.object(widget, "get_thread_messages_service", return_value=[
                {"id": "answer-1", "role": "assistant"},
            ]),
            patch.object(widget, "save_widget_feedback", side_effect=RuntimeError("write failed")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await widget.submit_widget_feedback(
                    request,
                    authorization="Bearer token-1",
                    origin="https://client.example",
                )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Feedback could not be saved. Please try again.")


class FeedbackDatabaseTests(unittest.TestCase):
    def test_feedback_dedup_migration_supports_both_upsert_conflict_targets(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "supabase"
            / "migrations"
            / "037_feedback_dedup_constraints.sql"
        )
        migration = migration_path.read_text(encoding="utf-8")

        self.assertIn(
            "CONSTRAINT message_feedback_user_dedup UNIQUE (user_id, thread_id, message_id)",
            migration,
        )
        self.assertIn(
            "CONSTRAINT message_feedback_session_dedup UNIQUE (client_session_id, thread_id, message_id)",
            migration,
        )
        self.assertNotIn("DELETE FROM", migration.upper())

    def test_save_message_feedback_propagates_database_failure(self):
        service_db = Mock()
        service_db.table.return_value.upsert.return_value.execute.side_effect = RuntimeError("write failed")

        with patch.object(database, "get_db", return_value=service_db):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                database.save_message_feedback(
                    user_id="client-1",
                    thread_id="thread-1",
                    message_id="answer-1",
                    rating=-1,
                    tenant_id="tenant-1",
                )

    def test_save_widget_feedback_propagates_database_failure(self):
        service_db = Mock()
        service_db.table.return_value.upsert.return_value.execute.side_effect = RuntimeError("write failed")

        with patch.object(database, "get_db", return_value=service_db):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                database.save_widget_feedback(
                    client_session_id="session-1",
                    thread_id="thread-1",
                    message_id="answer-1",
                    rating=-1,
                    tenant_id="tenant-1",
                )


if __name__ == "__main__":
    unittest.main()
