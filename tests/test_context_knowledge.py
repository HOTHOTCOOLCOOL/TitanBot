"""Tests for context.py KNOWLEDGE.md loading and date hint."""

import pytest
from pathlib import Path

from nanobot.agent.context import ContextBuilder


@pytest.fixture
def workspace_with_knowledge(tmp_path: Path) -> Path:
    """Create a workspace with a KNOWLEDGE.md file."""
    (tmp_path / "memory").mkdir()
    (tmp_path / "KNOWLEDGE.md").write_text(
        "# System Knowledge\n\n## Rules\n- Sales reports arrive next day\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def workspace_without_knowledge(tmp_path: Path) -> Path:
    """Create a workspace without KNOWLEDGE.md."""
    (tmp_path / "memory").mkdir()
    return tmp_path


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
        # Should still generate a valid prompt
        assert "nanobot" in prompt


class TestDateHint:
    def test_date_hint_in_identity(self, workspace_without_knowledge: Path):
        """Date interpretation hint appears in identity section."""
        ctx = ContextBuilder(workspace_without_knowledge, language="zh")
        prompt = ctx.build_system_prompt()
        assert "日期理解提示" in prompt
        assert "KNOWLEDGE.md" in prompt
