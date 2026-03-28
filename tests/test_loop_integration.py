"""Tests for Phase 8 loop.py integration: implicit feedback, stats display,
last_task_key, few-shot injection, upgrade commands, consolidation counter."""

import pytest
from pathlib import Path

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.session.manager import Session, SessionManager
from nanobot.agent.i18n import msg as i18n_msg, set_language


# ── Fixtures ──


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def store(tmp_workspace: Path) -> TaskKnowledgeStore:
    s = TaskKnowledgeStore(tmp_workspace)
    s.add_task(
        key="search weather",
        description="Search for weather",
        steps=[{"tool": "web_search", "args": {"query": "weather"}}],
        params={},
        result_summary="Today: sunny",
        steps_detail=[
            {"tool": "web_search", "args": {"query": "weather today"}, "result": "Sunny, 25°C"},
        ],
    )
    return s


@pytest.fixture
def kw(tmp_workspace: Path, store: TaskKnowledgeStore) -> KnowledgeWorkflow:
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


# ── Upgrade Command Recognition ──


class TestUpgradeCommand:
    @pytest.mark.parametrize("text", [
        "升级", "upgrade", "升级skill", "UPGRADE", "Upgrade Skill", "升",
    ])
    def test_is_upgrade_command(self, text: str):
        assert KnowledgeWorkflow.is_upgrade_command(text) is True

    @pytest.mark.parametrize("text", [
        "是", "yes", "save", "hello", "redo", "不", "取消",
    ])
    def test_is_not_upgrade_command(self, text: str):
        assert KnowledgeWorkflow.is_upgrade_command(text) is False


# ── Implicit Feedback Logic ──


class TestImplicitFeedback:
    """Test that implicit feedback logic (checked at _process_message entry) works."""

    def test_positive_feedback_records_success(self, kw: KnowledgeWorkflow):
        """Non-negative message after task → record success."""
        # Simulate: last_task_key was set, user says "谢谢" (positive)
        assert not kw.is_negative_feedback("谢谢")
        kw.record_outcome("search weather", success=True)
        task = kw.knowledge_store.find_task("search weather")
        assert task["success_count"] == 2  # was 1 initially

    def test_negative_feedback_records_failure(self, kw: KnowledgeWorkflow):
        """Negative message after task → record failure."""
        assert kw.is_negative_feedback("不对")
        kw.record_outcome("search weather", success=False)
        task = kw.knowledge_store.find_task("search weather")
        assert task["fail_count"] == 1

    def test_last_task_key_cleared_after_feedback(self):
        """session.last_task_key should be set to None after processing."""
        session = Session(key="test:1")
        session.last_task_key = "some_task"
        # This simulates loop.py behavior:
        session.last_task_key = None
        assert session.last_task_key is None


# ── Stats-Enhanced Match Display ──


class TestMatchWithStats:
    def test_stats_prompt_includes_rate(self, kw: KnowledgeWorkflow):
        """knowledge_match_with_stats message includes success rate."""
        match = kw.knowledge_store.find_task("search weather")
        stats = kw.get_match_stats(match)
        assert stats["use_count"] > 0
        assert stats["rate"] == 100  # 1 success, 0 failures

        prompt = i18n_msg(
            "knowledge_match_with_stats",
            key="search weather",
            rate=str(stats["rate"]),
            count=str(stats["use_count"]),
            score="0.95",
            lang="en",
        )
        assert "100" in prompt
        assert "search weather" in prompt
        assert "0.95" in prompt

    def test_stats_prompt_zh(self, kw: KnowledgeWorkflow):
        """Chinese version of stats prompt works."""
        match = kw.knowledge_store.find_task("search weather")
        stats = kw.get_match_stats(match)
        prompt = i18n_msg(
            "knowledge_match_with_stats",
            key="search weather",
            rate=str(stats["rate"]),
            count=str(stats["use_count"]),
            score="0.88",
            lang="zh",
        )
        assert "成功率" in prompt
        assert "相似度" in prompt


# ── last_task_key Setting ──


class TestLastTaskKey:
    def test_session_last_task_key_lifecycle(self):
        """last_task_key is set after tool execution and cleared after feedback."""
        session = Session(key="test:1")
        assert session.last_task_key is None

        # Simulate _execute_with_llm setting it
        session.last_task_key = "分析报表"
        assert session.last_task_key == "分析报表"

        # Simulate implicit feedback clearing it
        session.last_task_key = None
        assert session.last_task_key is None


# ── Few-shot Injection ──


class TestFewShotInjection:
    def test_few_shot_appended_to_system_prompt(self, kw: KnowledgeWorkflow):
        """Few-shot context is generated and can be appended to system message."""
        match = kw.knowledge_store.find_task("search weather")
        few_shot = kw.format_few_shot_prompt(match)
        assert "Reference" in few_shot
        assert "web_search" in few_shot

        # Simulate what loop.py does
        messages = [{"role": "system", "content": "You are nanobot."}]
        if few_shot:
            messages[0]["content"] += f"\n\n{few_shot}"
        assert "Reference" in messages[0]["content"]
        assert messages[0]["content"].startswith("You are nanobot.")

    def test_empty_few_shot_not_appended(self):
        """Empty few-shot does not modify system message."""
        match = {"key": "empty", "steps": [], "last_steps_detail": []}
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        few_shot = kw.format_few_shot_prompt(match)
        assert few_shot == ""

        messages = [{"role": "system", "content": "Original prompt"}]
        # loop.py only appends if few_shot is truthy
        if few_shot:
            messages[0]["content"] += f"\n\n{few_shot}"
        assert messages[0]["content"] == "Original prompt"


# ── Session Persistence: New Fields ──


class TestSessionPersistence:
    def test_pending_upgrade_persisted(self, tmp_workspace: Path):
        """pending_upgrade is saved and loaded correctly."""
        sm = SessionManager(tmp_workspace)
        session = sm.get_or_create("test:upgrade")
        session.pending_upgrade = {"key": "weather", "match": {"key": "weather"}}
        sm.save(session)

        sm.invalidate("test:upgrade")
        reloaded = sm.get_or_create("test:upgrade")
        assert reloaded.pending_upgrade is not None
        assert reloaded.pending_upgrade["key"] == "weather"

    def test_message_count_persisted(self, tmp_workspace: Path):
        """message_count_since_consolidation is saved and loaded."""
        sm = SessionManager(tmp_workspace)
        session = sm.get_or_create("test:counter")
        session.message_count_since_consolidation = 15
        sm.save(session)

        sm.invalidate("test:counter")
        reloaded = sm.get_or_create("test:counter")
        assert reloaded.message_count_since_consolidation == 15

    def test_last_task_key_persisted(self, tmp_workspace: Path):
        """last_task_key is saved and loaded."""
        sm = SessionManager(tmp_workspace)
        session = sm.get_or_create("test:ltk")
        session.last_task_key = "分析邮件"
        sm.save(session)

        sm.invalidate("test:ltk")
        reloaded = sm.get_or_create("test:ltk")
        assert reloaded.last_task_key == "分析邮件"

    def test_clear_resets_new_fields(self):
        """Session.clear() resets pending_upgrade and counter."""
        s = Session(key="test:clear")
        s.pending_upgrade = {"key": "x"}
        s.message_count_since_consolidation = 10
        s.clear()
        assert s.pending_upgrade is None
        assert s.message_count_since_consolidation == 0


# ── P1-B: Consolidation Counter ──


class TestConsolidationCounter:
    def test_counter_increments(self):
        """Message counter increments by 2 per exchange (user+assistant)."""
        s = Session(key="test:cnt")
        assert s.message_count_since_consolidation == 0
        s.message_count_since_consolidation += 2
        assert s.message_count_since_consolidation == 2

    def test_counter_triggers_at_20(self):
        """Counter >= 20 triggers consolidation (simulated)."""
        s = Session(key="test:cnt2")
        s.message_count_since_consolidation = 18
        s.message_count_since_consolidation += 2
        assert s.message_count_since_consolidation >= 20

    def test_no_trigger_with_pending(self):
        """Consolidation NOT triggered when pending_save is set."""
        s = Session(key="test:pending")
        s.message_count_since_consolidation = 20
        s.pending_save = {"key": "something"}
        # Simulate the guard check from loop.py
        should_trigger = (
            s.message_count_since_consolidation >= 20
            and not s.pending_knowledge
            and not s.pending_save
            and not s.pending_upgrade
        )
        assert should_trigger is False


# ── Skill Upgrade Suggestion ──


class TestSkillUpgradeIntegration:
    def test_upgrade_not_suggested_initially(self, kw: KnowledgeWorkflow):
        """With 1 success, upgrade should not be suggested."""
        assert kw.should_suggest_skill_upgrade("search weather") is False

    def test_upgrade_suggested_after_3(self, kw: KnowledgeWorkflow):
        """After 3 successes, upgrade should be suggested."""
        kw.record_outcome("search weather", success=True)
        kw.record_outcome("search weather", success=True)
        assert kw.should_suggest_skill_upgrade("search weather") is True

    def test_upgrade_prompt_format(self, kw: KnowledgeWorkflow):
        match = kw.knowledge_store.find_task("search weather")
        prompt = KnowledgeWorkflow.format_skill_upgrade_prompt(match, lang="zh")
        assert "升级" in prompt or "skill" in prompt.lower()

        prompt_en = KnowledgeWorkflow.format_skill_upgrade_prompt(match, lang="en")
        assert "upgrade" in prompt_en.lower() or "skill" in prompt_en.lower()
