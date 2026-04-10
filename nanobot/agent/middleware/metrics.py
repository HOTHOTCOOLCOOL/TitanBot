"""Phase 41 (P41-2): MetricsMiddleware — outermost timing layer.

Records per-turn iteration elapsed time using the existing MetricsCollector.
"""

from __future__ import annotations

import time

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext
from nanobot.utils.metrics import metrics


class MetricsMiddleware(AgentMiddleware):
    """Outermost layer: records iteration timing."""

    async def pre_process(self, ctx: TurnContext) -> None:
        ctx._metrics_start = time.monotonic()  # type: ignore[attr-defined]

    async def post_process(self, ctx: TurnContext) -> None:
        start = getattr(ctx, '_metrics_start', None)
        if start is not None:
            elapsed_ms = (time.monotonic() - start) * 1000
            metrics._record_timing("loop_iteration_ms", elapsed_ms)
