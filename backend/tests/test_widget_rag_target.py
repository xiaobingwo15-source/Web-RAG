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

        async def fake_agent_execute(**kwargs):
            captured.update(kwargs)
            yield {"type": "token", "content": "The canonical support color is cobalt blue."}

        with (
            patch.object(widget, "verify_widget_token", return_value={"tenant_id": "tenant-a", "session_id": "session-a", "origin": "http://example.test"}),
            patch.object(widget, "check_rate_limit"),
            patch.object(widget, "get_db", return_value=Mock(table=Mock(return_value=_Query([])))),
            patch.object(widget, "_resolve_widget_rag_target_user_id", return_value="admin-a"),
            patch.object(widget, "create_widget_thread", return_value={"id": "thread-a"}),
            patch.object(widget, "save_widget_message", return_value={"id": "message-a"}),
            patch.object(widget, "get_thread_messages_service", return_value=[]),
            patch.object(widget, "agent_execute", new=fake_agent_execute),
        ):
            response = await widget.chat_stream(
                request=widget.WidgetChatRequest(message="What is the canonical support color?"),
                authorization="Bearer widget-token",
                origin="http://example.test",
            )
            async for _ in response.body_iterator:
                pass

        self.assertEqual(captured["target_user_id"], "admin-a")
        self.assertEqual(captured["tenant_id"], "tenant-a")
        self.assertEqual(captured["user_id"], "session-a")


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
