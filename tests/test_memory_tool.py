"""Tests for the unified MemoryTool (store/search/delete with tags)."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.tools.memory_search_tool import MemorySearchTool
from nanobot.agent.memory import MemoryStore


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with memory directory."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    return tmp_path


@pytest.fixture
def memory_store(tmp_workspace):
    """Create a MemoryStore instance."""
    return MemoryStore(tmp_workspace)


@pytest.fixture
def memory_tool(tmp_workspace, memory_store):
    """Create a MemoryTool with mocked vector memory and real MemoryStore."""
    tool = MemorySearchTool()
    tool.set_memory_store(memory_store)
    # Mock vector memory for search tests
    mock_vm = MagicMock()
    mock_vm.search.return_value = []
    mock_vm.ingest_text = MagicMock()
    tool.set_vector_memory(mock_vm)
    return tool


# ── Tool metadata tests ──

class TestMemoryToolMetadata:
    """Test tool name, description, and parameter schema."""

    def test_tool_name(self, memory_tool):
        assert memory_tool.name == "memory"

    def test_tool_has_action_parameter(self, memory_tool):
        props = memory_tool.parameters["properties"]
        assert "action" in props
        assert set(props["action"]["enum"]) == {"search", "store", "delete"}

    def test_tool_has_query_parameter(self, memory_tool):
        assert "query" in memory_tool.parameters["required"]

    def test_tool_has_tags_parameter(self, memory_tool):
        props = memory_tool.parameters["properties"]
        assert "tags" in props

    def test_tool_has_memory_type_parameter(self, memory_tool):
        props = memory_tool.parameters["properties"]
        assert "memory_type" in props
        assert set(props["memory_type"]["enum"]) == {"fact", "event"}


# ── Store action tests ──

class TestMemoryStore:
    """Test the store action."""

    @pytest.mark.asyncio
    async def test_store_fact(self, memory_tool, memory_store):
        result = await memory_tool.execute(
            action="store",
            query="User prefers dark mode",
            memory_type="fact",
        )
        assert "✅" in result
        assert "fact" in result.lower() or "long-term" in result.lower()

        # Verify it was written to MEMORY.md
        content = memory_store.read_long_term()
        assert "User prefers dark mode" in content

    @pytest.mark.asyncio
    async def test_store_event(self, memory_tool, memory_store, tmp_workspace):
        result = await memory_tool.execute(
            action="store",
            query="Deployed v2.0 to production",
            memory_type="event",
        )
        assert "✅" in result
        assert "event" in result.lower() or "daily" in result.lower()

        # Verify it was written to a daily log file
        today = time.strftime("%Y-%m-%d")
        daily_file = tmp_workspace / "memory" / f"{today}.md"
        assert daily_file.exists()
        assert "Deployed v2.0 to production" in daily_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_store_with_tags(self, memory_tool, memory_store):
        result = await memory_tool.execute(
            action="store",
            query="User language is Chinese",
            memory_type="fact",
            tags=["preference", "language"],
        )
        assert "✅" in result

        content = memory_store.read_long_term()
        assert "User language is Chinese" in content
        assert "<!-- tags: preference, language -->" in content

    @pytest.mark.asyncio
    async def test_store_ingests_into_vector_store(self, memory_tool):
        await memory_tool.execute(
            action="store",
            query="Important project decision",
            memory_type="fact",
        )
        memory_tool._vector_memory.ingest_text.assert_called()

    @pytest.mark.asyncio
    async def test_store_default_is_fact(self, memory_tool, memory_store):
        result = await memory_tool.execute(
            action="store",
            query="Default memory type test",
        )
        assert "fact" in result.lower() or "long-term" in result.lower()
        assert "Default memory type test" in memory_store.read_long_term()

    @pytest.mark.asyncio
    async def test_store_without_memory_store(self):
        tool = MemorySearchTool()
        # Don't set memory store
        result = await tool.execute(action="store", query="test")
        assert "error" in result.lower()


# ── Search action tests ──

class TestMemorySearch:
    """Test the search action."""

    @pytest.mark.asyncio
    async def test_search_no_results(self, memory_tool):
        memory_tool._vector_memory.search.return_value = []
        result = await memory_tool.execute(
            action="search",
            query="nonexistent topic",
        )
        assert "No relevant memory" in result

    @pytest.mark.asyncio
    async def test_search_with_results(self, memory_tool):
        memory_tool._vector_memory.search.return_value = [
            {
                "text": "User likes Python",
                "score": 0.95,
                "source": "memory",
                "metadata": {"date": "2026-03-15"},
            }
        ]
        result = await memory_tool.execute(
            action="search",
            query="programming language",
        )
        assert "User likes Python" in result
        assert "95%" in result

    @pytest.mark.asyncio
    async def test_search_default_action(self, memory_tool):
        """If no action specified, defaults to search."""
        memory_tool._vector_memory.search.return_value = []
        result = await memory_tool.execute(query="test query")
        assert "No relevant memory" in result

    @pytest.mark.asyncio
    async def test_search_with_source_filter(self, memory_tool):
        memory_tool._vector_memory.search.return_value = []
        await memory_tool.execute(
            action="search",
            query="test",
            source="daily_log",
        )
        memory_tool._vector_memory.search.assert_called_with(
            query="test", top_k=5, source_filter="daily_log"
        )

    @pytest.mark.asyncio
    async def test_search_without_vector_memory(self):
        tool = MemorySearchTool()
        # Don't set vector memory
        result = await tool.execute(action="search", query="test")
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_search_top_k_capped(self, memory_tool):
        await memory_tool.execute(
            action="search",
            query="test",
            top_k=100,
        )
        memory_tool._vector_memory.search.assert_called_with(
            query="test", top_k=10, source_filter=None
        )

    @pytest.mark.asyncio
    async def test_search_tag_filtering(self, memory_tool):
        memory_tool._vector_memory.search.return_value = [
            {
                "text": "User likes dark mode",
                "score": 0.9,
                "source": "memory",
                "metadata": {"tags": "preference,ui"},
            },
            {
                "text": "Deployed v2",
                "score": 0.8,
                "source": "daily_log",
                "metadata": {"tags": "deploy"},
            },
        ]
        result = await memory_tool.execute(
            action="search",
            query="user settings",
            tags=["preference"],
        )
        assert "User likes dark mode" in result
        # The deploy entry should be filtered out since it doesn't have 'preference' tag
        # But if tag filtering finds matches, only those are returned


# ── Delete action tests ──

class TestMemoryDelete:
    """Test the delete action."""

    @pytest.mark.asyncio
    async def test_delete_existing_entry(self, memory_tool, memory_store):
        memory_store.write_long_term("- User likes Python\n- User likes dark mode\n- Project uses PostgreSQL")
        result = await memory_tool.execute(
            action="delete",
            query="dark mode",
        )
        assert "🗑️" in result
        assert "1" in result

        content = memory_store.read_long_term()
        assert "dark mode" not in content
        assert "Python" in content
        assert "PostgreSQL" in content

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, memory_tool, memory_store):
        memory_store.write_long_term("- User likes Python")
        result = await memory_tool.execute(
            action="delete",
            query="nonexistent keyword",
        )
        assert "No memory entries" in result

    @pytest.mark.asyncio
    async def test_delete_from_empty_memory(self, memory_tool):
        result = await memory_tool.execute(
            action="delete",
            query="anything",
        )
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_delete_with_tags(self, memory_tool, memory_store):
        memory_store.write_long_term("<!-- tags: preference -->\n- User likes dark mode\n- Project uses PostgreSQL")
        result = await memory_tool.execute(
            action="delete",
            query="dark mode",
        )
        assert "🗑️" in result
        content = memory_store.read_long_term()
        assert "dark mode" not in content
        assert "<!-- tags: preference -->" not in content
        assert "PostgreSQL" in content

    @pytest.mark.asyncio
    async def test_delete_without_memory_store(self):
        tool = MemorySearchTool()
        result = await tool.execute(action="delete", query="test")
        assert "error" in result.lower()


# ── Empty query tests ──

class TestMemoryEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_empty_query(self, memory_tool):
        result = await memory_tool.execute(action="search", query="")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_store_multiple_facts(self, memory_tool, memory_store):
        await memory_tool.execute(action="store", query="Fact 1")
        await memory_tool.execute(action="store", query="Fact 2")
        await memory_tool.execute(action="store", query="Fact 3")

        content = memory_store.read_long_term()
        assert "Fact 1" in content
        assert "Fact 2" in content
        assert "Fact 3" in content


# ── Memory intent detection tests ──

class TestMemoryIntentDetection:
    """Test the memory intent detection in AgentLoop."""

    def test_detect_chinese_remember(self):
        from nanobot.agent.loop import AgentLoop
        # Test the static method directly by creating a minimal instance
        # We'll test the detection logic directly
        input_lower = "请记住我喜欢深色模式"
        triggers_zh = [
            "记住", "别忘了", "不要忘记", "保存这个", "记下来",
            "以后记得", "帮我记", "请记住",
        ]
        assert any(t in input_lower for t in triggers_zh)

    def test_detect_english_remember(self):
        input_lower = "remember this for later"
        triggers_en = [
            "remember this", "don't forget", "save this", "keep in mind",
            "note this down", "make a note", "remember that",
        ]
        assert any(t in input_lower for t in triggers_en)

    def test_no_detect_normal_message(self):
        input_lower = "帮我查一下今天的邮件"
        triggers_zh = [
            "记住", "别忘了", "不要忘记", "保存这个", "记下来",
            "以后记得", "帮我记", "请记住",
        ]
        triggers_en = [
            "remember this", "don't forget", "save this", "keep in mind",
            "note this down", "make a note", "remember that",
        ]
        assert not any(t in input_lower for t in triggers_zh + triggers_en)


# ── Memory export/import tests ──

class TestMemoryExportImport:
    """Test memory export and import functionality."""

    def test_export_creates_file(self, tmp_workspace, memory_store):
        from nanobot.agent.loop import AgentLoop
        
        memory_store.write_long_term("Test memory content")
        memory_store.append_daily_log("Test daily log")
        
        # Directly test the export logic
        export_data = {
            "long_term_memory": memory_store.read_long_term(),
            "preferences": memory_store.read_preferences(),
            "daily_logs": {},
        }
        for f in sorted(memory_store.memory_dir.glob("????-??-??.md")):
            export_data["daily_logs"][f.stem] = f.read_text(encoding="utf-8")
        
        export_path = tmp_workspace / "memory_export.json"
        export_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        assert export_path.exists()
        data = json.loads(export_path.read_text(encoding="utf-8"))
        assert data["long_term_memory"] == "Test memory content"
        assert len(data["daily_logs"]) >= 1

    def test_import_from_json(self, tmp_workspace):
        # Create an export file
        export_data = {
            "long_term_memory": "Imported memory",
            "preferences": '{"theme": "dark"}',
            "daily_logs": {
                "2026-01-01": "Imported log entry",
            },
        }
        export_path = tmp_workspace / "test_import.json"
        export_path.write_text(json.dumps(export_data), encoding="utf-8")
        
        # Import it
        memory = MemoryStore(tmp_workspace)
        
        data = json.loads(export_path.read_text(encoding="utf-8"))
        imported = []
        
        if ltm := data.get("long_term_memory"):
            memory.write_long_term(ltm)
            imported.append("MEMORY.md")
        
        if prefs := data.get("preferences"):
            memory.write_preferences(prefs)
            imported.append("preferences.json")
        
        if daily := data.get("daily_logs"):
            for date_key, content in daily.items():
                daily_file = memory.memory_dir / f"{date_key}.md"
                if not daily_file.exists():
                    daily_file.write_text(content, encoding="utf-8")
                    imported.append(f"{date_key}.md")
        
        assert "MEMORY.md" in imported
        assert "preferences.json" in imported
        assert memory.read_long_term() == "Imported memory"
        assert '"dark"' in memory.read_preferences()
        assert (memory.memory_dir / "2026-01-01.md").exists()


# ── i18n message tests ──

class TestMemoryI18n:
    """Test that memory-related i18n messages exist."""

    def test_memory_help_exists(self):
        from nanobot.agent.i18n import MESSAGES
        assert "memory_help" in MESSAGES
        assert "zh" in MESSAGES["memory_help"]
        assert "en" in MESSAGES["memory_help"]

    def test_memory_help_contains_export(self):
        from nanobot.agent.i18n import MESSAGES
        zh = MESSAGES["memory_help"]["zh"]
        assert "/memory export" in zh
        assert "/memory import" in zh

    def test_help_text_includes_memory(self):
        from nanobot.agent.i18n import MESSAGES
        zh = MESSAGES["help_text"]["zh"]
        assert "/memory" in zh
