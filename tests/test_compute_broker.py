"""Tests for ComputeBroker offloading."""

import asyncio
import time

import pytest

from nanobot.compute import ComputeBroker, run_cpu_heavy, shutdown_broker


# --- picklable top-level helpers (required by ProcessPoolExecutor) ---

def _cpu_spin(n: int) -> int:
    """Simulate CPU-bound work by summing a range."""
    return sum(range(n))


def _always_fail() -> None:
    raise ValueError("intentional failure")


# --- Tests ---

@pytest.fixture(autouse=True)
def _reset_broker():
    """Ensure the singleton is clean before/after each test."""
    # Reset before
    ComputeBroker._instance = None
    yield
    # Cleanup after
    try:
        shutdown_broker(wait=False)
    except Exception:
        pass
    ComputeBroker._instance = None


@pytest.mark.asyncio
async def test_basic_offload():
    """run_cpu_heavy should return the correct result."""
    result = await run_cpu_heavy(_cpu_spin, 100_000)
    assert result == sum(range(100_000))


@pytest.mark.asyncio
async def test_heartbeat_not_blocked():
    """While a CPU task runs in the pool, the event loop should stay responsive."""
    heartbeats: list[float] = []

    async def heartbeat():
        for _ in range(5):
            heartbeats.append(time.monotonic())
            await asyncio.sleep(0.1)

    # Run heartbeat and CPU task concurrently
    await asyncio.gather(heartbeat(), run_cpu_heavy(_cpu_spin, 5_000_000))

    # Heartbeats should have been recorded at ~100ms intervals
    assert len(heartbeats) == 5
    for i in range(1, len(heartbeats)):
        gap = heartbeats[i] - heartbeats[i - 1]
        # Allow generous tolerance (should be ~0.1s, fail if >2s)
        assert gap < 2.0, f"Heartbeat gap {gap:.2f}s — event loop was blocked!"


@pytest.mark.asyncio
async def test_error_propagation():
    """Exceptions raised inside the pool should propagate to the caller."""
    with pytest.raises(ValueError, match="intentional failure"):
        await run_cpu_heavy(_always_fail)


@pytest.mark.asyncio
async def test_graceful_after_shutdown():
    """After shutdown, run_cpu_heavy should fall back to synchronous execution."""
    # Use the broker once
    result1 = await run_cpu_heavy(_cpu_spin, 100)
    assert result1 == sum(range(100))

    # Shut it down
    shutdown_broker(wait=True)

    # Should still work (graceful fallback)
    result2 = await run_cpu_heavy(_cpu_spin, 100)
    assert result2 == sum(range(100))
