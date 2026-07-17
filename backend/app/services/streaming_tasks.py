import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_streaming_tasks: set[asyncio.Task[Any]] = set()


def spawn_streaming_task(
    coroutine: Coroutine[Any, Any, Any],
    *,
    name: str,
) -> asyncio.Task[Any]:
    """Create a detached task while retaining and observing it."""
    task = asyncio.create_task(coroutine, name=name)
    _streaming_tasks.add(task)

    def _observe(completed: asyncio.Task[Any]) -> None:
        _streaming_tasks.discard(completed)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error(
                "Detached streaming task failed: %s",
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(_observe)
    return task


async def shutdown_streaming_tasks() -> None:
    """Cancel and await all active streaming tasks during graceful shutdown."""
    tasks = list(_streaming_tasks)
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
