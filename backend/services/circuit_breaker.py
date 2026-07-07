from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a circuit breaker is open and rejects calls."""


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 60.0


class AsyncCircuitBreaker:
    """Small async circuit breaker with CLOSED -> OPEN -> HALF_OPEN states."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def call(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            if self._state == "OPEN":
                elapsed = time.monotonic() - self._last_failure_at
                if elapsed >= self._config.recovery_timeout_seconds:
                    self._state = "HALF_OPEN"
                    logger.warning("Circuit breaker '%s' moved OPEN -> HALF_OPEN.", self._name)
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self._name}' is OPEN; retry in "
                        f"{max(0.0, self._config.recovery_timeout_seconds - elapsed):.1f}s."
                    )

        try:
            result = await func(*args, **kwargs)
        except Exception:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_at = time.monotonic()
                if self._failure_count >= self._config.failure_threshold:
                    if self._state != "OPEN":
                        logger.error(
                            "Circuit breaker '%s' opened after %d failures.",
                            self._name,
                            self._failure_count,
                        )
                    self._state = "OPEN"
            raise

        async with self._lock:
            if self._state in {"OPEN", "HALF_OPEN"}:
                logger.info("Circuit breaker '%s' recovered to CLOSED.", self._name)
            self._state = "CLOSED"
            self._failure_count = 0

        return result
