"""
BFF Gateway - In-Memory Token Bucket Rate Limiter

Limits requests per user_id to BFF_RATE_LIMIT_RPM requests per minute.
Uses a sliding window token bucket backed by a simple asyncio-compatible dict.

TODO(Prod Phase 3): Replace with Redis-backed distributed rate limiter when
  BFF scales to multiple instances behind a load balancer.
"""

import asyncio
import time
import os

from loguru import logger


class RateLimiter:
    """
    Per-user token bucket rate limiter (in-memory, single-process).

    Each user gets BFF_RATE_LIMIT_RPM tokens per minute, refilled continuously.
    """

    def __init__(self, rpm: int | None = None):
        self._rpm = rpm or int(os.getenv("BFF_RATE_LIMIT_RPM", "60"))
        # user_id -> (token_count: float, last_refill_time: float)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, user_id: str) -> bool:
        """
        Returns True if the request is allowed, False if rate-limited.
        Thread-safe via asyncio lock.
        """
        async with self._lock:
            now = time.monotonic()
            tokens, last_refill = self._buckets.get(user_id, (float(self._rpm), now))

            # Refill tokens based on elapsed time
            elapsed = now - last_refill
            refill_rate = self._rpm / 60.0  # tokens per second
            tokens = min(float(self._rpm), tokens + elapsed * refill_rate)

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[user_id] = (tokens, now)
                return True
            else:
                self._buckets[user_id] = (tokens, now)
                logger.warning(f"[RateLimit] User '{user_id}' exceeded {self._rpm} RPM limit")
                return False
