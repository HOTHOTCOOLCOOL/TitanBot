"""Tests for Phase 22A — Skill Trigger & Discovery Optimization.

Covers:
- SK1: AI-First Skill Descriptions (quality checks)
- SK2: Skill Taxonomy & Categories (frontmatter parsing, XML output, grouping)
- SK3: Skill-Level Memory (execution logging, retrieval, formatting)
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from nanobot.agent.skills import SkillsLoader, SKILL_CATEGORIES, _MAX_EXECUTION_LOG


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with a test skill."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return tmp_path


@pytest.fixture
def skill_with_multiline(tmp_workspace):
    """Create a skill with multi-line YAML description and category."""
    skill_dir = tmp_workspace / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: test-skill\n"
        "description: >\n"
        "  This is a multi-line description that spans several lines.\n"
        "  Use when user asks to: test things, verify stuff, run checks.\n"
        "  Triggers: \"test it\", \"verify this\", \"run checks\".\n"
        "category: code_quality\n"
        "---\n\n"
        "# Test Skill\n\nBody content here.\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def skill_with_simple_desc(tmp_workspace):
    """Create a skill with simple single-line description."""
    skill_dir = tmp_workspace / "skills" / "simple-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: simple-skill\n"
        "description: A simple short description.\n"
        "category: data_fetching\n"
        "---\n\n"
        "# Simple Skill\n\nBody content here.\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def multi_skill_workspace(tmp_workspace):
    """Create workspace with multiple skills across categories."""
    for name, cat, desc in [
        ("email-tool", "business_workflow", "Handle emails."),
        ("report-gen", "business_workflow", "Generate reports."),
        ("weather-check", "data_fetching", "Check weather."),
        ("code-lint", "code_quality", "Lint code."),
        ("no-cat-skill", "", "A skill without category."),
    ]:
        d = tmp_workspace / "skills" / name
        d.mkdir(parents=True)
        cat_line = f"category: {cat}\n" if cat else ""
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n{cat_line}---\n\n# {name}\n",
            encoding="utf-8",
        )
    return tmp_workspace


@pytest.fixture
def loader(skill_with_multiline):
    """SkillsLoader for the multiline skill workspace."""
    return SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))


@pytest.fixture
def multi_loader(multi_skill_workspace):
    """SkillsLoader for multi-skill workspace."""
    return SkillsLoader(multi_skill_workspace, builtin_skills_dir=Path("/nonexistent"))


# ── SK1: AI-First Skill Descriptions ────────────────────────────────────────

class TestSK1DescriptionQuality:
    """Verify that builtin SKILL.md files have AI-optimized descriptions."""

    BUILTIN_DIR = Path(__file__).parent.parent / "nanobot" / "skills"

    @pytest.fixture
    def builtin_loader(self):
        """Loader pointing at the real builtin skills."""
        ws = Path(tempfile.mkdtemp())
        return SkillsLoader(ws, builtin_skills_dir=self.BUILTIN_DIR)

    def _get_all_builtin_names(self):
        if not self.BUILTIN_DIR.exists():
            pytest.skip("Builtin skills dir not found")
        return [
            d.name for d in self.BUILTIN_DIR.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    def test_all_descriptions_longer_than_50_chars(self, builtin_loader):
        """Each SKILL.md must have a description > 50 characters."""
        for name in self._get_all_builtin_names():
            meta = builtin_loader.get_skill_metadata(name)
            assert meta is not None, f"No metadata for {name}"
            desc = meta.get("description", "")
            assert len(desc) > 50, (
                f"Skill '{name}' description too short ({len(desc)} chars): '{desc[:80]}...'"
            )

    def test_descriptions_contain_trigger_info(self, builtin_loader):
        """Each description should contain trigger/usage guidance."""
        trigger_markers = ["Use when", "Trigger", "use when", "trigger"]
        for name in self._get_all_builtin_names():
            meta = builtin_loader.get_skill_metadata(name)
            assert meta is not None, f"No metadata for {name}"
            desc = meta.get("description", "")
            has_trigger = any(m in desc for m in trigger_markers)
            assert has_trigger, (
                f"Skill '{name}' description lacks trigger info: '{desc[:100]}...'"
            )

    def test_all_skills_have_category(self, builtin_loader):
        """Each builtin SKILL.md should have a category field."""
        for name in self._get_all_builtin_names():
            meta = builtin_loader.get_skill_metadata(name)
            assert meta is not None, f"No metadata for {name}"
            cat = meta.get("category", "")
            assert cat, f"Skill '{name}' has no category"
            assert cat in SKILL_CATEGORIES, (
                f"Skill '{name}' has invalid category '{cat}'. "
                f"Valid: {sorted(SKILL_CATEGORIES)}"
            )


# ── SK2: Taxonomy & Categories ──────────────────────────────────────────────

class TestSK2YAMLParsing:
    """Test the improved YAML frontmatter parser."""

    def test_parse_multiline_description(self, loader):
        """Multi-line `>` description should be joined into a single string."""
        meta = loader.get_skill_metadata("test-skill")
        assert meta is not None
        desc = meta["description"]
        assert "This is a multi-line description" in desc
        assert "Triggers:" in desc
        # No literal newlines in folded scalar output
        assert "\n" not in desc

    def test_parse_category_field(self, loader):
        """Category field should be parsed correctly."""
        meta = loader.get_skill_metadata("test-skill")
        assert meta is not None
        assert meta["category"] == "code_quality"

    def test_parse_simple_description(self, tmp_workspace):
        """Simple single-line description should parse correctly."""
        d = tmp_workspace / "skills" / "simple"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: simple\ndescription: Short desc.\ncategory: infra_ops\n---\n\n# X\n",
            encoding="utf-8",
        )
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        meta = loader.get_skill_metadata("simple")
        assert meta["description"] == "Short desc."
        assert meta["category"] == "infra_ops"

    def test_parse_quoted_values(self, tmp_workspace):
        """Quoted values should have quotes stripped."""
        d = tmp_workspace / "skills" / "quoted"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            '---\nname: "quoted"\ndescription: "A quoted description."\n---\n\n# X\n',
            encoding="utf-8",
        )
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        meta = loader.get_skill_metadata("quoted")
        assert meta["description"] == "A quoted description."


class TestSK2CategoryGrouping:
    """Test category-based skill grouping."""

    def test_build_skills_summary_includes_category(self, multi_loader):
        """XML output should contain <category> tags."""
        summary = multi_loader.build_skills_summary()
        assert '<category name="business_workflow">' in summary
        assert '<category name="data_fetching">' in summary
        assert '<category name="code_quality">' in summary
        # Uncategorized skill goes to "other"
        assert '<category name="other">' in summary

    def test_build_skills_summary_groups_correctly(self, multi_loader):
        """Each skill should appear within its correct category group."""
        summary = multi_loader.build_skills_summary()
        # email-tool and report-gen should be in business_workflow
        bw_start = summary.index('category name="business_workflow"')
        bw_end = summary.index("</category>", bw_start)
        bw_section = summary[bw_start:bw_end]
        assert "email-tool" in bw_section
        assert "report-gen" in bw_section

    def test_list_skills_by_category(self, multi_loader):
        """list_skills_by_category should return correct grouping dict."""
        grouped = multi_loader.list_skills_by_category()
        assert "business_workflow" in grouped
        assert len(grouped["business_workflow"]) == 2
        assert "data_fetching" in grouped
        assert len(grouped["data_fetching"]) == 1
        assert "other" in grouped
        assert len(grouped["other"]) == 1

    def test_list_skills_by_category_empty_dir(self, tmp_workspace):
        """Empty skills dir should return empty dict."""
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        # Remove the skills dir
        import shutil
        skills_dir = tmp_workspace / "skills"
        if skills_dir.exists():
            shutil.rmtree(skills_dir)
        assert loader.list_skills_by_category() == {}


# ── SK3: Skill-Level Memory ─────────────────────────────────────────────────

class TestSK3ExecutionLogging:
    """Test per-skill execution memory."""

    def test_log_execution_creates_memory_dir(self, skill_with_multiline):
        """log_execution should create memory/ dir and executions.jsonl."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        loader.log_execution("test-skill", "test input", "test output", 150, True)

        mem_dir = skill_with_multiline / "skills" / "test-skill" / "memory"
        assert mem_dir.exists()
        log_file = mem_dir / "executions.jsonl"
        assert log_file.exists()

    def test_log_execution_valid_json(self, skill_with_multiline):
        """Each line in executions.jsonl should be valid JSON."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        loader.log_execution("test-skill", "input1", "output1", 100, True)
        loader.log_execution("test-skill", "input2", "output2", 200, False)

        log_file = skill_with_multiline / "skills" / "test-skill" / "memory" / "executions.jsonl"
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["input"] == "input1"
        assert entry1["success"] is True
        assert entry1["duration_ms"] == 100

        entry2 = json.loads(lines[1])
        assert entry2["input"] == "input2"
        assert entry2["success"] is False

    def test_log_execution_fifo_cap(self, skill_with_multiline):
        """Execution log should be capped at _MAX_EXECUTION_LOG entries."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        
        for i in range(_MAX_EXECUTION_LOG + 20):
            loader.log_execution("test-skill", f"input_{i}", f"output_{i}", i * 10, True)

        log_file = skill_with_multiline / "skills" / "test-skill" / "memory" / "executions.jsonl"
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == _MAX_EXECUTION_LOG

        # First entry should be input_20 (FIFO removed first 20)
        first = json.loads(lines[0])
        assert first["input"] == "input_20"

    def test_get_recent_executions_correct_count(self, skill_with_multiline):
        """get_recent_executions should return correct number of entries."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        for i in range(5):
            loader.log_execution("test-skill", f"input_{i}", f"output_{i}", i * 100, True)

        recent = loader.get_recent_executions("test-skill", n=3)
        assert len(recent) == 3

    def test_get_recent_executions_most_recent_first(self, skill_with_multiline):
        """Results should be in reverse chronological order (most recent first)."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        for i in range(5):
            loader.log_execution("test-skill", f"input_{i}", f"output_{i}", i * 100, True)

        recent = loader.get_recent_executions("test-skill", n=3)
        assert recent[0]["input"] == "input_4"  # Most recent
        assert recent[1]["input"] == "input_3"
        assert recent[2]["input"] == "input_2"

    def test_get_recent_executions_unknown_skill(self, skill_with_multiline):
        """Unknown skill should return empty list."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        assert loader.get_recent_executions("nonexistent-skill") == []

    def test_get_recent_executions_no_history(self, skill_with_multiline):
        """Skill without execution history should return empty list."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        assert loader.get_recent_executions("test-skill") == []

    def test_format_execution_context(self, skill_with_multiline):
        """format_execution_context should return formatted string."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        loader.log_execution("test-skill", "Analyze email A", "Report generated", 1500, True)
        loader.log_execution("test-skill", "Analyze email B", "Error: timeout", 5000, False)

        ctx = loader.format_execution_context("test-skill", n=2)
        assert "Recent executions of 'test-skill'" in ctx
        assert "✓" in ctx
        assert "✗" in ctx
        assert "Analyze email" in ctx

    def test_format_execution_context_empty(self, skill_with_multiline):
        """No history should return empty string."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        assert loader.format_execution_context("test-skill") == ""

    def test_build_summary_includes_execution_history(self, skill_with_multiline):
        """build_skills_summary should show recent_executions when available."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        loader.log_execution("test-skill", "Test input A", "Output A", 300, True)

        summary = loader.build_skills_summary()
        assert "<recent_executions>" in summary
        assert "Test input A" in summary


# ── SaveSkillTool Category ──────────────────────────────────────────────────

class TestSaveSkillCategory:
    """Test that SaveSkillTool includes category parameter."""

    def test_category_in_parameter_schema(self):
        from nanobot.agent.tools.save_skill import SaveSkillTool
        tool = SaveSkillTool(Path(tempfile.mkdtemp()))
        props = tool.parameters["properties"]
        assert "category" in props
        assert "enum" in props["category"]
        assert "business_workflow" in props["category"]["enum"]

    @pytest.mark.asyncio
    async def test_save_skill_with_category(self):
        from nanobot.agent.tools.save_skill import SaveSkillTool
        ws = Path(tempfile.mkdtemp())
        tool = SaveSkillTool(ws)
        result = await tool.execute(
            name="test-cat-skill",
            description="A test skill with category",
            summary="Testing category in frontmatter",
            steps=[{"action": "test step"}],
            category="business_workflow",
        )
        assert "Successfully saved" in result
        content = (ws / "skills" / "test-cat-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "category: business_workflow" in content


# ── Edge Cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Additional edge-case tests for robustness."""

    def test_log_execution_truncates_long_input(self, skill_with_multiline):
        """Input summary should be capped at 200 chars."""
        loader = SkillsLoader(skill_with_multiline, builtin_skills_dir=Path("/nonexistent"))
        long_input = "x" * 500
        loader.log_execution("test-skill", long_input, "output", 100, True)

        recent = loader.get_recent_executions("test-skill", n=1)
        assert len(recent[0]["input"]) <= 200

    def test_log_execution_nonexistent_skill(self, tmp_workspace):
        """Logging for nonexistent skill should not raise."""
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        # Should silently skip — no exception
        loader.log_execution("ghost-skill", "input", "output", 100, True)

    def test_category_constants_match_spec(self):
        """SKILL_CATEGORIES should match the Phase 22 spec exactly."""
        expected = {
            "library_api", "code_quality", "frontend_design",
            "business_workflow", "product_verification",
            "content_generation", "data_fetching",
            "service_debugging", "infra_ops",
        }
        assert SKILL_CATEGORIES == expected

    def test_multiline_yaml_with_inline_json_metadata(self, tmp_workspace):
        """Parser should handle inline JSON metadata alongside multi-line desc."""
        d = tmp_workspace / "skills" / "json-meta"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            '---\n'
            'name: json-meta\n'
            'description: >\n'
            '  Multi-line desc here.\n'
            '  Second line of desc.\n'
            'category: infra_ops\n'
            'metadata: {"nanobot":{"emoji":"🔧"}}\n'
            '---\n\n# X\n',
            encoding="utf-8",
        )
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        meta = loader.get_skill_metadata("json-meta")
        assert meta is not None
        assert "Multi-line desc here." in meta["description"]
        assert "Second line of desc." in meta["description"]
        assert meta["category"] == "infra_ops"
        assert '"nanobot"' in meta["metadata"]
