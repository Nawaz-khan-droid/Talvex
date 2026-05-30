"""
Test Suite: Rate Limiter Functionality

Validates the in-memory token bucket rate limiter:
  1. Token bucket mechanics (consume, refill, deficit calculation)
  2. Service configuration (openrouter, tavily, serper)
  3. Per-minute bucket limits
  4. Per-day bucket limits
  5. Min-interval enforcement
  6. Context manager and decorator interfaces
  7. Stale bucket cleanup
"""

import asyncio
import time
import threading

import pytest


# ===================================================================
# 1. Token Bucket Mechanics
# ===================================================================

class TestTokenBucketMechanics:
    """Test the TokenBucket dataclass."""

    def test_initial_tokens_equal_max(self, rate_limiter_module):
        """A fresh bucket starts with max_tokens."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert bucket.tokens == 10.0

    def test_consume_reduces_tokens(self, rate_limiter_module):
        """Consuming a token reduces the available count."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1.0)
        bucket.consume()
        assert bucket.tokens == 9.0

    def test_consume_below_zero(self, rate_limiter_module):
        """Tokens can go negative (deficit)."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=1.0, refill_rate=1.0)
        bucket.consume()
        bucket.consume()  # deficit
        assert bucket.tokens < 0

    def test_refill_increases_tokens(self, rate_limiter_module):
        """Tokens refill over time based on refill_rate."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=100.0)
        bucket.consume()
        time.sleep(0.05)  # 50ms should give ~5 tokens at rate 100/s
        bucket._refill()
        assert bucket.tokens > 8.0  # Should have partially refilled

    def test_refill_caps_at_max(self, rate_limiter_module):
        """Tokens never exceed max_tokens after refill."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1000.0)
        time.sleep(0.05)
        bucket._refill()
        assert bucket.tokens <= 10.0

    def test_deficit_seconds_when_available(self, rate_limiter_module):
        """deficit_seconds returns 0 when tokens are available."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert bucket.deficit_seconds == 0.0

    def test_deficit_seconds_when_depleted(self, rate_limiter_module):
        """deficit_seconds returns positive when tokens are depleted."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=0.0, refill_rate=1.0)
        # Tokens start at 0 (max=0), so deficit > 0
        assert bucket.deficit_seconds > 0

    def test_last_used_updated_on_consume(self, rate_limiter_module):
        """last_used is updated when a token is consumed."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1.0)
        before = bucket.last_used
        time.sleep(0.01)
        bucket.consume()
        assert bucket.last_used > before

    def test_is_stale(self, rate_limiter_module):
        """Bucket reports stale after 1 hour of inactivity."""
        bucket = rate_limiter_module.TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert not bucket.is_stale
        # Manually set last_used to the past
        bucket.last_used = time.monotonic() - 3700  # > 1 hour
        assert bucket.is_stale


# ===================================================================
# 2. Service Configuration
# ===================================================================

class TestServiceConfiguration:
    """Test that services are configured correctly."""

    def test_openrouter_service_exists(self, rate_limiter_module):
        """OpenRouter service is pre-configured."""
        assert "openrouter" in rate_limiter_module.rate_limiter._buckets

    def test_tavily_service_exists(self, rate_limiter_module):
        """Tavily service is pre-configured."""
        assert "tavily" in rate_limiter_module.rate_limiter._buckets

    def test_serper_service_exists(self, rate_limiter_module):
        """Serper service is pre-configured."""
        assert "serper" in rate_limiter_module.rate_limiter._buckets

    def test_openrouter_daily_limit(self, rate_limiter_module):
        """OpenRouter daily limit is 40."""
        bucket = rate_limiter_module.rate_limiter._buckets["openrouter"]
        assert bucket.day.max_tokens == 40.0

    def test_openrouter_minute_limit(self, rate_limiter_module):
        """OpenRouter minute limit is 15."""
        bucket = rate_limiter_module.rate_limiter._buckets["openrouter"]
        assert bucket.minute.max_tokens == 15.0

    def test_openrouter_min_interval(self, rate_limiter_module):
        """OpenRouter min interval is 4.5s."""
        bucket = rate_limiter_module.rate_limiter._buckets["openrouter"]
        assert bucket.min_interval == 4.5


# ===================================================================
# 3. Rate Limiter Context Manager
# ===================================================================

class TestRateLimiterContextManager:
    """Test the async context manager interface."""

    def test_context_manager_interface(self, rate_limiter_module):
        """Rate limiter supports 'async with' syntax."""
        assert hasattr(rate_limiter_module.rate_limiter, '__call__')
        ctx = rate_limiter_module.rate_limiter("openrouter")
        assert hasattr(ctx, '__aenter__')
        assert hasattr(ctx, '__aexit__')

    @pytest.mark.asyncio
    async def test_acquire_returns_true(self, rate_limiter_module):
        """acquire() returns True when tokens are available."""
        # Use a fresh limiter for testing
        limiter = rate_limiter_module.InMemoryRateLimiter()
        limiter.configure_service("test", daily=10, per_minute=10)
        result = await limiter.acquire("test")
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_consumes_tokens(self, rate_limiter_module):
        """acquire() consumes tokens from both minute and day buckets."""
        limiter = rate_limiter_module.InMemoryRateLimiter()
        limiter.configure_service("test", daily=10, per_minute=10)
        await limiter.acquire("test")
        bucket = limiter._buckets["test"]
        assert bucket.minute.tokens == 9.0
        assert bucket.day.tokens == 9.0


# ===================================================================
# 4. Decorator Interface
# ===================================================================

class TestRateLimiterDecorator:
    """Test the decorator interface."""

    def test_decorator_factory_exists(self, rate_limiter_module):
        """rate_limit() decorator factory exists."""
        assert callable(rate_limiter_module.rate_limit)

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self, rate_limiter_module):
        """rate_limit decorator wraps async functions."""
        limiter = rate_limiter_module.InMemoryRateLimiter()
        limiter.configure_service("test", daily=10, per_minute=10)

        @limiter.rate_limit_decorator("test")
        async def test_func():
            return "ok"

        result = await test_func()
        assert result == "ok"

    def test_shorthand_decorator_exists(self, rate_limiter_module):
        """Shorthand @rate_limit("service") syntax works."""
        decorator = rate_limiter_module.rate_limit("openrouter")
        assert callable(decorator)


# ===================================================================
# 5. Cleanup
# ===================================================================

class TestStaleBucketCleanup:
    """Test automatic cleanup of stale buckets."""

    def test_configure_creates_bucket(self, rate_limiter_module):
        """configure_service creates a new bucket."""
        limiter = rate_limiter_module.InMemoryRateLimiter(cleanup_interval=9999)
        limiter.configure_service("test-cleanup", daily=10, per_minute=10)
        assert "test-cleanup" in limiter._buckets

    def test_default_bucket_for_unknown_service(self, rate_limiter_module):
        """Unknown services get default bucket configuration."""
        limiter = rate_limiter_module.InMemoryRateLimiter(default_daily=100, default_per_minute=20)
        limiter._ensure_bucket("unknown-service")
        assert "unknown-service" in limiter._buckets
        assert limiter._buckets["unknown-service"].day.max_tokens == 100
