"""Phase 37: Execution Trace Archive — developer-only debug dump.

Saves raw execution traces to ``memory/traces/`` for offline human
inspection.  **NOT consumed by the Agent at runtime.**  The Agent-facing
knowledge path goes through the enriched Post-Mortem experience stored
in the Experience Bank (see ``_extract_trace_postmortem`` in loop.py).

Design:
  • Pure append-only file writes; dump failure never affects the main loop.
  • Auto-evicts oldest traces beyond ``MAX_TRACES``.
  • No index file, no retrieval system, no Agent-side filesystem access.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class TraceArchive:
    """Developer-only raw trace dumper.

    Not referenced by VerificationLayer or L0 injection — purely for
    human debugging of complex multi-step failures (Browser/RPA/exec).
    """

    MAX_TRACES = 30
    MAX_TRACE_SIZE = 200_000  # 200 KB per trace file

    def __init__(self, workspace: Path):
        self.traces_dir = workspace / "memory" / "traces"

    def dump_debug_trace(
        self,
        request_text: str,
        tool_calls_with_args: list[dict[str, Any]],
        action_log: list[dict[str, Any]],
        final_content: str,
    ) -> Path | None:
        """Dump a raw execution trace for offline developer inspection.

        Args:
            request_text: The user's original request.
            tool_calls_with_args: Full tool call chain from the agent loop.
            action_log: Phase 33 action history log (browser/rpa entries).
            final_content: The agent's final response text.

        Returns:
            Path to the created trace file, or None on failure.
        """
        try:
            self.traces_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            trace_file = self.traces_dir / f"trace_{ts}.json"

            trace = {
                "timestamp": datetime.now().isoformat(),
                "request": request_text[:500],
                "tool_chain": tool_calls_with_args[-10:],
                "action_log": action_log[-10:],
                "final_content": final_content[:500],
            }

            content = json.dumps(trace, indent=2, ensure_ascii=False)
            if len(content) > self.MAX_TRACE_SIZE:
                content = content[: self.MAX_TRACE_SIZE]

            trace_file.write_text(content, encoding="utf-8")
            self._cleanup()
            logger.info(f"Phase 37: Debug trace saved to {trace_file.name}")
            return trace_file

        except Exception as e:
            # Fail-open: dump failure must never affect the main agent loop
            logger.error(f"Phase 37: Failed to dump debug trace: {e}")
            return None

    def _cleanup(self) -> None:
        """Evict oldest traces beyond MAX_TRACES."""
        try:
            traces = sorted(self.traces_dir.glob("trace_*.json"))
            while len(traces) > self.MAX_TRACES:
                oldest = traces.pop(0)
                oldest.unlink(missing_ok=True)
                logger.debug(f"Phase 37: Evicted old trace {oldest.name}")
        except Exception as e:
            logger.debug(f"Phase 37: Trace cleanup error (non-critical): {e}")
