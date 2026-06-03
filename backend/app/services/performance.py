import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("app.performance")


def monotonic_ms() -> float:
    return time.perf_counter() * 1000


def elapsed_ms(start_ms: float) -> int:
    return int(monotonic_ms() - start_ms)


def log_latency(event: str, duration_ms: int, **fields: Any) -> None:
    payload = {
        "event": event,
        "duration_ms": duration_ms,
        **{key: value for key, value in fields.items() if value is not None},
    }
    logger.info("latency %s", payload)


@contextmanager
def timed_stage(event: str, **fields: Any):
    start = monotonic_ms()
    try:
        yield
    finally:
        log_latency(event, elapsed_ms(start), **fields)


async def timed_async(label: str, fn: Callable[[], Any], **fields: Any) -> Any:
    start = monotonic_ms()
    try:
        return await fn()
    finally:
        log_latency(label, elapsed_ms(start), **fields)
