"""Tests for Phase 22B — Skill Configurability & Hooks.

Covers:
- SK4: Configurable Skill Behavior (config.json overlay)
- SK5: Dynamic Hooks System (pre/post-execute hooks)
- SK7: Skill Registry & Versioning (skills_registry.json)
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from nanobot.agent.skills import SkillsLoader, HookResult


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with skills dir."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return tmp_path


@pytest.fixture
def skill_basic(tmp_workspace):
    """Create a basic skill for testing."""
    skill_dir = tmp_workspace / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: test-skill\n"
        "description: A basic test skill for Phase 22B testing.\n"
        "category: code_quality\n"
        "version: 2.1.0\n"
        'metadata: {"nanobot":{"requires":{"bins":[],"pip":["requests","openpyxl"]},"tags":["test"]}}\n'
        "---\n\n"
        "# Test Skill\n\nBody content.\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def skill_with_hooks_frontmatter(tmp_workspace):
    """Create a skill with hooks defined in frontmatter."""
    skill_dir = tmp_workspace / "skills" / "hooked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: hooked-skill\n"
        "description: A skill with hooks for testing.\n"
        "category: infra_ops\n"
        "hooks_pre: confirm_destructive\n"
        "hooks_post: log_execution, notify_completion\n"
        "---\n\n"
        "# Hooked Skill\n\nBody content.\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def skill_with_hooks_py(tmp_workspace):
    """Create a skill with a hooks.py file."""
    skill_dir = tmp_workspace / "skills" / "pyhooked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: pyhooked-skill\n"
        "description: A skill with hooks.py.\n"
        "category: code_quality\n"
        "---\n\n"
        "# PyHooked Skill\n",
        encoding="utf-8",
    )
    (skill_dir / "hooks.py").write_text(
        "async def pre_execute(context):\n"
        '    return {"proceed": True, "message": "pre-hook ran"}\n\n'
        "async def post_execute(context, result):\n"
        "    pass  # no-op\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def skill_with_bad_hooks_py(tmp_workspace):
    """Create a skill with a broken hooks.py."""
    skill_dir = tmp_workspace / "skills" / "bad-hook-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: bad-hook-skill\n"
        "description: Skill with broken hooks.\n"
        "category: infra_ops\n"
        "---\n\n"
        "# Bad Hook\n",
        encoding="utf-8",
    )
    (skill_dir / "hooks.py").write_text(
        "async def pre_execute(context):\n"
        "    raise RuntimeError('deliberate hook error')\n",
        encoding="utf-8",
    )
    return tmp_workspace


@pytest.fixture
def loader(skill_basic):
    return SkillsLoader(skill_basic, builtin_skills_dir=Path("/nonexistent"))


@pytest.fixture
def hooked_loader(skill_with_hooks_frontmatter):
    return SkillsLoader(skill_with_hooks_frontmatter, builtin_skills_dir=Path("/nonexistent"))


@pytest.fixture
def pyhooked_loader(skill_with_hooks_py):
    return SkillsLoader(skill_with_hooks_py, builtin_skills_dir=Path("/nonexistent"))


@pytest.fixture
def bad_hook_loader(skill_with_bad_hooks_py):
    return SkillsLoader(skill_with_bad_hooks_py, builtin_skills_dir=Path("/nonexistent"))


# ── SK4: Configurable Skill Behavior ────────────────────────────────────────


class TestSK4ConfigOverlay:
    """Test per-skill config.json overlay system."""

    def test_load_skill_config_empty(self, loader):
        """No config.json → returns empty dict."""
        assert loader.load_skill_config("test-skill") == {}

    def test_load_skill_config_valid(self, loader, skill_basic):
        """Valid config.json → returns parsed dict."""
        config_file = skill_basic / "skills" / "test-skill" / "config.json"
        config_file.write_text('{"max_results": 20, "language": "zh-CN"}', encoding="utf-8")
        cfg = loader.load_skill_config("test-skill")
        assert cfg["max_results"] == 20
        assert cfg["language"] == "zh-CN"

    def test_load_skill_config_invalid_json(self, loader, skill_basic):
        """Malformed JSON → returns empty dict (no crash)."""
        config_file = skill_basic / "skills" / "test-skill" / "config.json"
        config_file.write_text("{invalid json!!!", encoding="utf-8")
        cfg = loader.load_skill_config("test-skill")
        assert cfg == {}

    def test_load_skill_config_nonexistent_skill(self, loader):
        """Unknown skill → returns empty dict."""
        assert loader.load_skill_config("ghost-skill") == {}

    def test_save_skill_config(self, loader, skill_basic):
        """save_skill_config creates/overwrites config.json."""
        assert loader.save_skill_config("test-skill", {"auto_send": True})
        config_file = skill_basic / "skills" / "test-skill" / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data["auto_send"] is True

    def test_save_skill_config_nonexistent_skill(self, loader):
        """save_skill_config for unknown skill → returns False."""
        assert loader.save_skill_config("ghost-skill", {"key": "val"}) is False

    def test_effective_config_defaults_only(self, loader, skill_basic):
        """Only defaults file → returns defaults."""
        defaults_file = skill_basic / "skills" / "test-skill" / "config.defaults.json"
        defaults_file.write_text('{"max_results": 10, "folder": "inbox"}', encoding="utf-8")
        cfg = loader.get_effective_config("test-skill")
        assert cfg["max_results"] == 10
        assert cfg["folder"] == "inbox"

    def test_effective_config_overlay(self, loader, skill_basic):
        """User config overrides defaults."""
        defaults_file = skill_basic / "skills" / "test-skill" / "config.defaults.json"
        defaults_file.write_text('{"max_results": 10, "folder": "inbox"}', encoding="utf-8")
        config_file = skill_basic / "skills" / "test-skill" / "config.json"
        config_file.write_text('{"max_results": 50}', encoding="utf-8")
        cfg = loader.get_effective_config("test-skill")
        assert cfg["max_results"] == 50  # User override
        assert cfg["folder"] == "inbox"  # Default preserved

    def test_effective_config_no_files(self, loader):
        """No config files → returns empty dict."""
        cfg = loader.get_effective_config("test-skill")
        assert cfg == {}

    def test_xml_summary_includes_config_keys(self, loader, skill_basic):
        """build_skills_summary includes config_keys when config.json exists."""
        config_file = skill_basic / "skills" / "test-skill" / "config.json"
        config_file.write_text('{"max_results": 20, "language": "zh-CN"}', encoding="utf-8")
        summary = loader.build_skills_summary()
        assert "<config_keys>" in summary
        assert "language" in summary
        assert "max_results" in summary


# ── SK5: Dynamic Hooks System ───────────────────────────────────────────────


class TestSK5Hooks:
    """Test pre/post-execute hooks system."""

    def test_hook_result_defaults(self):
        """HookResult defaults to proceed=True, message=''."""
        hr = HookResult()
        assert hr.proceed is True
        assert hr.message == ""

    def test_hook_result_custom(self):
        """HookResult accepts custom values."""
        hr = HookResult(proceed=False, message="blocked!")
        assert hr.proceed is False
        assert hr.message == "blocked!"

    def test_get_hooks_from_frontmatter(self, hooked_loader):
        """Parse hooks from SKILL.md frontmatter."""
        hooks = hooked_loader.get_skill_hooks("hooked-skill")
        assert "confirm_destructive" in hooks["pre_execute"]
        assert "log_execution" in hooks["post_execute"]
        assert "notify_completion" in hooks["post_execute"]

    def test_get_hooks_no_hooks(self, loader):
        """Skill without hooks → empty lists."""
        hooks = loader.get_skill_hooks("test-skill")
        assert hooks["pre_execute"] == []
        assert hooks["post_execute"] == []

    def test_get_hooks_with_hooks_py(self, pyhooked_loader):
        """hooks.py presence auto-adds hooks_py to both lists."""
        hooks = pyhooked_loader.get_skill_hooks("pyhooked-skill")
        assert "hooks_py" in hooks["pre_execute"]
        assert "hooks_py" in hooks["post_execute"]

    @pytest.mark.asyncio
    async def test_run_pre_hooks_confirm_destructive_blocks(self, hooked_loader):
        """confirm_destructive pre-hook blocks execution."""
        result = await hooked_loader.run_pre_hooks("hooked-skill", {"input": "test"})
        assert result.proceed is False
        assert "destructive" in result.message

    @pytest.mark.asyncio
    async def test_run_pre_hooks_no_hooks_proceeds(self, loader):
        """No pre-hooks → proceeds."""
        result = await loader.run_pre_hooks("test-skill", {"input": "test"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_run_post_hooks_log_execution(self, hooked_loader, skill_with_hooks_frontmatter):
        """log_execution post-hook writes to execution log."""
        await hooked_loader.run_post_hooks(
            "hooked-skill",
            {"input": "test input", "duration_ms": 100, "success": True},
            "test result",
        )
        log_file = (
            skill_with_hooks_frontmatter / "skills" / "hooked-skill" / "memory" / "executions.jsonl"
        )
        assert log_file.exists()
        entry = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert entry["input"] == "test input"
        assert entry["success"] is True

    @pytest.mark.asyncio
    async def test_run_post_hooks_no_raise(self, loader):
        """Post hooks with no hooks → no error."""
        # Should not raise
        await loader.run_post_hooks("test-skill", {}, "result")

    @pytest.mark.asyncio
    async def test_hooks_py_loading(self, pyhooked_loader):
        """hooks.py loaded and pre_execute runs correctly."""
        result = await pyhooked_loader.run_pre_hooks(
            "pyhooked-skill", {"input": "test"}
        )
        # hooks.py returns {"proceed": True, "message": "pre-hook ran"}
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_hooks_py_bad_script_no_crash(self, bad_hook_loader):
        """Broken hooks.py → graceful fallback, no crash."""
        # Should not raise — error is logged at WARNING
        result = await bad_hook_loader.run_pre_hooks(
            "bad-hook-skill", {"input": "test"}
        )
        # Despite error, should return proceed=True (default)
        assert result.proceed is True


# ── SK7: Skill Registry & Versioning ────────────────────────────────────────


class TestSK7Registry:
    """Test skill registry with version tracking."""

    def test_registry_auto_creates(self, loader, skill_basic):
        """Registry JSON auto-created on first update."""
        registry_path = skill_basic / "skills_registry.json"
        assert not registry_path.exists()
        loader.update_registry("test-skill")
        assert registry_path.exists()

    def test_update_registry_records_version(self, loader, skill_basic):
        """Version from frontmatter is recorded."""
        loader.update_registry("test-skill")
        registry = json.loads(
            (skill_basic / "skills_registry.json").read_text(encoding="utf-8")
        )
        assert registry["test-skill"]["version"] == "2.1.0"

    def test_update_registry_increments_usage(self, loader, skill_basic):
        """usage_count increments on each update."""
        loader.update_registry("test-skill")
        loader.update_registry("test-skill")
        loader.update_registry("test-skill")
        registry = json.loads(
            (skill_basic / "skills_registry.json").read_text(encoding="utf-8")
        )
        assert registry["test-skill"]["usage_count"] == 3

    def test_update_registry_records_last_used(self, loader, skill_basic):
        """last_used timestamp is set."""
        loader.update_registry("test-skill")
        registry = json.loads(
            (skill_basic / "skills_registry.json").read_text(encoding="utf-8")
        )
        assert "last_used" in registry["test-skill"]
        assert len(registry["test-skill"]["last_used"]) > 10  # ISO format

    def test_update_registry_records_dependencies(self, loader, skill_basic):
        """pip dependencies from metadata are recorded."""
        loader.update_registry("test-skill")
        registry = json.loads(
            (skill_basic / "skills_registry.json").read_text(encoding="utf-8")
        )
        deps = registry["test-skill"].get("dependencies", [])
        assert "requests" in deps
        assert "openpyxl" in deps

    def test_check_dependencies_all_present(self, loader):
        """All deps found (json is stdlib) → empty list."""
        # Create a skill that requires only 'json' (always available)
        meta_str = '{"nanobot":{"requires":{"pip":["json"]}}}'
        skill_dir = loader.workspace / "skills" / "dep-test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: dep-test\ndescription: Dep test.\nmetadata: {meta_str}\n---\n\n# X\n",
            encoding="utf-8",
        )
        missing = loader.check_dependencies("dep-test")
        assert missing == []

    def test_check_dependencies_missing(self, loader):
        """Missing dep → returns its name."""
        meta_str = '{"nanobot":{"requires":{"pip":["nonexistent_pkg_xyz_12345"]}}}'
        skill_dir = loader.workspace / "skills" / "dep-missing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: dep-missing\ndescription: Dep test.\nmetadata: {meta_str}\n---\n\n# X\n",
            encoding="utf-8",
        )
        missing = loader.check_dependencies("dep-missing")
        assert "nonexistent_pkg_xyz_12345" in missing

    def test_registry_summary_format(self, loader, skill_basic):
        """get_registry_summary returns well-formed string."""
        loader.update_registry("test-skill")
        summary = loader.get_registry_summary()
        assert "Skill Registry:" in summary
        assert "test-skill" in summary
        assert "v2.1.0" in summary

    def test_registry_summary_empty(self, loader):
        """Empty registry → empty string."""
        assert loader.get_registry_summary() == ""


# ── SaveSkillTool Integration (SK4/SK7) ─────────────────────────────────────


class TestSaveSkillIntegration:
    """Test SaveSkillTool with new Phase 22B parameters."""

    @pytest.mark.asyncio
    async def test_save_skill_with_version(self):
        """SaveSkillTool writes version in frontmatter."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        ws = Path(tempfile.mkdtemp())
        tool = SaveSkillTool(ws)
        result = await tool.execute(
            name="versioned-skill",
            description="A versioned skill",
            summary="Testing version parameter",
            steps=[{"action": "test step"}],
            version="3.2.1",
        )
        assert "Successfully saved" in result
        content = (ws / "skills" / "versioned-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "version: 3.2.1" in content

    @pytest.mark.asyncio
    async def test_save_skill_with_config(self):
        """SaveSkillTool creates config.defaults.json."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        ws = Path(tempfile.mkdtemp())
        tool = SaveSkillTool(ws)
        result = await tool.execute(
            name="config-skill",
            description="A configurable skill",
            summary="Testing config parameter",
            steps=[{"action": "test step"}],
            config={"max_results": 10, "auto_send": False},
        )
        assert "Successfully saved" in result
        defaults_file = ws / "skills" / "config-skill" / "config.defaults.json"
        assert defaults_file.exists()
        data = json.loads(defaults_file.read_text(encoding="utf-8"))
        assert data["max_results"] == 10
        assert data["auto_send"] is False

    @pytest.mark.asyncio
    async def test_save_skill_with_pip_deps(self):
        """SaveSkillTool writes pip deps in metadata."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        ws = Path(tempfile.mkdtemp())
        tool = SaveSkillTool(ws)
        result = await tool.execute(
            name="dep-skill",
            description="A skill with pip dependencies",
            summary="Testing pip deps",
            steps=[{"action": "test step"}],
            pip_dependencies=["requests", "beautifulsoup4"],
        )
        assert "Successfully saved" in result
        content = (ws / "skills" / "dep-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "requests" in content
        assert "beautifulsoup4" in content

    def test_version_in_parameter_schema(self):
        """version parameter exists in SaveSkillTool schema."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        tool = SaveSkillTool(Path(tempfile.mkdtemp()))
        props = tool.parameters["properties"]
        assert "version" in props

    def test_config_in_parameter_schema(self):
        """config parameter exists in SaveSkillTool schema."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        tool = SaveSkillTool(Path(tempfile.mkdtemp()))
        props = tool.parameters["properties"]
        assert "config" in props
        assert props["config"]["type"] == "object"

    def test_pip_dependencies_in_parameter_schema(self):
        """pip_dependencies parameter exists in SaveSkillTool schema."""
        from nanobot.agent.tools.save_skill import SaveSkillTool
        tool = SaveSkillTool(Path(tempfile.mkdtemp()))
        props = tool.parameters["properties"]
        assert "pip_dependencies" in props
        assert props["pip_dependencies"]["type"] == "array"
