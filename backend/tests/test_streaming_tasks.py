import asyncio

import pytest


@pytest.mark.asyncio
async def test_shutdown_streaming_tasks_cancels_and_awaits_registered_work():
    from app.services.streaming_tasks import shutdown_streaming_tasks, spawn_streaming_task

    started = asyncio.Event()
    stopped = asyncio.Event()

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    spawn_streaming_task(worker(), name="test-stream")
    await started.wait()

    await shutdown_streaming_tasks()

    assert stopped.is_set()
