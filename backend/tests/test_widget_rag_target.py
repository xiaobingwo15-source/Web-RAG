import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from app.routers import widget
from app.services import agent_supervisor


class _Query:
    def __init__(self, data=None):
        self.data = data or []
        self.filters = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        return self


class WidgetRagTargetTests(unittest.IsolatedAsyncioTestCase):
    def test_widget_target_resolves_tenant_admin_with_processed_docs(self):
        docs = _Query([{"id": "doc-a"}])
        db = Mock()
        db.table.return_value = docs

        with (
            patch.object(widget, "get_tenant_admin_user_id", return_value="admin-a"),
            patch.object(widget, "get_db", return_value=db),
        ):
            target = widget._resolve_widget_rag_target_user_id("tenant-a")

        self.assertEqual(target, "admin-a")
        self.assertIn(("tenant_id", "tenant-a"), docs.filters)
        self.assertIn(("user_id", "admin-a"), docs.filters)
        self.assertIn(("status", "processed"), docs.filters)

    def test_widget_target_fails_without_admin_owner(self):
        with patch.object(widget, "get_tenant_admin_user_id", return_value=None):
            with self.assertRaises(HTTPException) as context:
                widget._resolve_widget_rag_target_user_id("tenant-a")

        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("not configured", context.exception.detail)

    def test_widget_target_fails_without_processed_docs(self):
        db = Mock()
        db.table.return_value = _Query([])

        with (
            patch.object(widget, "get_tenant_admin_user_id", return_value="admin-a"),
            patch.object(widget, "get_db", return_value=db),
        ):
            with self.assertRaises(HTTPException) as context:
                widget._resolve_widget_rag_target_user_id("tenant-a")

        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("no processed", context.exception.detail)

    async def test_widget_stream_passes_resolved_target_user_to_supervisor(self):
        captured: dict = {}
        log_update: dict = {}
        accepted_answer = "The canonical support color is cobalt blue."
        update_message = Mock(return_value={"id": "streaming-msg-a"})

        async def fake_agent_execute(**kwargs):
            captured.update(kwargs)
            yield {"type": "token", "content": accepted_answer}
            yield {
                "type": "rag_quality",
                "retrieval_log_ids": ["log-a"],
                "groundedness": None,
                "groundedness_flag": False,
                "retrieval_quality": "retrieved",
                "diagnostics": {
                    "channel": "widget",
                    "web_fallback_allowed": False,
                    "used_web_fallback": False,
                },
            }

        def fake_update_logs(**kwargs):
            log_update.update(kwargs)

        with (
            patch.object(widget, "verify_widget_token", return_value={"tenant_id": "tenant-a", "session_id": "session-a", "origin": "http://example.test"}),
            patch.object(widget, "check_rate_limit"),
            patch.object(widget, "get_db", return_value=Mock(table=Mock(return_value=_Query([])))),
            patch.object(widget, "_resolve_widget_rag_target_user_id", return_value="admin-a"),
            patch.object(widget, "create_widget_thread", return_value={"id": "thread-a"}),
            patch.object(widget, "save_widget_message", return_value={"id": "message-a"}),
            patch.object(widget, "save_widget_message_streaming", return_value={"id": "streaming-msg-a"}),
            patch.object(widget, "update_message_content", new=update_message),
            patch.object(widget, "update_retrieval_logs_for_answer", side_effect=fake_update_logs),
            patch.object(widget, "get_thread_messages_service", return_value=[]),
            patch.object(widget, "agent_execute", new=fake_agent_execute),
        ):
            response = await widget.chat_stream(
                request=widget.WidgetChatRequest(message="What is the canonical support color?"),
                authorization="Bearer widget-token",
                origin="http://example.test",
            )
            events = [
                json.loads(item["data"])
                async for item in response.body_iterator
            ]

        self.assertEqual(captured["target_user_id"], "admin-a")
        self.assertEqual(captured["tenant_id"], "tenant-a")
        self.assertEqual(captured["user_id"], "session-a")
        self.assertFalse(captured["enable_web_search"])
        self.assertEqual(log_update["diagnostics"]["channel"], "widget")
        self.assertFalse(log_update["diagnostics"]["web_fallback_allowed"])
        self.assertFalse(log_update["diagnostics"]["used_web_fallback"])
        streamed_answer = "".join(
            event["content"]
            for event in events
            if event["type"] == "token"
        )
        self.assertEqual(streamed_answer, accepted_answer)
        update_message.assert_called_once_with(
            "streaming-msg-a",
            accepted_answer,
            status="complete",
        )

    async def test_widget_stream_persists_agent_errors_as_failed(self):
        async def failing_agent(**_kwargs):
            yield {
                "type": "error",
                "content": "",
                "error_code": "server_error",
            }

        update_message = Mock(return_value={"id": "streaming-msg-a"})
        with (
            patch.object(widget, "verify_widget_token", return_value={"tenant_id": "tenant-a", "session_id": "session-a", "origin": "http://example.test"}),
            patch.object(widget, "check_rate_limit"),
            patch.object(widget, "get_db", return_value=Mock(table=Mock(return_value=_Query([])))),
            patch.object(widget, "_resolve_widget_rag_target_user_id", return_value="admin-a"),
            patch.object(widget, "create_widget_thread", return_value={"id": "thread-a"}),
            patch.object(widget, "save_widget_message", return_value={"id": "message-a"}),
            patch.object(widget, "save_widget_message_streaming", return_value={"id": "streaming-msg-a"}),
            patch.object(widget, "update_message_content", new=update_message),
            patch.object(widget, "get_thread_messages_service", return_value=[]),
            patch.object(widget, "agent_execute", new=failing_agent),
        ):
            response = await widget.chat_stream(
                request=widget.WidgetChatRequest(message="Question"),
                authorization="Bearer widget-token",
                origin="http://example.test",
            )
            async for _ in response.body_iterator:
                pass

        update_message.assert_called_once_with(
            "streaming-msg-a",
            "The AI provider returned an error. Please try again.",
            status="failed",
        )

    async def test_widget_disconnect_during_verification_still_persists_accepted_answer(self):
        verification_reached = asyncio.Event()
        release_verification = asyncio.Event()
        persisted = asyncio.Event()
        accepted_answer = "The canonical support color is cobalt blue."

        async def verifying_agent(**_kwargs):
            verification_reached.set()
            yield {
                "type": "thought",
                "content": "Checking groundedness before delivering answer (attempt 2)...",
                "action_type": "verifying",
            }
            await release_verification.wait()
            yield {"type": "token", "content": accepted_answer}

        def persist_message(*_args, **_kwargs):
            persisted.set()
            return {"id": "streaming-msg-a"}

        update_message = Mock(side_effect=persist_message)
        settings = Mock(
            rate_limit_widget_requests=10,
            rate_limit_widget_window=60,
            widget_free_tier_limit=10,
            chat_pipeline_timeout_seconds=120,
        )

        with (
            patch.object(widget, "Settings", return_value=settings),
            patch.object(widget, "verify_widget_token", return_value={"tenant_id": "tenant-a", "session_id": "session-a", "origin": "http://example.test"}),
            patch.object(widget, "check_rate_limit"),
            patch.object(widget, "get_db", return_value=Mock(table=Mock(return_value=_Query([])))),
            patch.object(widget, "_resolve_widget_rag_target_user_id", return_value="admin-a"),
            patch.object(widget, "create_widget_thread", return_value={"id": "thread-a"}),
            patch.object(widget, "save_widget_message", return_value={"id": "message-a"}),
            patch.object(widget, "save_widget_message_streaming", return_value={"id": "streaming-msg-a"}),
            patch.object(widget, "update_message_content", new=update_message),
            patch.object(widget, "get_thread_messages_service", return_value=[]),
            patch.object(widget, "agent_execute", new=verifying_agent),
        ):
            response = await widget.chat_stream(
                request=widget.WidgetChatRequest(message="Question"),
                authorization="Bearer widget-token",
                origin="http://example.test",
            )
            stream = response.body_iterator
            progress = json.loads((await anext(stream))["data"])
            await verification_reached.wait()

            self.assertEqual(progress["action_type"], "verifying")
            await stream.aclose()
            release_verification.set()
            await asyncio.wait_for(persisted.wait(), timeout=1)

        update_message.assert_called_once_with(
            "streaming-msg-a",
            accepted_answer,
            status="complete",
        )


class AgentSupervisorTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_supervisor_honors_explicit_target_user_id(self):
        captured: dict = {}

        async def fake_doc_execute(*args, **kwargs):
            captured.update(kwargs)
            yield {"type": "token", "content": "ok"}

        with (
            patch.object(agent_supervisor, "get_llm_client", return_value=Mock()),
            patch.object(agent_supervisor, "_resolve_target_user_id") as resolve_target,
            patch.object(agent_supervisor.doc_rag_agent, "execute", new=fake_doc_execute),
        ):
            events = [
                event
                async for event in agent_supervisor.execute(
                    token="token",
                    user_id="client-a",
                    message="Question",
                    history=[],
                    thread_id="thread-a",
                    use_documents=True,
                    tenant_id="tenant-a",
                    target_user_id="admin-a",
                )
            ]

        resolve_target.assert_not_called()
        self.assertEqual(captured["target_user_id"], "admin-a")
        self.assertTrue(any(event.get("type") == "token" for event in events))


if __name__ == "__main__":
    unittest.main()
