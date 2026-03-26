"""Tests for Phase 26A — Plugin Dependency Management.

Covers:
- BrowserConfig schema defaults and customization
- _check_requirements() extended pip support
- _get_missing_requirements() extended pip reporting
- install_dependencies() status reporting
- do_install_dependencies() subprocess pip install
- list_skills() filtering with pip deps
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from nanobot.agent.skills import SkillsLoader
from nanobot.config.schema import BrowserConfig, AgentsConfig


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with skills dir."""
    (tmp_path / "skills").mkdir()
    return tmp_path


def _create_skill(workspace, name, pip_deps=None, bins=None, env_vars=None):
    """Helper to create a skill with specific requirements."""
    requires = {}
    if pip_deps:
        requires["pip"] = pip_deps
    if bins:
        requires["bins"] = bins
    if env_vars:
        requires["env"] = env_vars

    meta = json.dumps({"nanobot": {"requires": requires}})
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n"
        f"name: {name}\n"
        f"description: Test skill for Phase 26A.\n"
        f"category: infra_ops\n"
        f"metadata: {meta}\n"
        f"---\n\n"
        f"# {name}\n\nBody.\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def loader(tmp_workspace):
    return SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))


# ── BrowserConfig Schema ───────────────────────────────────────────────────


class TestBrowserConfig:
    """Test BrowserConfig Pydantic model."""

    def test_defaults(self):
        """BrowserConfig() produces expected defaults."""
        cfg = BrowserConfig()
        assert cfg.enabled is True
        assert cfg.headless is True
        assert cfg.default_timeout_ms == 30000
        assert cfg.viewport_width == 1920
        assert cfg.viewport_height == 1080
        assert cfg.max_pages == 5
        assert cfg.session_ttl_hours == 24
        assert cfg.trusted_domains == []
        assert cfg.block_internal_ips is True

    def test_in_agents_config(self):
        """AgentsConfig has a browser field of type BrowserConfig."""
        agents = AgentsConfig()
        assert isinstance(agents.browser, BrowserConfig)

    def test_custom_values(self):
        """BrowserConfig accepts custom values."""
        cfg = BrowserConfig(
            headless=False,
            max_pages=10,
            trusted_domains=["*.company.com", "erp.internal.io"],
        )
        assert cfg.headless is False
        assert cfg.max_pages == 10
        assert len(cfg.trusted_domains) == 2


# ── _check_requirements with pip ────────────────────────────────────────────


class TestCheckRequirementsPip:
    """Test _check_requirements() extended pip support."""

    def test_pip_present(self, loader, tmp_workspace):
        """Skill with pip dep that exists (json is stdlib) → True."""
        _create_skill(tmp_workspace, "pip-ok", pip_deps=["json"])
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "pip-ok" in names

    def test_pip_missing(self, loader, tmp_workspace):
        """Skill with missing pip dep → filtered out."""
        _create_skill(tmp_workspace, "pip-bad", pip_deps=["nonexistent_xyz_99"])
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "pip-bad" not in names

    def test_pip_missing_unfiltered(self, loader, tmp_workspace):
        """Skill with missing pip dep still shows with filter_unavailable=False."""
        _create_skill(tmp_workspace, "pip-bad2", pip_deps=["nonexistent_xyz_99"])
        skills = loader.list_skills(filter_unavailable=False)
        names = [s["name"] for s in skills]
        assert "pip-bad2" in names

    def test_mixed_requirements_all_met(self, loader, tmp_workspace):
        """Skill with both bins and pip deps, all met → True."""
        # 'python' binary should exist on PATH
        _create_skill(tmp_workspace, "mixed-ok", pip_deps=["json"], bins=["python"])
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "mixed-ok" in names


# ── _get_missing_requirements with pip ──────────────────────────────────────


class TestGetMissingRequirementsPip:
    """Test _get_missing_requirements() pip reporting."""

    def test_reports_pip_missing(self, loader, tmp_workspace):
        """Missing pip dep shows as 'PIP: package_name'."""
        _create_skill(tmp_workspace, "missing-pip", pip_deps=["nonexistent_xyz_99"])
        summary = loader.build_skills_summary()
        assert "PIP: nonexistent_xyz_99" in summary

    def test_no_missing_no_requires_tag(self, loader, tmp_workspace):
        """All deps met → no <requires> tag in XML."""
        _create_skill(tmp_workspace, "all-ok", pip_deps=["json"])
        summary = loader.build_skills_summary()
        # The skill should be available=true, no <requires>
        assert 'available="true"' in summary


# ── install_dependencies ────────────────────────────────────────────────────


class TestInstallDependencies:
    """Test install_dependencies() reporting method."""

    def test_all_present(self, loader, tmp_workspace):
        """All deps satisfied → returns (True, message)."""
        _create_skill(tmp_workspace, "inst-ok", pip_deps=["json"])
        ok, msg = loader.install_dependencies("inst-ok")
        assert ok is True
        assert "already installed" in msg.lower()

    def test_missing_reports(self, loader, tmp_workspace):
        """Missing deps → returns (False, description with package names)."""
        _create_skill(tmp_workspace, "inst-miss", pip_deps=["nonexistent_xyz_99"])
        ok, msg = loader.install_dependencies("inst-miss")
        assert ok is False
        assert "nonexistent_xyz_99" in msg

    def test_no_skill(self, loader):
        """Non-existent skill → (True, all satisfied) since no deps declared."""
        ok, msg = loader.install_dependencies("ghost-skill")
        assert ok is True


# ── do_install_dependencies ─────────────────────────────────────────────────


class TestDoInstallDependencies:
    """Test do_install_dependencies() subprocess pip install."""

    def test_success(self):
        """Mocked successful pip install → (True, stdout)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed fake-pkg-1.0"
        with patch("nanobot.agent.skills.subprocess.run", return_value=mock_result) as mock_run:
            ok, output = SkillsLoader.do_install_dependencies(["fake-pkg"])
            assert ok is True
            assert "Successfully installed" in output
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == sys.executable
            assert "pip" in cmd
            assert "fake-pkg" in cmd

    def test_failure(self):
        """Mocked failed pip install → (False, stderr)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: Could not find a version"
        with patch("nanobot.agent.skills.subprocess.run", return_value=mock_result):
            ok, output = SkillsLoader.do_install_dependencies(["bad-pkg"])
            assert ok is False
            assert "ERROR" in output

    def test_timeout(self):
        """Subprocess timeout → (False, timeout message)."""
        with patch(
            "nanobot.agent.skills.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=300),
        ):
            ok, output = SkillsLoader.do_install_dependencies(["slow-pkg"])
            assert ok is False
            assert "timed out" in output.lower()

    def test_empty_packages(self):
        """Empty package list → (True, no-op message)."""
        ok, output = SkillsLoader.do_install_dependencies([])
        assert ok is True
        assert "no packages" in output.lower()
