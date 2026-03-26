"""Tests for Phase 27 AST-based sandbox escape fixes in skills.py."""

import pytest
from pathlib import Path
from nanobot.agent.skills import SkillsLoader

# Fixtures for creating mock skill directories
@pytest.fixture
def mock_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws

@pytest.fixture
def skill_loader(mock_workspace: Path) -> SkillsLoader:
    return SkillsLoader(workspace=mock_workspace)

@pytest.mark.asyncio
async def test_ast_sandbox_blocks_direct_import(skill_loader: SkillsLoader, mock_workspace: Path) -> None:
    # Setup mock skill
    skill_dir = mock_workspace / "skills" / "test_skill"
    skill_dir.mkdir(parents=True)
    
    hooks_file = skill_dir / "hooks.py"
    hooks_file.write_text("import os\n\nasync def pre_execute(ctx):\n    return {'proceed': True}", encoding="utf-8")
    
    # Run hooks
    result = await skill_loader._run_hooks_py("test_skill", "pre_execute", {})
    assert result is None, "_run_hooks_py should return None when blocked"

@pytest.mark.asyncio
async def test_ast_sandbox_blocks_dynamic_import(skill_loader: SkillsLoader, mock_workspace: Path) -> None:
    skill_dir = mock_workspace / "skills" / "test_skill2"
    skill_dir.mkdir(parents=True)
    
    hooks_file = skill_dir / "hooks.py"
    hooks_file.write_text("o = __import__('os')\n\nasync def pre_execute(ctx):\n    return {'proceed': True}", encoding="utf-8")
    
    result = await skill_loader._run_hooks_py("test_skill2", "pre_execute", {})
    assert result is None, "_run_hooks_py should block __import__"

@pytest.mark.asyncio
async def test_ast_sandbox_blocks_importlib(skill_loader: SkillsLoader, mock_workspace: Path) -> None:
    skill_dir = mock_workspace / "skills" / "test_skill3"
    skill_dir.mkdir(parents=True)
    
    hooks_file = skill_dir / "hooks.py"
    hooks_file.write_text("import importlib\nmod = importlib.import_module('os')\n\nasync def pre_execute(ctx):\n    return {'proceed': True}", encoding="utf-8")
    
    result = await skill_loader._run_hooks_py("test_skill3", "pre_execute", {})
    assert result is None, "_run_hooks_py should block importlib"

@pytest.mark.asyncio
async def test_ast_sandbox_allows_safe_code(skill_loader: SkillsLoader, mock_workspace: Path) -> None:
    skill_dir = mock_workspace / "skills" / "test_skill4"
    skill_dir.mkdir(parents=True)
    
    hooks_file = skill_dir / "hooks.py"
    hooks_file.write_text("import re\nimport json\n\nasync def pre_execute(ctx):\n    return {'proceed': True, 'message': 'ok'}", encoding="utf-8")
    
    result = await skill_loader._run_hooks_py("test_skill4", "pre_execute", {})
    assert result is not None
    assert result.proceed is True
    assert result.message == 'ok'
