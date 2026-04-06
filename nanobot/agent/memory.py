"""Memory system for persistent agent memory.

OpenClaw-inspired design: plain Markdown files as source of truth.
- MEMORY.md: curated long-term facts (preferences, configs, decisions)
- memory/YYYY-MM-DD.md: daily activity logs (append-only)
- HISTORY.md: grep-searchable conversation summaries
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

from loguru import logger
from nanobot.utils.helpers import ensure_dir


# Phase 40B: Maximum number of rolling MEMORY.md backups
_MAX_BACKUPS: int = 5


class MemoryStore:
    """File-based memory: MEMORY.md (curated facts) + daily logs + HISTORY.md."""

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.preferences_file = self.memory_dir / "preferences.json"
        self.history_file = self.memory_dir / "HISTORY.md"

    def read_long_term(self) -> str:
        """Read the raw L2 MEMORY.md file (for RAG or consolidation)."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """Write to the raw L2 MEMORY.md file (with rolling backup).

        Phase 40B-2: Rotates up to _MAX_BACKUPS numbered .bak files before
        overwriting, protecting against LLM hallucination corrupting memory.
        """
        self._rotate_backup()
        self.memory_file.write_text(content, encoding="utf-8")

    # ── Phase 40B-2: Rolling Backup ──

    def _rotate_backup(self) -> None:
        """Rotate MEMORY.md backups before overwrite (keep latest N copies).

        Naming scheme: MEMORY.md.bak.1 (newest) → MEMORY.md.bak.N (oldest).
        Skips backup if the file does not exist or is empty.
        """
        if not self.memory_file.exists():
            return
        try:
            existing = self.memory_file.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(f"Phase 40B: Cannot read MEMORY.md for backup: {e}")
            return
        if not existing.strip():
            return  # Don't backup empty/whitespace-only files

        try:
            # Delete the oldest backup if it exists
            oldest = self.memory_dir / f"MEMORY.md.bak.{_MAX_BACKUPS}"
            if oldest.exists():
                oldest.unlink()

            # Shift backups: .bak.(N-1) → .bak.N, ... .bak.1 → .bak.2
            for i in range(_MAX_BACKUPS, 1, -1):
                src = self.memory_dir / f"MEMORY.md.bak.{i - 1}"
                dst = self.memory_dir / f"MEMORY.md.bak.{i}"
                if src.exists():
                    src.rename(dst)

            # Copy current file → .bak.1 (copy, not move, so write_long_term can overwrite original)
            bak1 = self.memory_dir / f"MEMORY.md.bak.1"
            shutil.copy2(str(self.memory_file), str(bak1))
            logger.debug("Phase 40B: MEMORY.md backup rotated successfully")
        except OSError as e:
            # Backup failure is non-fatal — log and continue
            logger.warning(f"Phase 40B: MEMORY.md backup rotation failed: {e}")

    def read_preferences(self) -> str:
        """Read the L1 distilled preferences.json."""
        if self.preferences_file.exists():
            return self.preferences_file.read_text(encoding="utf-8")
        return ""

    def write_preferences(self, content: str) -> None:
        """Write the distilled JSON to preferences.json."""
        self.preferences_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    # ── Daily Logs (OpenClaw-inspired) ──

    def append_daily_log(self, entry: str) -> None:
        """Append to today's daily log file (memory/YYYY-MM-DD.md)."""
        today = date.today().isoformat()
        daily_file = self.memory_dir / f"{today}.md"
        with open(daily_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def read_recent_daily(self, days: int = 2) -> str:
        """Read recent daily logs (today + N-1 previous days).

        Returns concatenated content from most recent daily log files.
        """
        parts = []
        today = date.today()
        for i in range(days):
            d = today - timedelta(days=i)
            daily_file = self.memory_dir / f"{d.isoformat()}.md"
            if daily_file.exists():
                content = daily_file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"### {d.isoformat()}\n{content}")
        return "\n\n".join(parts)

    # ── Context Building ──

    def get_memory_context(self) -> str:
        """Build injected memory context: L1 distilled preferences + recent daily logs.

        This is injected into the system prompt to give the LLM
        awareness of core user preferences and recent activity without blowing up the context window.
        """
        parts = []
        preferences = self.read_preferences()
        if preferences:
            parts.append(f"## Distilled Core Preferences (L1 Memory)\n```json\n{preferences}\n```")
        elif self.read_long_term():
            parts.append(f"## Memory Note\nYou have L2 memory in {self.memory_file}, but it has not been distilled yet.")
        daily = self.read_recent_daily(days=2)
        if daily:
            parts.append(f"## Recent Activity\n{daily}")
        return "\n\n".join(parts) if parts else ""

