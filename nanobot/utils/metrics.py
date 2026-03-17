"""Lightweight performance metrics collector (no external dependencies).

Usage:
    from nanobot.utils.metrics import metrics

    # Record a timing
    with metrics.timer("llm_call"):
        result = await provider.chat(...)

    # Record a count
    metrics.increment("tool_executions")

    # Record token usage
    metrics.record_tokens(prompt=500, completion=200, total=700)

    # Get summary
    print(metrics.report())
"""

__all__ = ["metrics", "get_metrics", "MetricsCollector"]

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _TimingStat:
    """Aggregated timing statistics for a named operation."""

    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    def record(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_ms += elapsed_ms
        self.min_ms = min(self.min_ms, elapsed_ms)
        self.max_ms = max(self.max_ms, elapsed_ms)


@dataclass
class _TokenStat:
    """Aggregated token usage statistics."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class _Timer:
    """Context manager for timing a block of code."""

    def __init__(self, collector: "MetricsCollector", name: str):
        self._collector = collector
        self._name = name
        self._start: float = 0.0

    def __enter__(self) -> "_Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        self._collector._record_timing(self._name, elapsed_ms)


class MetricsCollector:
    """Thread-safe, lightweight performance metrics collector.

    Tracks:
    - Named timings (with min/max/avg/count)
    - Named counters
    - Token usage (prompt/completion/total)

    No external dependencies. All metrics are in-memory only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timings: dict[str, _TimingStat] = defaultdict(_TimingStat)
        self._counters: dict[str, int] = defaultdict(int)
        self._tokens = _TokenStat()
        self._start_time: float = time.monotonic()

    def timer(self, name: str) -> _Timer:
        """Return a context manager that records the elapsed time under *name*.

        Example:
            with metrics.timer("llm_call"):
                await provider.chat(...)
        """
        return _Timer(self, name)

    def _record_timing(self, name: str, elapsed_ms: float) -> None:
        with self._lock:
            self._timings[name].record(elapsed_ms)

    def increment(self, name: str, delta: int = 1) -> None:
        """Increment a named counter."""
        with self._lock:
            self._counters[name] += delta

    def record_tokens(
        self, prompt: int = 0, completion: int = 0, total: int = 0,
    ) -> None:
        """Record token usage from an LLM call.

        Args:
            prompt: Number of prompt (input) tokens.
            completion: Number of completion (output) tokens.
            total: Total tokens (if 0, computed as prompt + completion).
        """
        with self._lock:
            self._tokens.calls += 1
            self._tokens.prompt_tokens += prompt
            self._tokens.completion_tokens += completion
            self._tokens.total_tokens += total or (prompt + completion)

    def get_timing(self, name: str) -> dict[str, Any]:
        """Get timing stats for a named operation."""
        with self._lock:
            stat = self._timings.get(name)
            if not stat or stat.count == 0:
                return {"count": 0}
            return {
                "count": stat.count,
                "avg_ms": round(stat.avg_ms, 1),
                "min_ms": round(stat.min_ms, 1),
                "max_ms": round(stat.max_ms, 1),
                "total_ms": round(stat.total_ms, 1),
            }

    def get_counter(self, name: str) -> int:
        """Get current value of a named counter."""
        with self._lock:
            return self._counters.get(name, 0)

    def get_tokens(self) -> dict[str, int]:
        """Get cumulative token usage stats."""
        with self._lock:
            return {
                "calls": self._tokens.calls,
                "prompt_tokens": self._tokens.prompt_tokens,
                "completion_tokens": self._tokens.completion_tokens,
                "total_tokens": self._tokens.total_tokens,
            }

    def uptime_seconds(self) -> float:
        """Return seconds since the MetricsCollector was created."""
        return time.monotonic() - self._start_time

    def report(self) -> str:
        """Return a human-readable summary of all collected metrics."""
        lines: list[str] = []
        with self._lock:
            if self._timings:
                lines.append("── Timings ──")
                for name, stat in sorted(self._timings.items()):
                    if stat.count == 0:
                        continue
                    lines.append(
                        f"  {name}: {stat.count}x, "
                        f"avg={stat.avg_ms:.0f}ms, "
                        f"min={stat.min_ms:.0f}ms, "
                        f"max={stat.max_ms:.0f}ms"
                    )
            if self._counters:
                lines.append("── Counters ──")
                for name, val in sorted(self._counters.items()):
                    lines.append(f"  {name}: {val}")
            if self._tokens.calls > 0:
                t = self._tokens
                lines.append("── Tokens ──")
                lines.append(
                    f"  LLM calls: {t.calls}, "
                    f"prompt: {t.prompt_tokens}, "
                    f"completion: {t.completion_tokens}, "
                    f"total: {t.total_tokens}"
                )
        uptime = self.uptime_seconds()
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        lines.insert(0, f"── Uptime: {hours}h {minutes}m {seconds}s ──")
        return "\n".join(lines) if lines else "(no metrics collected)"

    def reset(self) -> None:
        """Clear all metrics (uptime is NOT reset)."""
        with self._lock:
            self._timings.clear()
            self._counters.clear()
            self._tokens = _TokenStat()


# Global singleton
metrics = MetricsCollector()


def get_metrics() -> dict:
    """Return all metrics as a JSON-serializable dict (used by Dashboard API)."""
    with metrics._lock:
        timings = {}
        for name, stat in metrics._timings.items():
            if stat.count > 0:
                timings[name] = {
                    "count": stat.count,
                    "avg_ms": round(stat.avg_ms, 1),
                    "min_ms": round(stat.min_ms, 1),
                    "max_ms": round(stat.max_ms, 1),
                    "total_ms": round(stat.total_ms, 1),
                }
        counters = dict(metrics._counters)
        tokens = {
            "calls": metrics._tokens.calls,
            "prompt_tokens": metrics._tokens.prompt_tokens,
            "completion_tokens": metrics._tokens.completion_tokens,
            "total_tokens": metrics._tokens.total_tokens,
        }
    return {
        "uptime_seconds": round(metrics.uptime_seconds(), 1),
        "timings": timings,
        "counters": counters,
        "tokens": tokens,
    }

