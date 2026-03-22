"""Tests for KnowledgeWorkflow: key extraction, matching, and command recognition."""

import pytest
from pathlib import Path

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.task_knowledge import TaskKnowledgeStore


# ── Fixtures ──


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with knowledge store."""
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def kw(tmp_workspace: Path) -> KnowledgeWorkflow:
    """Create a KnowledgeWorkflow with no LLM provider (fallback mode)."""
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


@pytest.fixture
def kw_with_tasks(tmp_workspace: Path) -> KnowledgeWorkflow:
    """Create a KnowledgeWorkflow with pre-populated knowledge base."""
    store = TaskKnowledgeStore(tmp_workspace)
    store.add_task(
        key="分析上周发给老板的报表邮件",
        description="分析业绩报表",
        steps=[{"tool": "outlook", "args": {"query": "report"}}],
        params={},
        result_summary="已分析3封报表邮件",
    )
    store.add_task(
        key="search weather forecast",
        description="Search for weather info",
        steps=[{"tool": "web_search", "args": {"query": "weather"}}],
        params={},
        result_summary="Today's forecast: sunny",
    )
    store.add_task(
        key="send daily summary email",
        description="Send a summary email",
        steps=[
            {"tool": "outlook", "args": {"action": "search"}},
            {"tool": "outlook", "args": {"action": "send"}},
        ],
        params={},
        result_summary="Email sent successfully",
    )
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


# ── Key Extraction Tests (fallback mode, no LLM) ──


class TestExtractKey:
    @pytest.mark.asyncio
    async def test_fallback_key_short_text(self, kw: KnowledgeWorkflow):
        """Short requests are returned as-is."""
        key = await kw.extract_key("Hello world")
        assert key == "Hello world"

    @pytest.mark.asyncio
    async def test_fallback_key_chinese_truncation(self, kw: KnowledgeWorkflow):
        """Chinese text is truncated to 50 chars."""
        long_cn = "分析" * 30  # 60 chars
        key = await kw.extract_key(long_cn)
        assert len(key) <= 50

    @pytest.mark.asyncio
    async def test_fallback_key_english_truncation(self, kw: KnowledgeWorkflow):
        """English text is truncated to 200 chars."""
        long_en = "analyze " * 30  # 240 chars
        key = await kw.extract_key(long_en)
        assert len(key) <= 200


# ── Knowledge Matching Tests ──


class TestMatchKnowledge:
    def test_exact_match(self, kw_with_tasks: KnowledgeWorkflow):
        """Exact key match returns the task."""
        match = kw_with_tasks.match_knowledge("分析上周发给老板的报表邮件")
        assert match is not None
        assert match["key"] == "分析上周发给老板的报表邮件"

    def test_exact_match_case_insensitive(self, kw_with_tasks: KnowledgeWorkflow):
        """Matching is case-insensitive."""
        match = kw_with_tasks.match_knowledge("Search Weather Forecast")
        assert match is not None
        assert match["key"] == "search weather forecast"

    def test_substring_match(self, kw_with_tasks: KnowledgeWorkflow):
        """Substring match works when one key contains the other."""
        match = kw_with_tasks.match_knowledge("weather forecast")
        assert match is not None
        assert "weather" in match["key"]

    def test_word_similarity_match(self, kw_with_tasks: KnowledgeWorkflow):
        """Common-word similarity finds related tasks."""
        match = kw_with_tasks.match_knowledge("send daily summary email report")
        assert match is not None
        assert "email" in match["key"]

    def test_no_match(self, kw_with_tasks: KnowledgeWorkflow):
        """Completely unrelated key returns None."""
        match = kw_with_tasks.match_knowledge("compile python project")
        assert match is None

    def test_empty_knowledge_base(self, kw: KnowledgeWorkflow):
        """Empty knowledge base always returns None."""
        match = kw.match_knowledge("anything")
        assert match is None


# ── Command Recognition Tests ──


class TestCommandRecognition:
    # Use commands
    @pytest.mark.parametrize("text", [
        "use", "USE", "reuse", "直接用", "用知识库", "yes", "用", "使用知识库",
    ])
    def test_is_use_command(self, text: str):
        assert KnowledgeWorkflow.is_use_command(text) is True

    @pytest.mark.parametrize("text", ["no", "redo", "hello", "不用"])
    def test_is_not_use_command(self, text: str):
        assert KnowledgeWorkflow.is_use_command(text) is False

    # Redo commands
    @pytest.mark.parametrize("text", [
        "redo", "REDO", "re-execute", "重新执行", "重新", "rerun", "again",
    ])
    def test_is_redo_command(self, text: str):
        assert KnowledgeWorkflow.is_redo_command(text) is True

    @pytest.mark.parametrize("text", ["use", "hello", "no"])
    def test_is_not_redo_command(self, text: str):
        assert KnowledgeWorkflow.is_redo_command(text) is False

    # Save confirm commands
    @pytest.mark.parametrize("text", [
        "yes", "YES", "ok", "save", "是", "好", "是的", "好的", "保存", "y",
    ])
    def test_is_save_confirm(self, text: str):
        assert KnowledgeWorkflow.is_save_confirm(text) is True

    @pytest.mark.parametrize("text", ["no", "cancel", "不", "算了"])
    def test_is_not_save_confirm(self, text: str):
        assert KnowledgeWorkflow.is_save_confirm(text) is False


# ── Save / Update Tests ──


class TestSaveToKnowledge:
    @pytest.mark.asyncio
    async def test_save_new_task(self, kw: KnowledgeWorkflow):
        """Save a brand new task to knowledge base."""
        result = await kw.save_to_knowledge(
            key="test_task",
            steps=[{"tool": "exec", "args": {"cmd": "ls"}}],
            user_request="list files",
            result_summary="Listed 5 files",
        )
        assert result is True

        # Verify it's findable
        match = kw.match_knowledge("test_task")
        assert match is not None
        assert match["key"] == "test_task"

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, kw_with_tasks: KnowledgeWorkflow):
        """Saving with an existing key updates the entry."""
        result = await kw_with_tasks.save_to_knowledge(
            key="search weather forecast",
            steps=[{"tool": "web_search", "args": {"query": "weather tomorrow"}}],
            user_request="search weather forecast",
            result_summary="Tomorrow: rainy",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_save_without_store_returns_false(self):
        """Save fails gracefully without a knowledge store."""
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        result = await kw.save_to_knowledge(
            key="anything",
            steps=[],
            user_request="test",
        )
        assert result is False


# ── Prompt Formatting Tests ──


class TestPromptFormatting:
    def test_format_match_prompt_en(self):
        match = {"key": "weather_search"}
        prompt = KnowledgeWorkflow.format_match_prompt(match, lang="en")
        assert "weather_search" in prompt
        assert "use" in prompt.lower() or "redo" in prompt.lower()

    def test_format_match_prompt_zh(self):
        match = {"key": "天气搜索"}
        prompt = KnowledgeWorkflow.format_match_prompt(match, lang="zh")
        assert "天气搜索" in prompt
        assert "直接用" in prompt or "重新执行" in prompt or "知识库" in prompt

    def test_format_save_prompt_en(self):
        prompt = KnowledgeWorkflow.format_save_prompt(lang="en")
        assert "save" in prompt.lower() or "knowledge" in prompt.lower()

    def test_format_save_prompt_zh(self):
        prompt = KnowledgeWorkflow.format_save_prompt(lang="zh")
        assert "知识库" in prompt or "保存" in prompt

    def test_format_save_confirmed_en(self):
        msg = KnowledgeWorkflow.format_save_confirmed(lang="en")
        assert "✅" in msg

    def test_format_save_confirmed_zh(self):
        msg = KnowledgeWorkflow.format_save_confirmed(lang="zh")
        assert "✅" in msg
