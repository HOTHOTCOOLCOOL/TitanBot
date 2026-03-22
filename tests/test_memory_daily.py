"""Tests for P0-B: Memory System with Daily Logs."""

import pytest
from datetime import date, timedelta
from pathlib import Path

from nanobot.agent.memory import MemoryStore


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path)


class TestDailyLog:
    def test_append_creates_file(self, memory: MemoryStore):
        memory.append_daily_log("Task: searched weather")
        today = date.today().isoformat()
        daily_file = memory.memory_dir / f"{today}.md"
        assert daily_file.exists()
        assert "searched weather" in daily_file.read_text(encoding="utf-8")

    def test_append_multiple_entries(self, memory: MemoryStore):
        memory.append_daily_log("Entry 1")
        memory.append_daily_log("Entry 2")
        today = date.today().isoformat()
        content = (memory.memory_dir / f"{today}.md").read_text(encoding="utf-8")
        assert "Entry 1" in content
        assert "Entry 2" in content

    def test_read_recent_includes_today(self, memory: MemoryStore):
        memory.append_daily_log("Today's task")
        result = memory.read_recent_daily(days=1)
        assert "Today's task" in result
        assert date.today().isoformat() in result

    def test_read_recent_empty(self, memory: MemoryStore):
        result = memory.read_recent_daily(days=2)
        assert result == ""


class TestMemoryContext:
    def test_context_empty(self, memory: MemoryStore):
        assert memory.get_memory_context() == ""

    def test_context_with_long_term_only(self, memory: MemoryStore):
        memory.write_long_term("User prefers Chinese.")
        ctx = memory.get_memory_context()
        assert "Memory Note" in ctx
        assert "L2 memory" in ctx

    def test_context_with_daily_only(self, memory: MemoryStore):
        memory.append_daily_log("Analyzed sales report")
        ctx = memory.get_memory_context()
        assert "Recent Activity" in ctx
        assert "Analyzed sales report" in ctx

    def test_context_with_both(self, memory: MemoryStore):
        memory.write_long_term("User prefers concise replies.")
        memory.append_daily_log("Created PPT for Q4 review")
        ctx = memory.get_memory_context()
        assert "Memory Note" in ctx
        assert "L2 memory" in ctx
        assert "Recent Activity" in ctx
        assert "PPT" in ctx


class TestHistory:
    def test_append_and_read(self, memory: MemoryStore):
        memory.append_history("[2026-02-24] User asked about weather")
        assert memory.history_file.exists()
        content = memory.history_file.read_text(encoding="utf-8")
        assert "weather" in content
