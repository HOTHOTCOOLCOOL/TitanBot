"""Shell execution tool."""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ExecTool(Tool):
    """Tool to execute shell commands."""
    
    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = True,
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\brmdir\s+/s\b",               # rmdir /s
            r"\b(format|mkfs|diskpart)\b",   # disk operations
            r"\bdd\s+if=",                   # dd
            r">\s*/dev/sd",                  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
            # --- Phase 18A: network exfiltration ---
            r"\bcurl\b",                     # curl
            r"\bwget\b",                     # wget
            r"\binvoke-webrequest\b",        # PowerShell web request
            r"\binvoke-restmethod\b",        # PowerShell REST call
            # --- Phase 18A: encoded / obfuscated execution ---
            r"\bpowershell\b.*\s-[eE]nc",    # powershell -enc base64
            r"\bpwsh\b.*\s-[eE]nc",          # pwsh -enc base64
            # --- Phase 18A: pipe to shell ---
            r"\|\s*(bash|sh|cmd|powershell|pwsh)\b",  # echo X | bash
            # --- Phase 18A: destructive PowerShell ---
            r"\bremove-item\b.*-recurse",    # Remove-Item -Recurse
            r"\bstop-process\b",             # Stop-Process
            # --- Phase 18A: reverse shells ---
            r"\bnc\s+-e\b",                  # nc -e /bin/sh
            r"\bncat\b",                     # ncat
            r"/dev/tcp/",                    # bash reverse shell
            # --- Phase 21A (S1): cd traversal ---
            r"\bcd\s+\.\.",                  # cd .. (with or without trailing slash)
            r"\bcd\.\.",                     # cd.. (no space, Windows CMD)
            r"%2e",                          # URL-encoded dot (percent-encoded traversal)
            # --- Phase 21A (S2): interpreter bypass ---
            # NOTE: python -c, node -e are ALLOWED — they are used legitimately
            # by the LLM for PPT generation, data processing, etc.
            # Only block truly dangerous interpreter patterns:
            r"\bruby\s+-e\b",               # ruby -e (eval Ruby)
            r"\bperl\s+-e\b",               # perl -e (eval Perl)
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
    
    @property
    def name(self) -> str:
        return "exec"
    
    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        
        try:
            from nanobot.agent.sandbox import ShellSandbox
            returncode, stdout_str, stderr_str = await ShellSandbox.execute(
                command=command,
                cwd=cwd,
                timeout=self.timeout
            )
            
            output_parts = []
            
            if stdout_str:
                output_parts.append(stdout_str)
            
            if stderr_str:
                if stderr_str.strip():
                    output_parts.append(f"STDERR:\n{stderr_str}")
            
            if returncode != 0:
                output_parts.append(f"\nExit code: {returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # Truncate very long output
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"
            
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            # Only match absolute paths — avoid false positives on relative
            # paths like ".venv/bin/python" where "/bin/python" would be
            # incorrectly extracted by the old pattern.
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
