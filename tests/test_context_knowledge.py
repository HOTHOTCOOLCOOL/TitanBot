"""Tests for context.py bootstrap loading and prompt invariants."""

from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from nanobot.agent.context import ContextBuilder


@pytest.fixture
def workspace_with_knowledge() -> Path:
    """Create a workspace with a KNOWLEDGE.md file."""
    workspace = Path(".pytest_tmp_context") / f"with_knowledge_{uuid4().hex}"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "KNOWLEDGE.md").write_text(
        "# System Knowledge\n\n## Rules\n- Sales reports arrive next day\n",
        encoding="utf-8",
    )
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def workspace_without_knowledge() -> Path:
    """Create a workspace without KNOWLEDGE.md."""
    workspace = Path(".pytest_tmp_context") / f"without_knowledge_{uuid4().hex}"
    (workspace / "memory").mkdir(parents=True)
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


class TestKnowledgeLoading:
    def test_knowledge_in_bootstrap_files(self):
        """KNOWLEDGE.md is listed in BOOTSTRAP_FILES."""
        assert "KNOWLEDGE.md" in ContextBuilder.BOOTSTRAP_FILES

    def test_knowledge_loaded_into_prompt(self, workspace_with_knowledge: Path):
        """KNOWLEDGE.md content appears in system prompt."""
        ctx = ContextBuilder(workspace_with_knowledge, language="zh")
        prompt = ctx.build_system_prompt()
        assert "Sales reports arrive next day" in prompt

    def test_missing_knowledge_no_error(self, workspace_without_knowledge: Path):
        """Missing KNOWLEDGE.md does not cause errors."""
        ctx = ContextBuilder(workspace_without_knowledge, language="zh")
        prompt = ctx.build_system_prompt()
        assert "nanobot" in prompt


class TestPromptHints:
    def test_date_hint_in_identity(self, workspace_without_knowledge: Path):
        """Date interpretation hint appears in the identity section."""
        ctx = ContextBuilder(workspace_without_knowledge, language="zh")
        prompt = ctx.build_system_prompt()
        assert "日期理解提示" in prompt
        assert "KNOWLEDGE.md" in prompt

    def test_complex_task_protocol_in_prompt(self, workspace_without_knowledge: Path):
        """Planning Gate fallback instructions should always be present."""
        ctx = ContextBuilder(workspace_without_knowledge, language="zh")
        prompt = ctx.build_system_prompt()
        assert "Complex Task Protocol" in prompt
        assert "`write_artifact`" in prompt
        assert "implementation_plan.md" in prompt


class TestReasoningTemplatePromptBudget:
    def test_reasoning_template_truncated(self, workspace_without_knowledge: Path):
        """T03: reasoning_template entities are truncated to 1000 chars."""
        from nanobot.agent.knowledge_graph import KnowledgeGraph

        workspace = workspace_without_knowledge
        kg = KnowledgeGraph(workspace)
        kg._add_triple("Reasoning: Huge", "is", "huge")
        kg.rebuild_entity_index()
        long_text = "A" * 1500
        kg._entities["Reasoning: Huge"]["type"] = "reasoning_template"
        kg._entities["Reasoning: Huge"]["summary"] = long_text
        kg._save()

        ctx = ContextBuilder(workspace, language="zh")
        messages = ctx.build_messages([], "Tell me about Reasoning: Huge", knowledge_graph=kg)
        sys_prompt = messages[0]["content"]

        assert "A" * 1000 in sys_prompt
        assert "A" * 1050 not in sys_prompt

    def test_reasoning_template_truncated_with_prefetched_kg(
        self, workspace_without_knowledge: Path
    ):
        """T03: pre-fetched KG injection follows the same 1000-char cap."""
        from nanobot.agent.knowledge_graph import KnowledgeGraph

        workspace = workspace_without_knowledge
        kg = KnowledgeGraph(workspace)
        kg._add_triple("Reasoning: Huge", "is", "huge")
        kg.rebuild_entity_index()
        long_text = "A" * 1500
        kg._entities["Reasoning: Huge"]["type"] = "reasoning_template"
        kg._entities["Reasoning: Huge"]["summary"] = long_text
        kg._save()

        ctx = ContextBuilder(workspace, language="zh")
        pre_fetched_kg = kg.get_entity_context("Tell me about Reasoning: Huge")
        messages = ctx.build_messages(
            [],
            "Tell me about Reasoning: Huge",
            knowledge_graph=kg,
            pre_fetched_kg=pre_fetched_kg,
        )
        sys_prompt = messages[0]["content"]

        assert "A" * 1000 in sys_prompt
        assert "A" * 1050 not in sys_prompt

    def test_non_reasoning_template_not_truncated(
        self, workspace_without_knowledge: Path
    ):
        """T03: Non-reasoning templates are not truncated."""
        from nanobot.agent.knowledge_graph import KnowledgeGraph

        workspace = workspace_without_knowledge
        kg = KnowledgeGraph(workspace)
        kg._add_triple("Normal Entity", "is", "large")
        kg.rebuild_entity_index()
        long_text = "B" * 1500
        kg._entities["Normal Entity"]["type"] = ""
        kg._entities["Normal Entity"]["summary"] = long_text
        kg._save()

        ctx = ContextBuilder(workspace, language="zh")
        messages = ctx.build_messages([], "Tell me about Normal Entity", knowledge_graph=kg)
        sys_prompt = messages[0]["content"]

        assert "B" * 1500 in sys_prompt


class TestSkillSslPromptCompression:
    def test_skill_ssl_scheduling_preferred_in_system_prompt(
        self, workspace_without_knowledge: Path
    ):
        """T05: Active skill injection should prefer persisted SSL Scheduling over raw SKILL.md."""
        from nanobot.agent.knowledge_graph import KnowledgeGraph

        workspace = workspace_without_knowledge
        skill_dir = workspace / "skills" / "mock_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("A" * 5000, encoding="utf-8")

        kg = KnowledgeGraph(workspace)
        kg._entities["mock_skill_ssl"] = {
            "type": "skill_ssl",
            "summary": "",
            "triple_indices": [],
            "properties": {
                "hash": "mockhash",
                "graph": {
                    "Scheduling": {"trigger": "always", "cost": "low"},
                    "Structural": {"depends_on": []},
                    "Logical": {"rules": []},
                },
            },
        }
        kg._save()

        ctx = ContextBuilder(workspace, language="zh")
        prompt = ctx.build_system_prompt(skill_names=["mock_skill"])

        assert "Scheduling" in prompt
        assert "trigger" in prompt
        assert "A" * 200 not in prompt
