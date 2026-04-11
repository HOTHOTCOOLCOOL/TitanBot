"""Shell execution tool."""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.capability import CapabilityTag

# Pre-compiled patterns for dynamic DESTRUCTIVE tag detection (Phase 45B).
# This is the SINGLE SOURCE OF TRUTH for deciding whether a given exec command
# is dangerous enough to warrant an L1 hard-block.  Plain query commands
# (dir, ls, pwd, echo, etc.) do NOT match these.
#
# ADR-45B Decision 4: All command-level security patterns are consolidated here.
# verification.py's _DESTRUCTIVE_PATTERNS is used ONLY as a no-registry fallback.
_SHELL_DYNAMIC_RISK_PATTERNS: list[re.Pattern] = [
    # --- Interpreter inline execution ---
    # Content-aware match (multi-line \n attacks via DOTALL)
    re.compile(
        r"\bpython\d*\b.*\s-c\s+[\"']?.*(?:import|exec|eval|__import__|base64\.b64decode|os\.|sys\.|subprocess|open\()",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\bnode\s+-e\b", re.IGNORECASE),                 # node -e
    re.compile(r"\bruby\s+-e\b", re.IGNORECASE),                 # ruby -e
    re.compile(r"\bperl\s+-e\b", re.IGNORECASE),                 # perl -e
    # --- Script file execution ---
    re.compile(r"\.py\b", re.IGNORECASE),                        # executing .py script file
    re.compile(r"\.sh\b", re.IGNORECASE),                        # executing .sh script file
    re.compile(r"\.ps1\b", re.IGNORECASE),                       # executing .ps1 PowerShell script
    # --- Code injection primitives ---
    re.compile(r"\beval\b", re.IGNORECASE),                      # eval primitive (shell or python)
    re.compile(r"\b__import__\b"),                               # __import__ bypass
    re.compile(r"\bbase64\b.*\bdecode\b", re.IGNORECASE),        # base64 de-obfuscation
    re.compile(r"\|\s*(bash|sh|cmd|powershell|pwsh)\b", re.IGNORECASE),  # pipe-to-shell injection
    # --- Filesystem-destructive commands (Linux/Unix) ---
    re.compile(r"\brm\s+(-\w+\s+)*-r\w*\s+/(?:\s|$)", re.IGNORECASE),   # rm -rf /
    re.compile(r"\brm\s+(-\w+\s+)*-f\w*r\w*\s+/(?:\s|$)", re.IGNORECASE),  # rm -fr /
    re.compile(r"\bmkfs\b", re.IGNORECASE),                      # mkfs (format filesystem)
    re.compile(r"\bdd\s+.*\bof=/dev/", re.IGNORECASE),           # dd write to disk device
    re.compile(r":\(\)\s*\{\s*:\|\s*:\s*&\s*\}", re.IGNORECASE), # fork bomb
    # --- Filesystem-destructive commands (Windows CMD) ---
    re.compile(r"\bdel\s+/[fq]\b", re.IGNORECASE),              # del /f, del /q
    re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),               # rmdir /s
    re.compile(r"\b(format|diskpart)\b", re.IGNORECASE),         # format/diskpart
    # --- Filesystem-destructive commands (Windows PowerShell) ---
    re.compile(r"\bremove-item\b.*-recurse", re.IGNORECASE),     # Remove-Item -Recurse
    re.compile(r"\bstop-process\b", re.IGNORECASE),              # Stop-Process
    re.compile(r"\bpowershell\b.*\s-[eE]nc", re.IGNORECASE),    # powershell -enc base64
    re.compile(r"\bpwsh\b.*\s-[eE]nc", re.IGNORECASE),          # pwsh -enc base64
    # --- Network exfiltration ---
    re.compile(r"\bcurl\b.+https?://", re.IGNORECASE),           # curl with URL
    re.compile(r"\bwget\b.+https?://", re.IGNORECASE),           # wget with URL
    re.compile(r"\binvoke-webrequest\b", re.IGNORECASE),         # PowerShell web request
    re.compile(r"\binvoke-restmethod\b", re.IGNORECASE),         # PowerShell REST call
    # --- System power and reverse shells ---
    re.compile(r"\b(shutdown|reboot|poweroff)\b", re.IGNORECASE),  # system power
    re.compile(r"\bnc\s+-e\b", re.IGNORECASE),                  # nc -e /bin/sh
    re.compile(r"/dev/tcp/", re.IGNORECASE),                     # bash reverse shell
]

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
        # Phase 45B (ADR-45B Decision 4): Command deny-list logic has been
        # migrated to L1 R-SHELL-GUARD (verification.py) which uses Tag-Driven
        # evaluation via evaluate_dynamic_tags(). This parameter is retained
        # for backward-compatible construction but no longer consumed by
        # _guard_command (which now only enforces path traversal constraints).
        self.deny_patterns = deny_patterns or []
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
    
    @property
    def static_tags(self) -> CapabilityTag:
        # SHELL_EXECUTION: declares exec capability.
        # MUTATIVE: commands may produce persistent side-effects.
        # DESTRUCTIVE is NOT declared statically — evaluate_dynamic_tags() elevates
        # the tag at runtime only when a genuinely dangerous pattern is detected.
        return CapabilityTag.SHELL_EXECUTION | CapabilityTag.MUTATIVE

    def evaluate_dynamic_tags(self, args: dict[str, Any]) -> CapabilityTag:
        """Phase 45B: Dynamically detect high-risk command patterns and elevate to DESTRUCTIVE.

        This is the single source of truth for deciding whether a given exec command
        is safe (routes to HITL approval) or outright dangerous (routes to L1 R-SHELL-GUARD
        hard block). Matches _SHELL_DYNAMIC_RISK_PATTERNS compiled at module level.
        """
        if not isinstance(args, dict):
            return CapabilityTag.NONE
        cmd = str(args.get("command", ""))
        
        # Phase 45B Exception: Allow known built-in skill scripts to execute
        # so they don't trip the general ".py" script execution block (e.g. ssrs-report workflow).
        safe_cmd = re.sub(r"\bfetch_report\.py\b", "SYS_SAFE_SCRIPT", cmd)
        
        for pat in _SHELL_DYNAMIC_RISK_PATTERNS:
            if pat.search(safe_cmd):
                return CapabilityTag.DESTRUCTIVE
        return CapabilityTag.NONE
    
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
        """Execution-layer sandbox: path traversal and workspace confinement only.

        Phase 45B: Command blacklist logic has been moved to L1 VerificationLayer
        (R-SHELL-GUARD rule in verification.py) which runs before tool execution
        and has access to CapabilityTag for Tag-Driven evaluation. This method
        now only enforces physical path constraints that are meaningful at
        execution time (after L1 has already cleared the command semantics).
        """
        cmd = command.strip()

        if self.allow_patterns:
            lower = cmd.lower()
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
