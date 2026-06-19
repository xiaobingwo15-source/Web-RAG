import json
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from app.models.chat import ChatRequest
from app.routers import chat


class ReplyContextTests(unittest.TestCase):
    def test_build_active_message_includes_plain_text_reply(self):
        messages = [{"id": "assistant-a", "role": "assistant", "content": "Samsung RF28R7351SR details"}]

        result = chat.build_active_message("Show me in Chinese", messages, "assistant-a")

        self.assertEqual(
            result,
            "Replying to: Samsung RF28R7351SR details\n\nUser message: Show me in Chinese",
        )

    def test_build_active_message_extracts_json_text_reply(self):
        messages = [
            {
                "id": "user-a",
                "role": "user",
                "content": json.dumps({"text": "Photo of the label", "images": ["data:image/png;base64,abc"]}),
            }
        ]

        result = chat.build_active_message("What model is this?", messages, "user-a")

        self.assertEqual(result, "Replying to: Photo of the label\n\nUser message: What model is this?")

    def test_build_active_message_truncates_long_reply(self):
        messages = [{"id": "assistant-a", "role": "assistant", "content": "x" * 600}]

        result = chat.build_active_message("Summarize", messages, "assistant-a")

        quoted = result.removeprefix("Replying to: ").split("\n\nUser message:")[0]
        self.assertEqual(len(quoted), 500)
        self.assertTrue(quoted.endswith("..."))

    def test_build_active_message_ignores_missing_reply(self):
        messages = [{"id": "assistant-a", "role": "assistant", "content": "Details"}]

        result = chat.build_active_message("Show me in Chinese", messages, "missing")

        self.assertEqual(result, "Show me in Chinese")

    def test_build_active_message_without_reply_is_unchanged(self):
        result = chat.build_active_message("Plain question", [], None)

        self.assertEqual(result, "Plain question")


class ChatStreamReplyContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_passes_reply_aware_message_to_agent(self):
        captured: dict = {}

        async def fake_agent_execute(**kwargs):
            captured.update(kwargs)
            yield {"type": "token", "content": "Samsung RF28R7351SR"}

        user = SimpleNamespace(
            id="user-a",
            status="approved",
            access_token="token-a",
            tenant_id="tenant-a",
        )
        thread_messages = [
            {
                "id": "assistant-a",
                "role": "assistant",
                "content": "The refrigerator model is Samsung RF28R7351SR.",
            },
            {
                "id": "user-b",
                "role": "user",
                "content": "Show me in Chinese",
                "reply_to": "assistant-a",
            },
        ]

        with (
            patch.object(chat, "Settings", return_value=SimpleNamespace(rate_limit_chat_requests=10, rate_limit_chat_window=60)),
            patch.object(chat, "check_rate_limit"),
            patch.object(chat, "propagate_attributes", return_value=nullcontext()),
            patch.object(chat, "save_message", return_value={"id": "user-b", "created_at": "2026-01-01T00:00:00Z"}),
            patch.object(chat, "save_message_streaming", return_value={"id": "assistant-b", "created_at": "2026-01-01T00:00:01Z"}),
            patch.object(chat, "update_message_content", return_value={"id": "assistant-b"}),
            patch.object(chat, "get_thread_messages", return_value=thread_messages),
            patch.object(chat, "agent_execute", new=fake_agent_execute),
        ):
            response = await chat.chat_stream(
                request=ChatRequest(
                    message="Show me in Chinese",
                    thread_id="thread-a",
                    reply_to="assistant-a",
                    use_documents=True,
                ),
                user=user,
            )
            async for _ in response.body_iterator:
                pass

        self.assertEqual(
            captured["message"],
            "Replying to: The refrigerator model is Samsung RF28R7351SR.\n\nUser message: Show me in Chinese",
        )
        self.assertEqual(captured["thread_id"], "thread-a")
        self.assertTrue(captured["use_documents"])


if __name__ == "__main__":
    unittest.main()
