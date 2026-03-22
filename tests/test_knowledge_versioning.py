"""Tests for Phase 9: Knowledge Versioning, Auto-Merge, and Skill Evolution."""

import pytest
from pathlib import Path

from nanobot.agent.task_knowledge import TaskKnowledgeStore, tokenize_key
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow


# ── Fixtures ──


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def store(tmp_workspace: Path) -> TaskKnowledgeStore:
    s = TaskKnowledgeStore(tmp_workspace)
    s.add_task(
        key="分析上周报表邮件",
        description="分析业绩报表",
        steps=[{"tool": "outlook", "args": {"query": "report"}}],
        params={},
        result_summary="已分析3封报表邮件",
        steps_detail=[
            {"tool": "outlook", "args": {"query": "weekly report"}, "result": "3 emails found"},
        ],
    )
    s.add_task(
        key="search weather forecast",
        description="Search for weather info",
        steps=[{"tool": "web_search", "args": {"query": "weather"}}],
        params={},
        result_summary="Today: sunny",
    )
    return s


@pytest.fixture
def kw(tmp_workspace: Path) -> KnowledgeWorkflow:
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


@pytest.fixture
def kw_with_tasks(tmp_workspace: Path, store: TaskKnowledgeStore) -> KnowledgeWorkflow:
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


# ═══════════════════════════════════════════════════════════════════════
# P0: 版本化 + 自动合并
# ═══════════════════════════════════════════════════════════════════════


class TestTokenizeKey:
    def test_english_tokenization(self):
        tokens = tokenize_key("search weather forecast")
        assert "search" in tokens
        assert "weather" in tokens
        assert "forecast" in tokens

    def test_short_words_filtered(self):
        tokens = tokenize_key("I am a test")
        # Single-char words filtered
        assert "I" not in tokens and "a" not in tokens

    def test_chinese_tokenization(self):
        tokens = tokenize_key("分析上周的报表邮件")
        assert len(tokens) > 0  # jieba should produce tokens


class TestVersionField:
    def test_new_task_has_version_1(self, store: TaskKnowledgeStore):
        task = store.find_task("分析上周报表邮件")
        assert task is not None
        assert task.get("version") == 1

    def test_version_persists_after_reload(self, tmp_workspace: Path, store: TaskKnowledgeStore):
        # Force reload
        store2 = TaskKnowledgeStore(tmp_workspace)
        task = store2.find_task("分析上周报表邮件")
        assert task["version"] == 1


class TestFindSimilarTask:
    def test_similar_chinese(self, store: TaskKnowledgeStore):
        similar = store.find_similar_task("分析上周的报表邮件")
        assert similar is not None
        assert similar["key"] == "分析上周报表邮件"

    def test_similar_english(self, store: TaskKnowledgeStore):
        similar = store.find_similar_task("search weather report")
        assert similar is not None
        assert "weather" in similar["key"]

    def test_no_match(self, store: TaskKnowledgeStore):
        similar = store.find_similar_task("compile python project")
        assert similar is None

    def test_empty_store(self, tmp_workspace: Path):
        empty_store = TaskKnowledgeStore(tmp_workspace)
        # Remove all tasks
        empty_store._tasks = []
        assert empty_store.find_similar_task("anything") is None

    def test_threshold(self, store: TaskKnowledgeStore):
        # Very high threshold should not match
        similar = store.find_similar_task("search weather report", threshold=0.99)
        assert similar is None


class TestMergeTask:
    def test_version_increments(self, store: TaskKnowledgeStore):
        result = store.merge_task(
            "分析上周报表邮件",
            new_steps=[{"tool": "outlook", "args": {"query": "monthly"}}],
            new_result_summary="分析了5封月报",
        )
        assert result is True
        task = store.find_task("分析上周报表邮件")
        assert task["version"] == 2

    def test_steps_updated(self, store: TaskKnowledgeStore):
        new_steps = [{"tool": "web_fetch", "args": {"url": "http://example.com"}}]
        store.merge_task("search weather forecast", new_steps=new_steps)
        task = store.find_task("search weather forecast")
        assert task["steps"] == new_steps

    def test_result_summary_updated(self, store: TaskKnowledgeStore):
        store.merge_task("search weather forecast", new_result_summary="Tomorrow: rainy")
        task = store.find_task("search weather forecast")
        assert task["result_summary"] == "Tomorrow: rainy"

    def test_preserves_success_fail_counts(self, store: TaskKnowledgeStore):
        # Record some outcomes first
        store.record_success("search weather forecast")
        store.record_failure("search weather forecast")
        task_before = store.find_task("search weather forecast")
        sc_before = task_before["success_count"]
        fc_before = task_before["fail_count"]

        store.merge_task("search weather forecast", new_result_summary="Updated")
        task_after = store.find_task("search weather forecast")
        assert task_after["success_count"] == sc_before
        assert task_after["fail_count"] == fc_before

    def test_use_count_increments(self, store: TaskKnowledgeStore):
        task_before = store.find_task("search weather forecast")
        uc_before = task_before["use_count"]
        store.merge_task("search weather forecast", new_result_summary="Updated")
        task_after = store.find_task("search weather forecast")
        assert task_after["use_count"] == uc_before + 1

    def test_nonexistent_key_returns_false(self, store: TaskKnowledgeStore):
        assert store.merge_task("nonexistent_key") is False

    def test_steps_detail_updated(self, store: TaskKnowledgeStore):
        new_detail = [{"tool": "exec", "args": {"cmd": "ls"}, "result": "files found"}]
        store.merge_task("分析上周报表邮件", new_steps_detail=new_detail)
        task = store.find_task("分析上周报表邮件")
        assert task["last_steps_detail"] == new_detail


class TestCount:
    def test_count(self, store: TaskKnowledgeStore):
        assert store.count() == 2

    def test_count_empty(self, tmp_workspace: Path):
        empty = TaskKnowledgeStore(tmp_workspace)
        empty._tasks = []
        assert empty.count() == 0


class TestSaveAutoMerge:
    @pytest.mark.asyncio
    async def test_save_exact_key_merges(self, kw_with_tasks: KnowledgeWorkflow):
        """Saving with same key should merge, not create duplicate."""
        result = await kw_with_tasks.save_to_knowledge(
            key="search weather forecast",
            steps=[{"tool": "web_search", "args": {"query": "weather tomorrow"}}],
            user_request="search weather forecast",
            result_summary="Tomorrow: rainy",
        )
        assert result is True
        # Should still be 2 tasks (not 3)
        assert kw_with_tasks.knowledge_store.count() == 2
        task = kw_with_tasks.knowledge_store.find_task("search weather forecast")
        assert task["version"] == 2
        assert task["result_summary"] == "Tomorrow: rainy"

    @pytest.mark.asyncio
    async def test_save_similar_key_merges(self, kw_with_tasks: KnowledgeWorkflow):
        """Saving with similar key should merge into existing."""
        result = await kw_with_tasks.save_to_knowledge(
            key="search weather report",
            steps=[{"tool": "web_search", "args": {"query": "weather weekly"}}],
            user_request="search weather report",
            result_summary="Weekly forecast ready",
        )
        assert result is True
        # Should still be 2 tasks (merged into "search weather forecast")
        assert kw_with_tasks.knowledge_store.count() == 2

    @pytest.mark.asyncio
    async def test_save_new_task_when_no_similar(self, kw_with_tasks: KnowledgeWorkflow):
        """Completely new task should create a new entry."""
        result = await kw_with_tasks.save_to_knowledge(
            key="compile rust project",
            steps=[{"tool": "exec", "args": {"cmd": "cargo build"}}],
            user_request="compile rust project",
            result_summary="Build successful",
        )
        assert result is True
        assert kw_with_tasks.knowledge_store.count() == 3

    @pytest.mark.asyncio
    async def test_save_without_store(self):
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        result = await kw.save_to_knowledge(
            key="anything", steps=[], user_request="test",
        )
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# P1: 静默步骤更新
# ═══════════════════════════════════════════════════════════════════════


class TestSilentUpdateSteps:
    def test_silent_update_existing_task(self, kw_with_tasks: KnowledgeWorkflow):
        tool_calls = [{"tool": "web_search", "args": {"query": "weather updated"}}]
        result = kw_with_tasks.silent_update_steps("search weather forecast", tool_calls)
        assert result is True
        task = kw_with_tasks.knowledge_store.find_task("search weather forecast")
        assert task["last_steps_detail"] == tool_calls

    def test_silent_update_nonexistent(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.silent_update_steps("nonexistent", [{"tool": "x"}])
        assert result is False

    def test_silent_update_empty_calls(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.silent_update_steps("search weather forecast", [])
        assert result is False

    def test_silent_update_no_store(self):
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        result = kw.silent_update_steps("anything", [{"tool": "x"}])
        assert result is False


class TestSessionLastToolCalls:
    def test_session_stores_last_tool_calls(self, tmp_workspace: Path):
        from nanobot.session.manager import Session, SessionManager
        mgr = SessionManager(tmp_workspace)
        session = mgr.get_or_create("test:session")
        session.last_tool_calls = [{"tool": "exec", "args": {"cmd": "ls"}}]
        session.last_task_key = "test_key"
        mgr.save(session)

        # Reload
        mgr.invalidate("test:session")
        loaded = mgr.get_or_create("test:session")
        assert loaded.last_tool_calls == [{"tool": "exec", "args": {"cmd": "ls"}}]
        assert loaded.last_task_key == "test_key"

    def test_session_clear_resets_tool_calls(self, tmp_workspace: Path):
        from nanobot.session.manager import Session
        session = Session(key="test")
        session.last_tool_calls = [{"tool": "x"}]
        session.clear()
        assert session.last_tool_calls is None


# ═══════════════════════════════════════════════════════════════════════
# P2: /kb 知识库管理命令
# ═══════════════════════════════════════════════════════════════════════


class TestKbList:
    def test_list_with_tasks(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.format_kb_list()
        assert "分析上周报表邮件" in result
        assert "search weather forecast" in result
        assert "v1" in result

    def test_list_empty(self, kw: KnowledgeWorkflow):
        result = kw.format_kb_list()
        assert "空" in result or "empty" in result.lower()

    def test_list_no_store(self):
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        result = kw.format_kb_list()
        assert "空" in result or "empty" in result.lower()


class TestKbDelete:
    def test_delete_existing(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.delete_knowledge("search weather forecast")
        assert "search weather forecast" in result
        assert kw_with_tasks.knowledge_store.find_task("search weather forecast") is None

    def test_delete_nonexistent(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.delete_knowledge("nonexistent_key")
        assert "nonexistent_key" in result
        assert "⚠️" in result or "not found" in result.lower()


class TestKbCleanup:
    def test_cleanup_merges_duplicates(self, tmp_workspace: Path):
        store = TaskKnowledgeStore(tmp_workspace)
        store.add_task(
            key="search weather today",
            description="Search weather",
            steps=[{"tool": "web_search"}],
            params={},
            result_summary="Sunny",
        )
        store.add_task(
            key="search weather forecast",
            description="Search weather forecast",
            steps=[{"tool": "web_search", "args": {"query": "forecast"}}],
            params={},
            result_summary="Rainy tomorrow",
        )
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)
        result = kw.cleanup_knowledge()
        # Should have merged 1 pair
        assert kw.knowledge_store.count() == 1
        assert "1" in result  # merged count

    def test_cleanup_no_duplicates(self, kw_with_tasks: KnowledgeWorkflow):
        result = kw_with_tasks.cleanup_knowledge()
        # "分析上周报表邮件" and "search weather forecast" are not similar
        assert kw_with_tasks.knowledge_store.count() == 2
        assert "0" in result


# ═══════════════════════════════════════════════════════════════════════
# P3: ChromaDB 语义匹配
# ═══════════════════════════════════════════════════════════════════════


class TestSemanticFallback:
    def test_count_method(self, store: TaskKnowledgeStore):
        assert store.count() == 2

    def test_semantic_fallback_skipped_when_few_entries(self, kw_with_tasks: KnowledgeWorkflow):
        """When entries <= 100, semantic fallback should not trigger."""
        # Only 2 entries, far below 100 threshold
        match = kw_with_tasks.match_knowledge("completely unrelated query xyz")
        assert match is None  # No match (no semantic fallback)

    def test_vector_memory_parameter_accepted(self, tmp_workspace: Path):
        """KnowledgeWorkflow accepts vector_memory parameter."""
        kw = KnowledgeWorkflow(
            provider=None, model=None, workspace=tmp_workspace,
            vector_memory="mock_vector_memory",
        )
        assert kw.vector_memory == "mock_vector_memory"

    def test_vector_memory_default_none(self, tmp_workspace: Path):
        """vector_memory defaults to None."""
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)
        assert kw.vector_memory is None
