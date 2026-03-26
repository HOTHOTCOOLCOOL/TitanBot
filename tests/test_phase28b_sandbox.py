import os
import sys
import json
import pytest
import asyncio
from pathlib import Path

from unittest.mock import patch
from nanobot.config.schema import Config
from nanobot.agent.sandbox import PythonSandbox, ShellSandbox


@pytest.fixture(autouse=True)
def setup_config():
    # Create an empty test config
    test_config = Config()
    
    # We need to setup a mock workspace
    test_workspace = Path("tests/mock_workspace").resolve()
    test_workspace.mkdir(parents=True, exist_ok=True)
    test_config.agents.defaults.workspace = str(test_workspace)
    
    with patch("nanobot.agent.sandbox.get_config", return_value=test_config):
        yield


@pytest.mark.asyncio
async def test_python_sandbox_success(tmp_path):
    """Test that a benign hook executes successfully."""
    hooks_file = tmp_path / "hooks.py"
    hooks_file.write_text(
        "def pre_execute(context):\n"
        "    return {'proceed': True, 'message': 'OK', 'context_val': context.get('val')}\n",
        encoding="utf-8"
    )

    success, message, result = await PythonSandbox.run_hook(
        hooks_file=hooks_file,
        hook_name="pre_execute",
        context={"val": 42}
    )

    assert success is True
    assert message == ""
    assert result is not None
    assert result["proceed"] is True
    assert result["message"] == "OK"
    assert result["context_val"] == 42


@pytest.mark.asyncio
async def test_python_sandbox_blocks_subprocess(tmp_path):
    """Test that dangerous subprocess calls are blocked."""
    hooks_file = tmp_path / "hooks.py"
    hooks_file.write_text(
        "import os\n"
        "def pre_execute(context):\n"
        "    os.system('echo malicious')\n"
        "    return {'proceed': True}\n",
        encoding="utf-8"
    )

    success, message, result = await PythonSandbox.run_hook(
        hooks_file=hooks_file,
        hook_name="pre_execute",
        context={}
    )

    assert success is False
    assert "Sandbox Violation: Subprocess execution is blocked" in message


@pytest.mark.asyncio
async def test_python_sandbox_blocks_network(tmp_path):
    """Test that network calls are blocked by default."""
    hooks_file = tmp_path / "hooks.py"
    hooks_file.write_text(
        "import urllib.request\n"
        "def pre_execute(context):\n"
        "    urllib.request.urlopen('http://example.com')\n"
        "    return {'proceed': True}\n",
        encoding="utf-8"
    )

    success, message, result = await PythonSandbox.run_hook(
        hooks_file=hooks_file,
        hook_name="pre_execute",
        context={}
    )

    assert success is False
    assert "Sandbox Violation" in message


@pytest.mark.asyncio
async def test_python_sandbox_blocks_out_of_workspace_write(tmp_path):
    """Test that writing outside the workspace is blocked."""
    hooks_file = tmp_path / "hooks.py"
    
    # We will try to write to a random file above the workspace
    out_file = Path("C:/hacked_sandbox_test.txt") if os.name == "nt" else Path("/hacked_sandbox_test.txt")
    
    # Using open explicitly
    hooks_file.write_text(
        f"def pre_execute(context):\n"
        f"    with open(r'{str(out_file)}', 'w') as f:\n"
        f"        f.write('hacked')\n"
        f"    return {{'proceed': True}}\n",
        encoding="utf-8"
    )

    success, message, result = await PythonSandbox.run_hook(
        hooks_file=hooks_file,
        hook_name="pre_execute",
        context={}
    )

    assert success is False
    assert "Sandbox Violation: Write access outside workspace blocked" in message


@pytest.mark.asyncio
async def test_shell_sandbox_environment_strip():
    """Test that ShellSandbox strips environment variables correctly."""
    
    shell_cmd = "echo %SENSITIVE_VAR%" if os.name == "nt" else "echo $SENSITIVE_VAR"
    
    # Set sensitive variable
    os.environ["SENSITIVE_VAR"] = "TOP_SECRET!"
    
    try:
        returncode, stdout, stderr = await ShellSandbox.execute(
            command=shell_cmd,
            cwd=os.getcwd()
        )
        
        # It should echo nothing or %SENSITIVE_VAR% verbatim depending on shell, but not TOP_SECRET
        assert "TOP_SECRET!" not in stdout
        assert returncode == 0
    finally:
        del os.environ["SENSITIVE_VAR"]
