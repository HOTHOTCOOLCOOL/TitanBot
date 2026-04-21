import ast
import asyncio
from pathlib import Path

import pytest

from nanobot.agent.skills import SkillsLoader, _VALIDATOR_ALLOWED_IMPORTS
from nanobot.utils.exceptions import ToolValidationFailure, SkillLoadError
from nanobot.config.schema import Config

@pytest.fixture
def tmp_workspace(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return tmp_path

@pytest.fixture
def loader(tmp_workspace):
    return SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))

@pytest.fixture
def mock_config():
    cfg = Config()
    cfg.agents.validator.enabled = True
    cfg.agents.validator.timeout_ms = 200
    return cfg

def create_skill(workspace, name, validator_code=None):
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    if validator_code is not None:
        (skill_dir / "validator.py").write_text(validator_code, encoding="utf-8")
    return skill_dir

def test_load_validator_success(loader, tmp_workspace):
    skill_dir = create_skill(tmp_workspace, "valid_skill", "def validate(action, ctx): pass")
    mod = loader._load_validator(skill_dir, "valid_skill")
    assert mod is not None
    assert hasattr(mod, "validate")

def test_load_validator_not_found(loader, tmp_workspace):
    skill_dir = create_skill(tmp_workspace, "no_validator_skill")
    mod = loader._load_validator(skill_dir, "no_validator_skill")
    assert mod is None

@pytest.mark.parametrize("bad_import", ["os", "subprocess", "sys", "importlib", "builtins", "string"])
def test_load_validator_blocked_imports(loader, tmp_workspace, bad_import):
    code = f"import {bad_import}\ndef validate(a, c): pass"
    skill_dir = create_skill(tmp_workspace, f"bad_skill_{bad_import}", code)
    with pytest.raises(SkillLoadError) as exc:
        loader._load_validator(skill_dir, f"bad_skill_{bad_import}")
    assert "forbidden import" in str(exc.value)

@pytest.mark.parametrize("blocked_module", ["os", "subprocess", "sys", "importlib", "builtins", "inspect", "typing", "string"])
def test_load_validator_blocked_from_imports(loader, tmp_workspace, blocked_module):
    code = f"from {blocked_module} import something\ndef validate(a, c): pass"
    skill_dir = create_skill(tmp_workspace, f"bad_from_{blocked_module}", code)
    with pytest.raises(SkillLoadError) as exc:
        loader._load_validator(skill_dir, f"bad_from_{blocked_module}")
    assert "forbidden import" in str(exc.value)

@pytest.mark.parametrize("bad_call", ["eval('1')", "exec('pass')", "getattr(object, '__doc__')", "__import__('os')"])
def test_load_validator_blocked_calls(loader, tmp_workspace, bad_call):
    code = f"def validate(a, c):\n    {bad_call}"
    skill_dir = create_skill(tmp_workspace, f"bad_call_skill", code)
    with pytest.raises(SkillLoadError) as exc:
        loader._load_validator(skill_dir, f"bad_call_skill")
    assert "forbidden call" in str(exc.value)

@pytest.mark.asyncio
async def test_run_validator_success(loader, tmp_workspace):
    code = "def validate(action, ctx):\n    pass"
    skill_dir = create_skill(tmp_workspace, "run_success", code)
    mod = loader._load_validator(skill_dir, "run_success")
    # Should not raise any exception
    await loader._run_validator(mod, "test_action", {"input": "test"}, "run_success")

@pytest.mark.asyncio
async def test_run_validator_reject(loader, tmp_workspace):
    code = (
        "def validate(action, ctx):\n"
        "    if action == 'forbidden':\n"
        "        raise ToolValidationFailure('blocked by validator', 'run_reject')\n"
    )
    skill_dir = create_skill(tmp_workspace, "run_reject", code)
    mod = loader._load_validator(skill_dir, "run_reject")
    with pytest.raises(ToolValidationFailure) as exc:
        await loader._run_validator(mod, "forbidden", {"input": "test"}, "run_reject")
    assert "blocked by validator" in str(exc.value)

@pytest.mark.asyncio
async def test_run_validator_timeout(loader, tmp_workspace):
    code = (
        "import time\n"
        "def validate(action, ctx):\n"
        "    time.sleep(1)\n"
    )
    skill_dir = create_skill(tmp_workspace, "run_timeout", code)
    mod = loader._load_validator(skill_dir, "run_timeout")
    with pytest.raises(ToolValidationFailure) as exc:
        await loader._run_validator(mod, "test", {}, "run_timeout", timeout_ms=50)
    assert "timed out" in str(exc.value)

@pytest.mark.asyncio
async def test_run_validator_crash_fail_open(loader, tmp_workspace):
    code = "def validate(action, ctx):\n    raise RuntimeError('random crash')"
    skill_dir = create_skill(tmp_workspace, "run_crash", code)
    mod = loader._load_validator(skill_dir, "run_crash")
    # Should skip safely (fail-open) and log warning
    from unittest.mock import patch
    with patch("nanobot.agent.skills.logger.warning") as mock_logger:
        await loader._run_validator(mod, "test", {}, "run_crash")
        assert mock_logger.called

@pytest.mark.asyncio
async def test_run_pre_hooks_integration(loader, tmp_workspace, mock_config):
    from unittest.mock import patch
    with patch("nanobot.agent.skills.get_config", return_value=mock_config):
        code = (
            "def validate(action, ctx):\n"
            "    if action == 'bad':\n"
            "        raise ToolValidationFailure('no bad actions', 'test')\n"
        )
        create_skill(tmp_workspace, "hook_test", code)
        
        # Valid action
        res = await loader.run_pre_hooks("hook_test", {"action": "good"})
        assert res.proceed is True

        # Invalid action
        with pytest.raises(ToolValidationFailure) as exc:
            await loader.run_pre_hooks("hook_test", {"action": "bad"})
        assert "no bad actions" in str(exc.value)
