"""Tests for P0-A: Knowledge Success Tracking + Few-shot Generation."""

import pytest
from pathlib import Path

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.task_knowledge import TaskKnowledgeStore


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
def kw(tmp_workspace: Path) -> KnowledgeWorkflow:
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


@pytest.fixture
def kw_with_tasks(tmp_workspace: Path, store: TaskKnowledgeStore) -> KnowledgeWorkflow:
    """KnowledgeWorkflow with pre-populated store (via store fixture)."""
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


# ── TaskKnowledgeStore: Success/Fail Tracking ──


class TestSuccessTracking:
    def test_initial_counts(self, store: TaskKnowledgeStore):
        task = store.find_task("search weather")
        assert task is not None
        assert task["success_count"] == 1
        assert task["fail_count"] == 0

    def test_record_success(self, store: TaskKnowledgeStore):
        store.record_success("search weather")
        task = store.find_task("search weather")
        assert task["success_count"] == 2

    def test_record_failure(self, store: TaskKnowledgeStore):
        store.record_failure("search weather")
        task = store.find_task("search weather")
        assert task["fail_count"] == 1

    def test_record_nonexistent_key(self, store: TaskKnowledgeStore):
        assert store.record_success("nonexistent") is False
        assert store.record_failure("nonexistent") is False

    def test_success_rate_all_success(self, store: TaskKnowledgeStore):
        rate = store.get_success_rate("search weather")
        assert rate == 1.0

    def test_success_rate_mixed(self, store: TaskKnowledgeStore):
        store.record_failure("search weather")
        # 1 success + 1 fail = 50%
        rate = store.get_success_rate("search weather")
        assert rate == 0.5

    def test_success_rate_not_found(self, store: TaskKnowledgeStore):
        assert store.get_success_rate("nonexistent") == -1.0

    def test_steps_detail_stored(self, store: TaskKnowledgeStore):
        task = store.find_task("search weather")
        assert len(task["last_steps_detail"]) == 1
        assert task["last_steps_detail"][0]["tool"] == "web_search"

    def test_update_steps_detail(self, store: TaskKnowledgeStore):
        new_detail = [{"tool": "web_fetch", "args": {"url": "http://..."}, "result": "done"}]
        store.update_steps_detail("search weather", new_detail)
        task = store.find_task("search weather")
        assert task["last_steps_detail"][0]["tool"] == "web_fetch"


# ── KnowledgeWorkflow: Outcome Recording ──


class TestOutcomeRecording:
    def test_record_success(self, kw_with_tasks: KnowledgeWorkflow):
        kw_with_tasks.record_outcome("search weather", success=True)
        task = kw_with_tasks.knowledge_store.find_task("search weather")
        assert task["success_count"] == 2

    def test_record_failure(self, kw_with_tasks: KnowledgeWorkflow):
        kw_with_tasks.record_outcome("search weather", success=False)
        task = kw_with_tasks.knowledge_store.find_task("search weather")
        assert task["fail_count"] == 1

    def test_record_without_store(self):
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        # Should not raise
        kw.record_outcome("anything", success=True)


# ── KnowledgeWorkflow: Negative Feedback Detection ──


class TestNegativeFeedback:
    @pytest.mark.parametrize("text", [
        "不对", "错了", "重来", "不行", "有问题",
        "wrong", "incorrect", "try again", "not right",
    ])
    def test_negative_detected(self, text: str):
        assert KnowledgeWorkflow.is_negative_feedback(text) is True

    @pytest.mark.parametrize("text", [
        "谢谢", "好的", "可以", "thanks", "great", "hello",
    ])
    def test_non_negative(self, text: str):
        assert KnowledgeWorkflow.is_negative_feedback(text) is False


# ── KnowledgeWorkflow: Few-shot Prompt Generation ──


class TestFewShotPrompt:
    def test_few_shot_with_detail(self, kw_with_tasks: KnowledgeWorkflow):
        match = kw_with_tasks.knowledge_store.find_task("search weather")
        prompt = kw_with_tasks.format_few_shot_prompt(match)
        assert "Reference" in prompt
        assert "web_search" in prompt
        assert "Sunny" in prompt

    def test_few_shot_without_detail(self, kw_with_tasks: KnowledgeWorkflow):
        # Add task with steps but no steps_detail
        kw_with_tasks.knowledge_store.add_task(
            key="simple task",
            description="test",
            steps=["step1", "step2"],
            params={},
            result_summary="Done",
        )
        match = kw_with_tasks.knowledge_store.find_task("simple task")
        prompt = kw_with_tasks.format_few_shot_prompt(match)
        assert "Tools used" in prompt
        assert "step1" in prompt

    def test_few_shot_empty(self):
        match = {"key": "empty", "steps": [], "last_steps_detail": []}
        kw = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        assert kw.format_few_shot_prompt(match) == ""


# ── KnowledgeWorkflow: Match Stats ──


class TestMatchStats:
    def test_stats_new_task(self, kw_with_tasks: KnowledgeWorkflow):
        match = kw_with_tasks.knowledge_store.find_task("search weather")
        stats = kw_with_tasks.get_match_stats(match)
        assert stats["success_count"] == 1
        assert stats["fail_count"] == 0
        assert stats["rate"] == 100
        assert stats["use_count"] == 1

    def test_stats_after_mixed(self, kw_with_tasks: KnowledgeWorkflow):
        kw_with_tasks.record_outcome("search weather", success=True)
        kw_with_tasks.record_outcome("search weather", success=False)
        match = kw_with_tasks.knowledge_store.find_task("search weather")
        stats = kw_with_tasks.get_match_stats(match)
        assert stats["success_count"] == 2
        assert stats["fail_count"] == 1
        # 2/3 ≈ 66.67%
        assert 66 < stats["rate"] < 67


# ── KnowledgeWorkflow: Skill Upgrade Suggestion ──


class TestSkillUpgrade:
    def test_no_upgrade_initially(self, kw_with_tasks: KnowledgeWorkflow):
        assert kw_with_tasks.should_suggest_skill_upgrade("search weather") is False

    def test_upgrade_after_3_successes(self, kw_with_tasks: KnowledgeWorkflow):
        # Already has 1 success, add 2 more
        kw_with_tasks.record_outcome("search weather", success=True)
        kw_with_tasks.record_outcome("search weather", success=True)
        assert kw_with_tasks.should_suggest_skill_upgrade("search weather") is True

    def test_no_upgrade_nonexistent(self, kw_with_tasks: KnowledgeWorkflow):
        assert kw_with_tasks.should_suggest_skill_upgrade("nonexistent") is False

    def test_upgrade_prompt_format(self, kw_with_tasks: KnowledgeWorkflow):
        match = kw_with_tasks.knowledge_store.find_task("search weather")
        prompt = KnowledgeWorkflow.format_skill_upgrade_prompt(match, lang="en")
        assert "upgrade" in prompt.lower() or "skill" in prompt.lower()
