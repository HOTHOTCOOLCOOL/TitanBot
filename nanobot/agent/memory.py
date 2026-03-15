"""Memory system for persistent agent memory.

OpenClaw-inspired design: plain Markdown files as source of truth.
- MEMORY.md: curated long-term facts (preferences, configs, decisions)
- memory/YYYY-MM-DD.md: daily activity logs (append-only)
- HISTORY.md: grep-searchable conversation summaries
"""

from datetime import date, timedelta
from pathlib import Path

from nanobot.utils.helpers import ensure_dir


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
        """Write to the raw L2 MEMORY.md file."""
        self.memory_file.write_text(content, encoding="utf-8")

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

