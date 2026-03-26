"""Subprocess-based Sandboxing for Execution Layer (Phase 28B)."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.loader import get_config


class ShellSandbox:
    """Sandbox for executing shell commands with restricted environment."""

    @staticmethod
    async def execute(
        command: str,
        cwd: str,
        timeout: int | None = None
    ) -> tuple[int, str, str]:
        """
        Execute a shell command in a highly restricted subprocess environment.
        Strips most environment variables to prevent leakage of API keys
        or other sensitive information.
        """
        config = get_config()
        timeout = timeout or config.agents.sandbox.shell_timeout_seconds

        # Strip environment variables
        # On Windows, keep essential variables required for basic process execution
        essential_vars = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP"}
        env = {k: v for k, v in os.environ.items() if k.upper() in essential_vars}

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                return process.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()  # Ensure child process is reaped (BUG-3)
                return -1, "", f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return -1, "", f"Subprocess creation failed: {e}"


class PythonSandbox:
    """Sandbox for executing Python hooks in an isolated process."""

    @staticmethod
    async def run_hook(
        hooks_file: Path,
        hook_name: str,
        context: dict[str, Any],
        result_content: str | None = None
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Execute a python hook in a restricted subprocess via sandbox_worker.py.
        Returns: (success_bool, message_string, result_dict)
        """
        config = get_config()
        timeout = config.agents.sandbox.python_timeout_seconds
        
        worker_script = Path(__file__).parent / "sandbox_worker.py"
        
        # -I: Isolate from user environment
        # -S: Disable site-packages (no installed modules, only standard library)
        # Note: loguru is used inside worker for error printing, so maybe we can't fully drop -S,
        # but we can try -I and rely on sys.addaudithook for the actual sandbox.
        # Actually, let's just use -I for isolation + sys.addaudithook
        cmd = [
            sys.executable,
            "-I",
            str(worker_script),
            str(hooks_file),
            hook_name
        ]
        
        # Prepare input payload for stdin
        payload = {
            "context": context,
            "result": result_content,
            "workspace": str(config.workspace_path),
            "allow_network": config.agents.sandbox.allow_network
        }
        
        # Same environment stripping as shell (SEC-3: PYTHONPATH removed — -I flag handles isolation)
        essential_vars = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE"}
        env = {k: v for k, v in os.environ.items() if k.upper() in essential_vars}
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(config.workspace_path)
            )
            
            payload_bytes = json.dumps(payload).encode("utf-8")
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(payload_bytes),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()  # Ensure child process is reaped (BUG-3)
                return False, f"Hook execution timed out after {timeout} seconds", None
                
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            if process.returncode != 0:
                logger.warning(f"Python sandbox worker failed (code {process.returncode}): {stderr_str}")
                return False, f"Sandbox Error: {stderr_str}", None
                
            if stdout_str:
                try:
                    result_data = json.loads(stdout_str)
                    return result_data.get("success", True), result_data.get("message", ""), result_data.get("result", None)
                except json.JSONDecodeError:
                    return False, f"Sandbox failed to return valid JSON: {stdout_str}\nStderr: {stderr_str}", None
                    
            return True, "", None
            
        except Exception as e:
            return False, f"Failed to run Python sandbox: {e}", None
