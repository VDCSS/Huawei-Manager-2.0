"""Tests for RateLimiter — per-device token bucket rate limiting."""
from __future__ import annotations

import pytest

from huawei_manager.sdn_controller.ratelimit import RateLimiter, TokenBucket

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter()


@pytest.fixture
def bucket() -> TokenBucket:
    return TokenBucket(device_id="R1", rate=10, burst=20)


# ── TokenBucket basics ───────────────────────────────────────────────────────


class TestTokenBucket:
    """TokenBucket must manage tokens per device."""

    def test_initial_tokens_equal_burst(self, bucket: TokenBucket):
        assert bucket.tokens == 20
        assert bucket.max_tokens == 20

    def test_consume_returns_true_when_tokens_available(self, bucket: TokenBucket):
        assert bucket.consume() is True
        assert bucket.tokens == 19

    def test_consume_multiple_tokens(self, bucket: TokenBucket):
        assert bucket.consume(5) is True
        assert bucket.tokens == 15

    def test_consume_returns_false_when_empty(self, bucket: TokenBucket):
        bucket.tokens = 0
        assert bucket.consume() is False
        assert bucket.tokens == 0

    def test_consume_returns_false_when_insufficient(self, bucket: TokenBucket):
        bucket.tokens = 2
        assert bucket.consume(5) is False
        assert bucket.tokens == 2

    def test_consume_exact_tokens(self, bucket: TokenBucket):
        bucket.tokens = 3
        assert bucket.consume(3) is True
        assert bucket.tokens == 0


# ── TokenBucket refill ───────────────────────────────────────────────────────


class TestTokenBucketRefill:
    """TokenBucket must refill tokens over time."""

    def test_refill_adds_tokens(self, bucket: TokenBucket):
        bucket.tokens = 0
        bucket.refill(elapsed=1.0)  # 1 sec at rate 10 = +10 tokens
        assert bucket.tokens == 10

    def test_refill_caps_at_burst(self, bucket: TokenBucket):
        bucket.tokens = 15
        bucket.refill(elapsed=1.0)  # would add 10, but cap at 20
        assert bucket.tokens == 20

    def test_no_refill_when_full(self, bucket: TokenBucket):
        bucket.tokens = 20
        bucket.refill(elapsed=1.0)
        assert bucket.tokens == 20

    def test_refill_partial_second(self, bucket: TokenBucket):
        bucket.tokens = 0
        bucket.refill(elapsed=0.5)  # 0.5 sec at rate 10 = +5 tokens
        assert bucket.tokens == 5

    def test_refill_large_elapsed(self, bucket: TokenBucket):
        bucket.tokens = 0
        bucket.refill(elapsed=10.0)  # would add 100, but cap at 20
        assert bucket.tokens == 20


# ── Burst behavior ──────────────────────────────────────────────────────────


class TestBurst:
    """Burst allows short-term spikes up to burst limit."""

    def test_burst_allows_all_tokens_at_once(self, bucket: TokenBucket):
        """Burst allows consuming all burst tokens immediately."""
        for _ in range(20):
            assert bucket.consume() is True
        assert bucket.tokens == 0
        assert bucket.consume() is False

    def test_burst_recovers(self, bucket: TokenBucket):
        """After draining, bucket recovers over time."""
        bucket.tokens = 0
        bucket.refill(elapsed=1.0)  # +10 tokens
        for _ in range(10):
            assert bucket.consume() is True
        assert bucket.consume() is False  # drained again


# ── RateLimiter multi-device ────────────────────────────────────────────────


class TestRateLimiterMultiDevice:
    """RateLimiter must manage buckets independently per device."""

    def test_get_or_create_bucket(self, limiter: RateLimiter):
        bucket = limiter.get_bucket("R1")
        assert bucket.device_id == "R1"
        assert bucket.tokens == limiter.default_burst

    def test_same_device_returns_same_bucket(self, limiter: RateLimiter):
        b1 = limiter.get_bucket("R1")
        b2 = limiter.get_bucket("R1")
        assert b1 is b2

    def test_different_devices_different_buckets(self, limiter: RateLimiter):
        b1 = limiter.get_bucket("R1")
        b2 = limiter.get_bucket("R2")
        assert b1 is not b2

    def test_check_returns_true_within_limit(self, limiter: RateLimiter):
        assert limiter.check("R1") is True

    def test_check_returns_false_when_exceeded(self, limiter: RateLimiter):
        bucket = limiter.get_bucket("R1")
        bucket.tokens = 0
        assert limiter.check("R1") is False

    def test_independent_limits(self, limiter: RateLimiter):
        """One device being rate-limited should not affect others."""
        b1 = limiter.get_bucket("R1")
        b1.tokens = 0
        assert limiter.check("R1") is False
        assert limiter.check("R2") is True  # R2 has full tokens


# ── Reset ────────────────────────────────────────────────────────────────────


class TestReset:
    """Reset must restore buckets to full capacity."""

    def test_reset_bucket(self, limiter: RateLimiter):
        bucket = limiter.get_bucket("R1")
        bucket.tokens = 0
        limiter.reset("R1")
        assert bucket.tokens == limiter.default_burst

    def test_reset_all(self, limiter: RateLimiter):
        b1 = limiter.get_bucket("R1")
        b2 = limiter.get_bucket("R2")
        b1.tokens = 0
        b2.tokens = 0
        limiter.reset_all()
        assert b1.tokens == limiter.default_burst
        assert b2.tokens == limiter.default_burst


# ── Integration: write-only ──────────────────────────────────────────────────


class TestWriteOnly:
    """Rate limiting should apply to write operations only, not reads."""

    def test_is_write_allowed(self, limiter: RateLimiter):
        """Write operations consume tokens."""
        bucket = limiter.get_bucket("R1")
        initial = bucket.tokens
        limiter.check("R1", is_write=True)
        assert bucket.tokens == initial - 1

    def test_read_does_not_consume(self, limiter: RateLimiter):
        """Read operations should not consume tokens."""
        bucket = limiter.get_bucket("R1")
        initial = bucket.tokens
        limiter.check("R1", is_write=False)
        assert bucket.tokens == initial

    def test_write_blocked_when_exhausted(self, limiter: RateLimiter):
        """Write should be blocked when no tokens."""
        bucket = limiter.get_bucket("R1")
        bucket.tokens = 0
        assert limiter.check("R1", is_write=True) is False

    def test_read_always_allowed(self, limiter: RateLimiter):
        """Read should always be allowed, even when no tokens."""
        bucket = limiter.get_bucket("R1")
        bucket.tokens = 0
        assert limiter.check("R1", is_write=False) is True


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Handle edge cases gracefully."""

    def test_zero_rate(self):
        """Zero rate means no tokens ever added."""
        bucket = TokenBucket(device_id="R1", rate=0, burst=10)
        assert bucket.tokens == 10  # initial burst
        bucket.tokens = 0
        bucket.refill(elapsed=10.0)
        assert bucket.tokens == 0

    def test_zero_burst(self):
        """Zero burst means no capacity — refill still caps at 0."""
        bucket = TokenBucket(device_id="R1", rate=5, burst=0)
        assert bucket.tokens == 0
        assert bucket.consume() is False
        bucket.refill(elapsed=1.0)
        assert bucket.tokens == 0  # max_tokens=0, cannot hold tokens

    def test_custom_rate_and_burst(self):
        limiter = RateLimiter(default_rate=5, default_burst=10)
        bucket = limiter.get_bucket("R1")
        assert bucket.rate == 5
        assert bucket.max_tokens == 10

    def test_refill_before_consume(self, bucket: TokenBucket):
        """Refill should happen before token check."""
        bucket.tokens = 0
        bucket.refill(elapsed=1.0)
        assert bucket.tokens == 10
        assert bucket.consume() is True

    def test_string_representation(self, bucket: TokenBucket):
        s = str(bucket)
        assert "R1" in s
        assert "20" in s or "10" in s

    def test_limiter_string_representation(self, limiter: RateLimiter):
        s = str(limiter)
        assert "RateLimiter" in s
