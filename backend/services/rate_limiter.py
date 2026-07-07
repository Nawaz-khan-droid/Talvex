"""In-memory token bucket rate limiter for the TALVEX project.

Pure stdlib — no Redis or external deps.  Stays within free-tier API limits.

Usage::

    async with rate_limiter("openrouter"):    # context manager
        await call_api()

    @rate_limit("openrouter")                 # decorator
    async def call_api(): ...
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import redis as redis_py

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Lazy-replenishing token bucket."""

    max_tokens: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False, default_factory=time.monotonic)
    last_used: float = field(init=False, default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.tokens = self.max_tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    @property
    def deficit_seconds(self) -> float:
        """Seconds until ≥1 token is available (0 when ready)."""
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.refill_rate if self.refill_rate > 0 else float("inf")

    def consume(self) -> None:
        """Take one token (caller must verify availability first)."""
        self._refill()
        self.tokens -= 1.0
        self.last_used = time.monotonic()

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self.last_used) > 3600


@dataclass
class ServiceBucket:
    """Minute + day bucket pair for one service."""
    minute: TokenBucket
    day: TokenBucket
    min_interval: float = 0.0
    last_call: float = 0.0


class InMemoryRateLimiter:
    """Thread-safe, in-memory token bucket rate limiter with per-service
    buckets and automatic stale-bucket eviction."""

    def __init__(
        self,
        default_daily: int = 1000,
        default_per_minute: int = 60,
        cleanup_interval: int = 3600,
        enable_redis_persistence: bool = True,
    ) -> None:
        self._default_daily = default_daily
        self._default_per_minute = default_per_minute
        self._cleanup_interval = cleanup_interval
        self._lock = threading.Lock()
        self._buckets: dict[str, ServiceBucket] = {}
        self._last_cleanup = time.monotonic()
        self._redis_enabled = enable_redis_persistence
        self._redis_client: redis_py.Redis | None = None
        if enable_redis_persistence:
            self._redis_client = self._create_redis_client()

    def configure_service(
        self, service: str, daily: int, per_minute: int, min_interval: float = 0.0
    ) -> None:
        """Register (or overwrite) rate limits for *service*."""
        with self._lock:
            self._buckets[service] = ServiceBucket(
                minute=TokenBucket(max_tokens=float(per_minute), refill_rate=per_minute / 60.0),
                day=TokenBucket(max_tokens=float(daily), refill_rate=daily / 86400.0),
                min_interval=min_interval,
            )

    async def acquire(self, service: str) -> bool:
        """Block until a token is available, then consume it.  Never raises."""
        bucket = self._ensure_bucket(service)
        if self._redis_client is not None:
            return await self._acquire_with_redis(service, bucket)
        while True:
            with self._lock:
                can, wait = self._check(bucket)
                if can:
                    bucket.minute.consume()
                    bucket.day.consume()
                    bucket.last_call = time.monotonic()
                    return True
            if wait > 0:
                logger.warning("Rate limit reached for '%s'; sleeping %.1fs", service, wait)
                await asyncio.sleep(wait)

    def _create_redis_client(self) -> redis_py.Redis | None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            client = redis_py.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("RateLimiter using Redis-backed persistence.")
            return client
        except Exception as exc:
            logger.warning(
                "RateLimiter Redis unavailable; falling back to in-memory only: %s",
                exc,
            )
            return None

    def _redis_key(self, service: str) -> str:
        return f"talvex:rate_limiter:{service}"

    def _load_redis_state(self, service: str, bucket: ServiceBucket) -> dict[str, float]:
        assert self._redis_client is not None
        now = time.time()
        raw = self._redis_client.hgetall(self._redis_key(service))
        if not raw:
            state = {
                "minute_tokens": bucket.minute.max_tokens,
                "minute_last_refill": now,
                "day_tokens": bucket.day.max_tokens,
                "day_last_refill": now,
                "last_call": 0.0,
            }
            self._redis_client.hset(self._redis_key(service), mapping={k: str(v) for k, v in state.items()})
            self._redis_client.expire(self._redis_key(service), 7 * 86400)
            return state

        def _f(name: str, default: float) -> float:
            try:
                return float(raw.get(name, default))
            except (TypeError, ValueError):
                return default

        return {
            "minute_tokens": _f("minute_tokens", bucket.minute.max_tokens),
            "minute_last_refill": _f("minute_last_refill", now),
            "day_tokens": _f("day_tokens", bucket.day.max_tokens),
            "day_last_refill": _f("day_last_refill", now),
            "last_call": _f("last_call", 0.0),
        }

    def _save_redis_state(self, service: str, state: dict[str, float]) -> None:
        assert self._redis_client is not None
        self._redis_client.hset(self._redis_key(service), mapping={k: str(v) for k, v in state.items()})
        self._redis_client.expire(self._redis_key(service), 7 * 86400)

    @staticmethod
    def _apply_redis_refill(tokens: float, max_tokens: float, refill_rate: float, now: float, last_refill: float) -> tuple[float, float]:
        elapsed = max(0.0, now - last_refill)
        if elapsed > 0:
            tokens = min(max_tokens, tokens + elapsed * refill_rate)
            last_refill = now
        return tokens, last_refill

    async def _acquire_with_redis(self, service: str, bucket: ServiceBucket) -> bool:
        assert self._redis_client is not None
        while True:
            wait = 0.0
            try:
                with self._lock:
                    now = time.time()
                    state = self._load_redis_state(service, bucket)

                    minute_tokens, minute_last = self._apply_redis_refill(
                        state["minute_tokens"],
                        bucket.minute.max_tokens,
                        bucket.minute.refill_rate,
                        now,
                        state["minute_last_refill"],
                    )
                    day_tokens, day_last = self._apply_redis_refill(
                        state["day_tokens"],
                        bucket.day.max_tokens,
                        bucket.day.refill_rate,
                        now,
                        state["day_last_refill"],
                    )

                    wait_minute = 0.0 if minute_tokens >= 1.0 else (1.0 - minute_tokens) / max(bucket.minute.refill_rate, 1e-9)
                    wait_day = 0.0 if day_tokens >= 1.0 else (1.0 - day_tokens) / max(bucket.day.refill_rate, 1e-9)
                    wait_interval = 0.0
                    if bucket.min_interval > 0 and state["last_call"] > 0:
                        since = now - state["last_call"]
                        if since < bucket.min_interval:
                            wait_interval = bucket.min_interval - since

                    wait = max(wait_minute, wait_day, wait_interval)
                    if wait <= 0:
                        minute_tokens -= 1.0
                        day_tokens -= 1.0
                        self._save_redis_state(
                            service,
                            {
                                "minute_tokens": minute_tokens,
                                "minute_last_refill": minute_last,
                                "day_tokens": day_tokens,
                                "day_last_refill": day_last,
                                "last_call": now,
                            },
                        )
                        return True
            except Exception as exc:
                logger.warning("RateLimiter Redis persistence failed; using in-memory fallback: %s", exc)
                self._redis_client = None
                return await self.acquire(service)

            logger.warning("Rate limit reached for '%s'; sleeping %.1fs", service, wait)
            await asyncio.sleep(wait)

    def _check(self, bucket: ServiceBucket) -> tuple[bool, float]:
        """Under lock: return (can_acquire, wait_seconds)."""
        deficit_min = bucket.minute.deficit_seconds
        deficit_day = bucket.day.deficit_seconds
        if deficit_min > 0 or deficit_day > 0:
            return False, max(deficit_min, deficit_day)
        if bucket.min_interval > 0 and bucket.last_call > 0:
            since = time.monotonic() - bucket.last_call
            if since < bucket.min_interval:
                return False, bucket.min_interval - since
        return True, 0.0

    def _ensure_bucket(self, service: str) -> ServiceBucket:
        self._maybe_cleanup()
        if service not in self._buckets:
            self.configure_service(service, self._default_daily, self._default_per_minute)
        return self._buckets[service]

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        stale = [n for n, b in self._buckets.items() if b.minute.is_stale and b.day.is_stale]
        for n in stale:
            del self._buckets[n]
        self._last_cleanup = now

    def rate_limit_decorator(self, service: str) -> Callable:
        """Decorator factory for async functions."""

        def decorator(func: Callable) -> Callable:
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                await self.acquire(service)
                return await func(*args, **kwargs)

            wrapper.__name__ = func.__name__
            wrapper.__qualname__ = func.__qualname__
            wrapper.__wrapped__ = func  # type: ignore[attr-defined]
            return wrapper

        return decorator

    def __call__(self, service: str) -> _RateLimitContext:
        """Enable ``async with rate_limiter("service")`` syntax."""
        return _RateLimitContext(self, service)


class _RateLimitContext:
    """Async context manager that acquires a rate-limit token on entry."""

    __slots__ = ("_limiter", "_service")

    def __init__(self, limiter: InMemoryRateLimiter, service: str) -> None:
        self._limiter = limiter
        self._service = service

    async def __aenter__(self) -> None:
        await self._limiter.acquire(self._service)

    async def __aexit__(self, *_args: Any) -> None:
        pass


# -- Singleton & pre-configuration -----------------------------------------

rate_limiter = InMemoryRateLimiter()
rate_limiter.configure_service("openrouter", daily=40, per_minute=15, min_interval=4.5)
rate_limiter.configure_service("tavily", daily=33, per_minute=10)
rate_limiter.configure_service("serper", daily=50, per_minute=15)
rate_limiter.configure_service("jsearch", daily=10, per_minute=5)


def rate_limit(service: str) -> Callable:
    """Shorthand decorator: ``@rate_limit("openrouter")``."""
    return rate_limiter.rate_limit_decorator(service)
