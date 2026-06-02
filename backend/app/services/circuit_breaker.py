"""
In-memory circuit breaker for external service calls.

States:
  CLOSED  — normal operation, calls pass through
  OPEN    — too many failures, calls rejected immediately
  HALF_OPEN — recovery window, limited calls allowed to test if service recovered
"""

import asyncio
import logging
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejecting calls."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is open. "
            f"Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """Async circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(f"Circuit '{self.name}' transitioning OPEN -> HALF_OPEN")
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker."""
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                retry_after = self.recovery_timeout - (
                    time.monotonic() - self._last_failure_time
                )
                raise CircuitBreakerOpenError(self.name, max(0, retry_after))

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(self.name, self.recovery_timeout)
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
        except Exception:
            async with self._lock:
                self._record_failure()
            raise
        else:
            async with self._lock:
                self._record_success()
            return result

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}' HALF_OPEN call failed -> OPEN")
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit '{self.name}' reached {self._failure_count} failures -> OPEN"
            )
            self._state = CircuitState.OPEN

    def _record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit '{self.name}' HALF_OPEN call succeeded -> CLOSED")
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0


# Global circuit breaker instances
_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, **kwargs)
    return _breakers[name]


def circuit_breaker(name: str, **kwargs: Any) -> Callable:
    """Decorator that wraps an async function with a circuit breaker."""

    def decorator(func: Callable) -> Callable:
        breaker = get_circuit_breaker(name, **kwargs)

        @wraps(func)
        async def wrapper(*args: Any, **kw: Any) -> Any:
            return await breaker.call(func, *args, **kw)

        wrapper.circuit_breaker = breaker  # type: ignore[attr-defined]
        return wrapper

    return decorator
