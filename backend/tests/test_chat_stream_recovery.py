import asyncio
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.chat import MessageResponse
from app.models.chat import ChatRequest
from app.routers import chat
from app.services import database
from app.services.streaming_tasks import shutdown_streaming_tasks


class _UpdateQuery:
    def __init__(self):
        self.data = [{"id": "stale-assistant"}]
        self.updated = None
        self.filters = []

    def update(self, payload):
        self.updated = payload
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def lt(self, key, value):
        self.filters.append(("lt", key, value))
        return self

    def execute(self):
        return self


class _FakeDb:
    def __init__(self):
        self.messages = _UpdateQuery()

    def table(self, name):
        assert name == "messages"
        return self.messages


def test_message_response_preserves_streaming_status_contract():
    response = MessageResponse.model_validate(
        {
            "id": "assistant-a",
            "role": "assistant",
            "content": "Answer",
            "created_at": "2026-07-17T00:00:00Z",
            "reply_to": None,
            "status": "complete",
        }
    )

    assert response.model_dump()["status"] == "complete"


def test_expire_stale_streaming_messages_marks_rows_failed(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(database, "get_db", lambda: fake_db)

    expired = database.expire_stale_streaming_messages(max_age_seconds=135)

    assert expired == 1
    assert fake_db.messages.updated == {
        "status": "failed",
        "content": "This response was interrupted. Please try again.",
    }
    assert ("eq", "status", "streaming") in fake_db.messages.filters
    assert any(item[:2] == ("lt", "created_at") for item in fake_db.messages.filters)


@pytest.mark.asyncio
async def test_chat_stream_sends_and_persists_one_accepted_answer():
    accepted_answer = "Atlas is operational."

    async def successful_agent(**_kwargs):
        yield {
            "type": "thought",
            "content": "Checking groundedness before delivering answer (attempt 2)...",
            "action_type": "verifying",
        }
        yield {"type": "token", "content": "Atlas is "}
        yield {"type": "token", "content": "operational."}
        yield {
            "type": "rag_quality",
            "retrieval_log_ids": ["log-a"],
            "groundedness": 0.95,
            "groundedness_flag": False,
            "retrieval_quality": "retrieved",
            "diagnostics": {"channel": "authenticated"},
        }

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=120,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=successful_agent),
        patch.object(chat, "update_message_content", return_value={}) as update_message,
        patch.object(chat, "update_retrieval_logs_for_answer"),
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        events = [
            json.loads(item["data"])
            async for item in response.body_iterator
        ]

    streamed_answer = "".join(
        event["content"]
        for event in events
        if event["type"] == "token"
    )
    assert streamed_answer == accepted_answer
    update_message.assert_called_once_with(
        "assistant-message",
        accepted_answer,
        status="complete",
    )


@pytest.mark.asyncio
async def test_chat_disconnect_during_verification_still_persists_accepted_answer():
    verification_reached = asyncio.Event()
    release_verification = asyncio.Event()
    persisted = asyncio.Event()
    accepted_answer = "Atlas is operational."

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
        return {}

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=120,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=verifying_agent),
        patch.object(
            chat,
            "update_message_content",
            side_effect=persist_message,
        ) as update_message,
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        stream = response.body_iterator
        await anext(stream)
        await anext(stream)
        progress = json.loads((await anext(stream))["data"])
        await verification_reached.wait()

        assert progress["action_type"] == "verifying"
        await stream.aclose()
        release_verification.set()
        await asyncio.wait_for(persisted.wait(), timeout=1)

    update_message.assert_called_once_with(
        "assistant-message",
        accepted_answer,
        status="complete",
    )


@pytest.mark.asyncio
async def test_chat_stream_persists_agent_errors_as_failed():
    async def failing_agent(**_kwargs):
        yield {
            "type": "error",
            "content": "",
            "error_code": "server_error",
        }

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=120,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=failing_agent),
        patch.object(chat, "update_message_content", return_value={}) as update_message,
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        async for _ in response.body_iterator:
            pass

    update_message.assert_called_once_with(
        "assistant-message",
        "The AI provider returned an error. Please try again.",
        status="failed",
    )


@pytest.mark.asyncio
async def test_chat_stream_marks_pipeline_timeout_as_failed():
    async def slow_empty_agent(**_kwargs):
        await __import__("asyncio").sleep(0.05)
        if False:
            yield {}

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=0.01,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=slow_empty_agent),
        patch.object(chat, "update_message_content", return_value={}) as update_message,
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        async for _ in response.body_iterator:
            pass

    update_message.assert_called_once_with(
        "assistant-message",
        "This response took too long. Please try again.",
        status="failed",
    )


@pytest.mark.asyncio
async def test_chat_stream_marks_empty_output_as_failed():
    async def empty_agent(**_kwargs):
        if False:
            yield {}

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=120,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=empty_agent),
        patch.object(chat, "update_message_content", return_value={}) as update_message,
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        async for _ in response.body_iterator:
            pass

    update_message.assert_called_once_with(
        "assistant-message",
        "The AI returned an empty response. Please try again.",
        status="failed",
    )


@pytest.mark.asyncio
async def test_chat_stream_marks_graceful_shutdown_as_failed():
    started = asyncio.Event()

    async def hanging_agent(**_kwargs):
        started.set()
        await asyncio.Event().wait()
        if False:
            yield {}

    user = SimpleNamespace(
        id="user-a",
        status="approved",
        role="client",
        access_token="token-a",
        tenant_id="tenant-a",
    )

    with (
        patch.object(
            chat,
            "Settings",
            return_value=SimpleNamespace(
                rate_limit_chat_requests=10,
                rate_limit_chat_window=60,
                sql_tools_enabled=False,
                chat_pipeline_timeout_seconds=120,
            ),
        ),
        patch.object(chat, "check_rate_limit"),
        patch.object(chat, "propagate_attributes", return_value=nullcontext()),
        patch.object(
            chat,
            "save_message",
            return_value={"id": "user-message", "created_at": "2026-07-17T00:00:00Z"},
        ),
        patch.object(
            chat,
            "save_message_streaming",
            return_value={"id": "assistant-message", "created_at": "2026-07-17T00:00:01Z"},
        ),
        patch.object(
            chat,
            "get_thread_messages",
            return_value=[{"id": "user-message", "role": "user", "content": "Question"}],
        ),
        patch.object(chat, "agent_execute", new=hanging_agent),
        patch.object(chat, "update_message_content", return_value={}) as update_message,
    ):
        response = await chat.chat_stream(
            ChatRequest(message="Question", thread_id="thread-a"),
            user=user,
        )
        stream = response.body_iterator
        await anext(stream)
        await anext(stream)
        await started.wait()

        await shutdown_streaming_tasks()
        async for _ in stream:
            pass

    update_message.assert_called_once_with(
        "assistant-message",
        "This response was interrupted. Please try again.",
        status="failed",
    )
