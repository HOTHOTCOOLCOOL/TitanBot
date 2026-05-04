from __future__ import annotations
import asyncio
"""Phase 31→32: Verification Layer — funnel-shaped verification pipeline (L0→L1→L3).

This module implements three progressive verification layers around the AgentLoop:

- **L0  (Pre-cognitive enrichment):** Consolidates experience hints, reflection
  memories, and system reminders into the system prompt before the LLM call.
- **L1  (Rigid rule interception):** Pure-Python checks on proposed tool calls
  *before* execution (parameter validation, safety, loop detection).
- **L3  (Post-reflection extraction):** After the agent loop completes, extracts
  success patterns or error lessons into the Experience Bank.  Also performs
  anti-pattern auditing (log-only) on executed tool calls.

L2 (small-model pre-action introspection) was removed in Phase 32 due to
structural false-reject problems.  See ``docs/L2_VERIFICATION_RETHINK.md``.

Design constraints (from ARCHITECTURE.md):
  • Each layer is individually toggled via ``VerificationConfig``.
  • All layers are *strippable* — they should become unnecessary as base models improve.
  • No new external dependencies.
  • Total context injection stays within ``_INJECTION_BUDGET`` (8000 chars).
"""


import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING


from loguru import logger

if TYPE_CHECKING:
    from nanobot.config.schema import VerificationConfig
    from nanobot.providers.base import LLMProvider

# Budget for all L0 injections (shared with loop.py constant)
_INJECTION_BUDGET = 8000


# ── L1: Rule definitions ──────────────────────────────────────────────

@dataclass
class RuleResult:
    """Result of L1 rule checking."""
    passed: bool
    violations: list[str] = field(default_factory=list)
    rewrite_hint: str | None = None


# Destructive shell patterns (supplement sandbox AST checks)
_DESTRUCTIVE_PATTERNS: list[re.Pattern] = [
    # --- Linux/Unix ---
    re.compile(r"\brm\s+(-\w+\s+)*-r\w*\s+/(?:\s|$)", re.IGNORECASE),
    re.compile(r"\brm\s+(-\w+\s+)*-f\w*r\w*\s+/(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+.*\bof=/dev/", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|\s*:\s*&\s*\}", re.IGNORECASE),  # fork bomb
    # --- Windows CMD (Phase 31 Retro: L1 early interception) ---
    re.compile(r"\bdel\s+/[fq]\b", re.IGNORECASE),
    re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),
    re.compile(r"\b(format|diskpart)\b", re.IGNORECASE),
    # --- Windows PowerShell (Phase 31 Retro) ---
    re.compile(r"\bremove-item\b.*-recurse", re.IGNORECASE),
    re.compile(r"\bstop-process\b", re.IGNORECASE),
    re.compile(r"\bpowershell\b.*\s-[eE]nc", re.IGNORECASE),
    re.compile(r"\bpwsh\b.*\s-[eE]nc", re.IGNORECASE),
    # --- Network exfiltration (Phase 31 Retro) ---
    re.compile(r"\binvoke-webrequest\b", re.IGNORECASE),
    re.compile(r"\binvoke-restmethod\b", re.IGNORECASE),
    # --- Phase 45B: Python interpreter variants & pipe injection ---
    # Content-aware match (multi-line \n attacks via DOTALL)
    re.compile(
        r"\bpython\d*\b.*\s-c\s+[\"']?.*(?:import|exec|eval|__import__|base64\.b64decode|os\.|sys\.|subprocess|open\()",
        re.IGNORECASE | re.DOTALL,
    ),
    # Pipe-to-shell injection (echo X | bash, etc.)
    re.compile(r"\|\s*(bash|sh|cmd|powershell|pwsh)\b", re.IGNORECASE),
]

# Sensitive path prefixes — writing to or executing commands targeting these is blocked
_SENSITIVE_PATHS = [
    # Windows
    "c:\\windows", "c:/windows",
    "c:\\program files", "c:/program files",
    "system32",
    # Unix
    "/etc/", "/boot/", "/usr/bin/", "/usr/sbin/",
    # User secrets
    "/.ssh/", "\\.ssh\\",
    # Windows-native .ssh path (resolved by realpath on Windows: C:\Users\<user>\.ssh)
    os.path.join(os.path.expanduser("~"), ".ssh"),
    os.path.join(os.path.expanduser("~"), ".gnupg"),
    "/.gnupg/", "\\.gnupg\\",

    # macOS specific (Phase 36)
    "/system/library/",
    "/library/launchagents/",
    "/library/launchdaemons/",
    "/library/keychains/",
]


def _looks_like_windows_absolute_path(path: str) -> bool:
    """Return True for drive-letter or UNC Windows paths."""
    return bool(re.match(r"^[a-zA-Z]:[\\/]", path)) or path.startswith("\\\\")


def _should_resolve_sensitive_prefix(path: str) -> bool:
    """Only pre-resolve stable absolute prefixes for the current host OS.

    ADR-66's realpath hardening is for write/edit path prefix checks. On
    Windows, resolving POSIX-rooted entries like ``/etc`` or bare keywords
    like ``system32`` turns them into false absolute paths on the current
    drive (for example ``D:\\etc`` or ``<cwd>\\system32``), which then
    creates false positives. Those entries remain raw substring markers for
    exec-command scanning instead of path-prefix matching.
    """
    expanded = os.path.expanduser(path)
    if os.name == "nt":
        return _looks_like_windows_absolute_path(expanded)
    return expanded.startswith("/")


def _resolve_sensitive_paths() -> set[str]:
    """ADR-66 A1: Pre-resolve _SENSITIVE_PATHS at module load time.

    Uses os.path.realpath to follow symlinks/junction points and normalises
    to lowercase, but only for stable absolute prefixes on the current OS.
    Bare keywords and cross-platform root markers stay out of the prefix set
    so they can continue serving as substring fallbacks for exec-command
    scanning without poisoning write/edit path checks.

    Appends os.sep to directory entries to prevent prefix false-positives
    (e.g. '/etc/pass' must not match '/etc/password_folder').
    """
    resolved: set[str] = set()
    for p in _SENSITIVE_PATHS:
        if not _should_resolve_sensitive_prefix(p):
            continue

        try:
            rp = os.path.normpath(os.path.realpath(os.path.expanduser(p))).lower()
        except (OSError, RuntimeError) as e:
            logger.debug(
                f"R07: Skipping sensitive prefix {p!r} because it could not be resolved: {e!r}"
            )
            continue

        # Ensure directory entries end with separator for startswith safety
        if not rp.endswith(os.sep):
            rp = rp + os.sep
        resolved.add(rp)
    return resolved


# Pre-resolved at module import — zero per-call I/O overhead
_SENSITIVE_PATHS_RESOLVED: set[str] = _resolve_sensitive_paths()

# Network exfiltration patterns — commands that send data to external hosts
_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bcurl\b.+https?://", re.IGNORECASE),
    re.compile(r"\bwget\b.+https?://", re.IGNORECASE),
    re.compile(r"\bInvoke-WebRequest\b.+https?://", re.IGNORECASE),
    re.compile(r"\bInvoke-RestMethod\b.+https?://", re.IGNORECASE),
]

# Max exec command length before we consider it suspicious (likely injection)
_EXEC_MAX_LENGTH = 2000

# Max tool calls in a single turn
_MAX_TOOL_CALLS_PER_TURN = 8


def _check_rule_message_content(tool_calls: list[Any]) -> list[str]:
    """R01: message tool must have non-empty content."""
    violations = []
    for tc in tool_calls:
        if tc.name == "message":
            content = tc.arguments.get("content", "")
            if not content or not str(content).strip():
                violations.append(
                    "R01: 'message' tool was called with empty content. "
                    "Please provide actual content to send."
                )
    return violations


def _check_rule_destructive_exec(tool_calls: list[Any]) -> list[str]:
    """R02: exec tool must not contain destructive commands."""
    violations = []
    for tc in tool_calls:
        if tc.name == "exec":
            command = tc.arguments.get("command", "")
            for pat in _DESTRUCTIVE_PATTERNS:
                if pat.search(command):
                    violations.append(
                        f"R02: Potentially destructive command detected: "
                        f"'{command[:100]}'. This command has been blocked for safety."
                    )
                    break
    return violations


def _check_rule_duplicate_calls(tool_calls: list[Any]) -> list[str]:
    """R03: Detect duplicate tool calls within a single turn (≥3 identical)."""
    if len(tool_calls) < 3:
        return []

    sig_counts: dict[str, int] = {}
    for tc in tool_calls:
        sig = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
        sig_counts[sig] = sig_counts.get(sig, 0) + 1

    violations = []
    for sig, count in sig_counts.items():
        if count >= 3:
            tool_name = sig.split(":")[0]
            violations.append(
                f"R03: Tool '{tool_name}' was called {count} times with identical "
                f"parameters in a single turn. This looks like a loop — please vary "
                f"your approach."
            )
    return violations


def _check_rule_outlook_recipient(tool_calls: list[Any]) -> list[str]:
    """R04: outlook send_email must have a non-empty recipient."""
    violations = []
    for tc in tool_calls:
        if tc.name == "outlook":
            action = tc.arguments.get("action", "")
            if action == "send_email":
                recipient = tc.arguments.get("recipient", "") or tc.arguments.get("to", "")
                if not recipient or not str(recipient).strip():
                    violations.append(
                        "R04: 'outlook' send_email was called without a recipient. "
                        "Please specify the 'recipient' address."
                    )
    return violations


def _check_rule_exec_length(tool_calls: list[Any]) -> list[str]:
    """R05: exec command length limit (>2000 chars → likely injection)."""
    violations = []
    for tc in tool_calls:
        if tc.name == "exec":
            command = tc.arguments.get("command", "")
            if len(command) > _EXEC_MAX_LENGTH:
                violations.append(
                    f"R05: exec command is {len(command)} chars (limit: {_EXEC_MAX_LENGTH}). "
                    f"Unusually long commands may indicate injection. Please break into smaller steps."
                )
    return violations


def _check_rule_sensitive_path(
    tool_calls: list[Any],
    *,
    extra_deny: list[str] | None = None,
    workspace: Path | str | None = None,
) -> list[str]:
    """R07: write_file / edit_file / exec must not target sensitive system paths.

    ADR-66 A2: Hardened path traversal defense.
    - write_file / edit_file: resolved via os.path.realpath to defeat ../
      traversal, symlink, and Windows Junction Point attacks. Matched against
      _SENSITIVE_PATHS_RESOLVED using startswith (pre-computed at module load).
    - exec: the argument is a shell command, not a path — realpath is NOT
      applied (would corrupt matching). Existing substring regex is retained.

    Phase 35v2: Also checks ``edit_file`` (closing a real blind spot) and
    supports configurable deny patterns from ``VerificationConfig.path_deny_patterns``.
    """
    import os
    violations = []
    for tc in tool_calls:
        if tc.name in ("write_file", "edit_file"):
            raw_path = str(tc.arguments.get("path", "") or tc.arguments.get("file_path", ""))
            workspace_root: Path | None = None

            if workspace is not None:
                try:
                    workspace_root = Path(workspace).expanduser().resolve(strict=False)
                except (OSError, RuntimeError) as e:
                    logger.warning(
                        f"R07: Failed to resolve workspace root for boundary check: {e!r}"
                    )
                    violations.append(
                        "R07: Workspace boundary check failed while resolving the workspace directory. "
                        "Refusing write until the target path can be verified."
                    )
                    continue

            try:
                target_path = Path(raw_path).expanduser()
                if workspace_root is not None and not target_path.is_absolute():
                    target_path = workspace_root / target_path
                resolved_path = target_path.resolve(strict=False)
            except (OSError, RuntimeError) as e:
                logger.warning(
                    f"R07: Failed to resolve write target '{raw_path}': {e!r}"
                )
                violations.append(
                    "R07: Unable to resolve write target path. Refusing write until the target path can be "
                    "checked against the workspace directory."
                )
                continue

            if workspace_root is not None and not resolved_path.is_relative_to(workspace_root):
                violations.append(
                    "R07: Out of bounds write. Target path must be within the workspace directory."
                )
                continue

            resolved = str(resolved_path).lower()

            # L2 fix (A1+B2): Split prefix-check path from glob-match path.
            # - resolved_prefix: has trailing os.sep for startswith safety
            #   (prevents '/etc/pass' matching '/etc/password_folder')
            # - resolved: raw realpath result WITHOUT trailing sep — used for
            #   fnmatch glob matching (trailing sep breaks exact-file patterns
            #   like 'c:\app\.env' and '**/.env')
            resolved_norm = os.path.normpath(resolved)
            if not resolved_norm.endswith(os.sep):
                resolved_prefix = resolved_norm + os.sep
            else:
                resolved_prefix = resolved_norm

            blocked = False
            for sensitive in _SENSITIVE_PATHS_RESOLVED:
                if resolved_prefix.startswith(sensitive):
                    violations.append(
                        f"R07: Operation targets a sensitive system path '{sensitive.rstrip(os.sep)}'. "
                        f"This has been blocked for safety."
                    )
                    blocked = True
                    break

            # Configurable deny patterns (Glob via fnmatch)
            # L2 fix: Use resolved_norm (no trailing sep) for fullpath glob,
            # and os.path.basename(resolved_norm) for filename-level patterns
            # like '*.env'.  normpath handles mixed separators and double
            # slashes, preventing empty-basename edge cases in fallback paths.
            if not blocked and extra_deny:
                resolved_basename = os.path.basename(resolved_norm).lower()
                for pattern in extra_deny:
                    pat_lower = pattern.lower()
                    if (fnmatch.fnmatch(resolved_norm, pat_lower)
                            or fnmatch.fnmatch(resolved_basename, pat_lower)):
                        violations.append(
                            f"R07: Path matches deny pattern '{pattern}'. "
                            f"This has been blocked by sandbox configuration."
                        )
                        break

        elif tc.name == "exec":
            # exec argument is a shell command string — do NOT run realpath on it
            # (would produce garbage). Keep substring regex matching.
            command_lower = tc.arguments.get("command", "").lower()
            for sensitive in _SENSITIVE_PATHS:
                if sensitive in command_lower:
                    violations.append(
                        f"R07: exec command references a sensitive path '{sensitive}'. "
                        f"This has been blocked for safety."
                    )
                    break

    return violations


def _check_rule_tool_call_count(tool_calls: list[Any]) -> list[str]:
    """R08: Single-turn tool call count limit (>8 calls → suspicious)."""
    if len(tool_calls) > _MAX_TOOL_CALLS_PER_TURN:
        return [
            f"R08: {len(tool_calls)} tool calls in a single turn exceeds the limit "
            f"of {_MAX_TOOL_CALLS_PER_TURN}. Please break your work into smaller steps."
        ]
    return []


def _check_rule_network_exfiltration(tool_calls: list[Any]) -> list[str]:
    """R09: exec must not contain network exfiltration commands (curl/wget + external URLs)."""
    violations = []
    for tc in tool_calls:
        if tc.name == "exec":
            command = tc.arguments.get("command", "")
            for pat in _EXFIL_PATTERNS:
                if pat.search(command):
                    violations.append(
                        f"R09: Network exfiltration pattern detected in exec command: "
                        f"'{command[:100]}'. Use the dedicated web_search or browser tool instead."
                    )
                    break
    return violations


def _check_rule_browser_use_ssrf(tool_calls: list[Any]) -> list[str]:
    """R10: browser_use_worker tasks must not contain SSRF/local file targets."""
    violations = []
    for tc in tool_calls:
        if tc.name == "browser_use_worker":
            task = str(tc.arguments.get("task", "")).lower()
            if any(forbidden in task for forbidden in ["127.0.0.1", "localhost", "file://", "0.0.0.0", "192.168.", "10."]):
                violations.append(
                    "R10: 'browser_use_worker' task contains restricted local IPs, domains or file URIs. "
                    "This has been blocked for SSRF/sandbox protection."
                )
    return violations


# ADR-66 A3: Three-tier SSRS fatal detection — no DOTALL to prevent cross-message false positives
_SSRS_FATAL_PATTERNS: list[re.Pattern] = [
    re.compile(r'"error_type"\s*:\s*"DependencyFatal"'),       # Standard JSON format
    re.compile(r'error_type["\s:]+DependencyFatal'),              # Loose / reformatted variant
    re.compile(r'(?:error|fatal|failed)[^\n]{0,80}DependencyFatal'),  # Contextual bare keyword
]


def _check_rule_ssrs_fatal(tool_calls: list[Any], messages: list[dict] | None = None) -> list[str]:
    """R-SSRS-001: Block outlook search and other workaround attempts after SSRS fatal failure (ADR-44).

    ADR-66 A3: Replaced hard-coded magic string match with a 3-tier regex cascade.
    DOTALL is intentionally omitted to prevent cross-message false positives
    (e.g. user asking 'what is DependencyFatal?' triggering the rule).
    Each pattern is tested against individual message content strings only.
    """
    if not messages:
        return []

    # Check if SSRS failed in recent history
    ssrs_failed = False
    for m in reversed(messages):
        content = str(m.get("content", ""))
        if any(pat.search(content) for pat in _SSRS_FATAL_PATTERNS):
            ssrs_failed = True
            break
        # Stop looking back too far (just current conversation turn)
        if m.get("role") == "user":
            break
            
    if not ssrs_failed:
        return []
        
    violations = []
    for tc in tool_calls:
        # Prevent searching or accessing outlook differently if SSRS failed
        if tc.name == "outlook" and tc.arguments.get("action", "") in ("find_emails", "search_email", "read_email"):
            violations.append(
                "R-SSRS-001: The SSRS report dependency has failed. "
                "Do NOT attempt to use outlook search or read to find a replacement report. "
                "Instead, notify the user immediately that the required report is unavailable and output an error."
            )
    return violations


def _check_rule_destructive_guard(
    tool_calls: list[Any],
    *,
    registry: Any | None = None,
    config_overrides: dict | None = None,
) -> list[str]:
    """R-DESTRUCTIVE-GUARD: 全局 Tag-Driven 毙灭性操作硬阻断 (ADR-61 重构自 R-SHELL-GUARD).

    对所有工具一视同仁：只要 evaluate_dynamic_tags() 合成出的 effective_tags
    包含 DESTRUCTIVE，无视工具名称，L1 立即硬阻断。

    ADR-45B 中原始版本限制于具有 SHELL_EXECUTION 静态标签的工具，
    这使得 RPA 等工具返回的 DESTRUCTIVE 标签无法被任何 L1 规则捕获（时序漏洞）。
    本规则通层泪汾这个盲区。

    降级兼容：当 registry 为 None 时（如单元测试运行环境），回退到针对
    'exec' 工具的 _DESTRUCTIVE_PATTERNS 静态正则扫描。
    """
    from nanobot.agent.capability import CapabilityTag
    violations = []
    for tc in tool_calls:
        if not hasattr(tc, "arguments") or not isinstance(tc.arguments, dict):
            continue

        tool_impl = registry.get(tc.name) if registry else None

        if tool_impl is None:
            # 无 registry：回退针对 'exec' 的静态正则扫描
            if tc.name != "exec":
                continue
            cmd = tc.arguments.get("command", "")
            for pat in _DESTRUCTIVE_PATTERNS:
                if pat.search(cmd):
                    violations.append(
                        f"R-DESTRUCTIVE-GUARD: Destructive command pattern detected in 'exec': "
                        f"'{cmd[:100]}'. This has been automatically blocked."
                    )
                    break
            continue

        # 【核心变更】：移除 SHELL_EXECUTION 前置限制，所有工具一视同仁
        # ADR-45B 原始版仅对 SHELL_EXECUTION 工具生效，导致
        # RPA evaluate_dynamic_tags() 返回的 DESTRUCTIVE 标签无人消费。

        override_val = config_overrides.get(tc.name) if config_overrides else None
        config_override = CapabilityTag(override_val) if override_val is not None else None

        try:
            effective = tool_impl.get_effective_tags(tc.arguments, config_override=config_override)
        except Exception as e:
            # evaluate_dynamic_tags 抛异常时：fallback 到 static_tags 并打印可见日志
            # 注意：不能静默降级（会掩盖 Tool 实现中的隐蛘 Bug）
            logger.error(
                f"R-DESTRUCTIVE-GUARD: evaluate_dynamic_tags failed for tool '{tc.name}': {e}. "
                f"Falling back to static_tags only."
            )
            effective = tool_impl.static_tags

        if effective & CapabilityTag.DESTRUCTIVE:
            violations.append(
                f"R-DESTRUCTIVE-GUARD: DESTRUCTIVE capability detected on tool '{tc.name}'. "
                f"Blocked automatically — no approval path exists."
            )
    return violations


# All L1 rules in evaluation order
_L1_RULES = [
    _check_rule_message_content,
    _check_rule_destructive_exec,
    _check_rule_duplicate_calls,
    _check_rule_outlook_recipient,
    _check_rule_exec_length,
    _check_rule_sensitive_path,
    _check_rule_tool_call_count,
    _check_rule_network_exfiltration,
    _check_rule_browser_use_ssrf,
    _check_rule_ssrs_fatal,
    _check_rule_destructive_guard,  # ADR-61: 全工具通用 DESTRUCTIVE 硬阻断（取代 R-SHELL-GUARD）
]


# ── Main class ─────────────────────────────────────────────────────────

class VerificationLayer:
    """Phase 31→32: Funnel-shaped verification pipeline (L0→L1→L3).

    All methods are designed to be called from AgentLoop and are safe to
    skip entirely when all layers are disabled.
    """

    def __init__(
        self,
        config: VerificationConfig,
        provider: LLMProvider | None = None,
        model: str | None = None,
        knowledge_workflow: Any | None = None,
    ):
        self.config = config
        self.provider = provider
        self.model = model
        self.knowledge_workflow = knowledge_workflow

    def _iter_ki_rule_dirs(self) -> list[Path]:
        """Return candidate KI rule directories in lookup order."""
        candidates: list[Path] = []

        config_workspace = getattr(self.config, "workspace", None)
        if config_workspace:
            candidates.append(Path(config_workspace).expanduser() / ".nanobot" / "ki_rules")

        workflow_workspace = getattr(
            getattr(self, "knowledge_workflow", None), "workspace", None
        )
        if workflow_workspace:
            candidates.append(Path(workflow_workspace).expanduser() / ".nanobot" / "ki_rules")

        candidates.append(Path.cwd() / ".nanobot" / "ki_rules")
        candidates.append(Path(__file__).resolve().parents[2] / ".nanobot" / "ki_rules")

        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.expanduser().resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)

        return unique_candidates

    def _get_ki_rules_dir(self) -> Path | None:
        """Pick the first existing KI rule directory."""
        for candidate in self._iter_ki_rule_dirs():
            if candidate.is_dir():
                return candidate
        return None

    # ── L0: Pre-cognitive Experience Enrichment ───────────────────────

    def enrich_context(
        self,
        system_messages: list[dict],
        request_text: str,
        session_message_count: int,
        *,
        memory_features: Any | None = None,
    ) -> int:
        """L0: Inject experience hints, reflections, and system reminders.

        Consolidates the injection logic previously scattered across
        ``loop.py`` L816-L864 into a single method.

        Args:
            system_messages: The initial_messages list (system_messages[0]
                must be the system prompt dict with role='system').
            request_text: The current user request text.
            session_message_count: ``session.message_count_since_consolidation``.
            memory_features: MemoryFeaturesConfig instance (for feature gates).

        Returns:
            Number of characters injected (for budget tracking).
        """
        if not self.config.l0_enabled:
            return 0

        if not system_messages or system_messages[0].get("role") != "system":
            return 0

        injection_used = 0

        # 0. KI Rules (Phase 59: Short-circuit tactical rules)
        try:
            ki_dir = self._get_ki_rules_dir()

            if ki_dir:
                mtime = ki_dir.stat().st_mtime
                for ki_file in ki_dir.glob("*.ki.json"):
                    f_mtime = ki_file.stat().st_mtime
                    if f_mtime > mtime:
                        mtime = f_mtime

                cache_dir = str(ki_dir.expanduser().resolve(strict=False))
                if (
                    getattr(self, "_ki_rules_cache", None) is None
                    or getattr(self, "_ki_rules_mtime", 0) < mtime
                    or getattr(self, "_ki_rules_cache_dir", None) != cache_dir
                ):
                    self._ki_rules_cache = []
                    self._ki_rules_mtime = mtime
                    self._ki_rules_cache_dir = cache_dir
                    for ki_file in ki_dir.glob("*.ki.json"):
                        try:
                            with ki_file.open("r", encoding="utf-8") as fp:
                                data = json.load(fp)
                                self._ki_rules_cache.append({
                                    "name": ki_file.name,
                                    "keywords": [k.lower() for k in data.get("keywords", [])],
                                    "rule": data.get("rule", "")[:500]  # Runtime strict truncation
                                })
                        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as e:
                            logger.debug(
                                f"L0: Skipping KI rule {ki_file.name} due to load failure: {e!r}"
                            )

                request_lower = request_text.lower()
                for ki in self._ki_rules_cache:
                    if any(k in request_lower for k in ki["keywords"]):
                        rule_text = f"\n\n## 🛡️ Tactical Rule ({ki['name']}):\n{ki['rule']}\n"
                        if injection_used + len(rule_text) <= _INJECTION_BUDGET:
                            system_messages[0]["content"] += rule_text
                            injection_used += len(rule_text)
                            logger.debug(f"L0: Injected KI rule {ki['name']}")
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug(f"KI Rules injection skipped: {e}")

        # 1. Experience Bank tactical hints
        if (getattr(memory_features, 'experience_enabled', True)
                and self.knowledge_workflow):
            experience_hint = self.knowledge_workflow.match_experience(request_text)
            if experience_hint:
                hint_text = (
                    "\n\n## 💡 Helpful Experience / Tactical Hint:\n"
                    f"{experience_hint}\n"
                    "Consider applying this hint if it's relevant to solving the task."
                )
                if injection_used + len(hint_text) <= _INJECTION_BUDGET:
                    system_messages[0]["content"] += hint_text
                    injection_used += len(hint_text)



        # 3. Long-session System Reminder
        if session_message_count >= 15:
            reminder_text = (
                "\n\n## ⚠️ System Reminder\nYou have executed many steps in this "
                "session. Please verify your current objective against the original "
                "request, and consider summarizing your progress to conclude if "
                "appropriate."
            )
            if injection_used + len(reminder_text) <= _INJECTION_BUDGET:
                system_messages[0]["content"] += reminder_text
                injection_used += len(reminder_text)
                logger.debug("L0: Injected System Reminder for long session.")

        return injection_used

    # ── L1: Rigid Rule Interception ───────────────────────────────────

    def check_rules(
        self,
        tool_calls: list[Any],
        messages: list[dict] | None = None,
        *,
        registry: Any | None = None,
        config_overrides: dict | None = None,
        workspace: Path | str | None = None,
    ) -> RuleResult:
        """L1: Run all rigid rules against proposed tool calls.

        Called *after* the LLM proposes tool calls but *before* they execute.

        Args:
            tool_calls: List of ToolCall objects from the LLM response.
            messages: Conversation history (used by context-sensitive rules).
            registry: ToolRegistry instance for Tag-Driven rules (R-SHELL-GUARD).
            config_overrides: Per-tool capability tag overrides from config.

        Returns:
            RuleResult with pass/fail status and any violation messages.
        """
        if not self.config.l1_enabled:
            return RuleResult(passed=True)

        # Phase 35v2: Read configurable deny patterns
        extra_deny = getattr(self.config, 'path_deny_patterns', None) or None

        all_violations: list[str] = []
        for rule_fn in _L1_RULES:
            if rule_fn is _check_rule_sensitive_path:
                violations = rule_fn(tool_calls, extra_deny=extra_deny, workspace=workspace)
            elif rule_fn is _check_rule_ssrs_fatal:
                violations = rule_fn(tool_calls, messages=messages)
            elif rule_fn is _check_rule_destructive_guard:
                violations = rule_fn(
                    tool_calls,
                    registry=registry,
                    config_overrides=config_overrides,
                )
            else:
                violations = rule_fn(tool_calls)
            all_violations.extend(violations)

        if all_violations:
            hint = (
                "The following issues were detected with your proposed actions:\n"
                + "\n".join(f"- {v}" for v in all_violations)
                + "\nPlease correct your approach and try again."
            )
            logger.warning(f"L1: {len(all_violations)} rule violation(s) detected")
            return RuleResult(
                passed=False,
                violations=all_violations,
                rewrite_hint=hint,
            )

        return RuleResult(passed=True)

    # ── L3: Post-reflection & Knowledge Extraction ───────────────────

    # Known anti-patterns to detect in executed tool calls (log-only)
    _ANTIPATTERNS = [
        {
            "id": "AP01",
            "desc": "Unnecessary pip install — a dedicated tool or pre-installed package may exist",
            "match": lambda tc: tc.name == "exec" and "pip install" in tc.arguments.get("command", ""),
        },
        {
            "id": "AP02",
            "desc": "Used exec for a task where a dedicated tool exists (e.g., curl instead of browser/web_search)",
            "match": lambda tc: (
                tc.name == "exec"
                and any(kw in tc.arguments.get("command", "").lower() for kw in ["curl ", "wget "])
            ),
        },
    ]

    def audit_antipatterns(
        self,
        tool_calls_with_args: list[dict],
        retry_count: int = 0,
    ) -> list[str]:
        """L3 anti-pattern audit: detect known bad patterns in executed tool calls.

        **Phase 32: log-only** — findings are returned for logging, NOT auto-written
        to Experience Bank.  A future config flag can enable auto-writing after
        manual review confirms detection quality.

        Args:
            tool_calls_with_args: List of {"tool": name, "args": dict} records
                from the completed agent loop.
            retry_count: Number of retries observed during the loop.

        Returns:
            List of human-readable finding strings (empty if none detected).
        """
        if not self.config.l3_enabled:
            return []

        findings: list[str] = []

        # Check static anti-patterns
        for record in tool_calls_with_args:
            # Build a lightweight duck-typed object for the matcher lambdas
            class _TC:
                def __init__(self, name: str, arguments: dict):
                    self.name = name
                    self.arguments = arguments
            tc = _TC(record.get("tool", ""), record.get("args", {}))
            for ap in self._ANTIPATTERNS:
                try:
                    if ap["match"](tc):
                        findings.append(f"{ap['id']}: {ap['desc']} — tool={tc.name}")
                except (AttributeError, KeyError, TypeError, ValueError) as e:
                    logger.debug(
                        "L3 anti-pattern matcher failed for %s: %r"
                        % (ap.get("id", "unknown"), e)
                    )

        # Check retry threshold
        if retry_count >= 3:
            findings.append(
                f"AP03: High retry count ({retry_count}) — agent may be stuck in a retry loop"
            )

        for f in findings:
            logger.info(f"L3 anti-pattern: {f}")

        return findings

    async def post_reflect(
        self,
        request_text: str,
        final_content: str,
        tools_used: list[str],
        tool_calls_with_args: list[dict],
        session: Any,
        exit_kind: str,
    ) -> None:
        """L3: Extract success patterns or failure lessons after agent loop.

        This consolidates and extends the existing P29-1/P29-5 extraction:
        - On SUCCESS with ≥N tools: extract a "success pattern" into Experience Bank
        - On FAILURE: existing directive/reflection mechanisms handle this

        This method is designed to be called as a fire-and-forget async task.

        Args:
            request_text: The original user request.
            final_content: The agent's final response text.
            tools_used: List of tool names used during execution.
            tool_calls_with_args: Detailed tool call records.
            session: The current Session object.
            exit_kind: The exit status of the loop ("success", "abort", "failure").
        """
        if not self.config.l3_enabled:
            return

        if not self.knowledge_workflow or not self.provider:
            return

        min_tools = self.config.l3_success_pattern_min_tools

        # Phase 39: Removed early return (min_tools or chitchat drops) to allow high-entropy
        # conversational preferences to reach reflection.
        # if len(tools_used) < min_tools:
        #     return

        # Check if the workflow succeeded (relying on ExitKind instead of _FAIL_INDICATORS)
        workflow_failed = exit_kind != "success"

        if workflow_failed:
            # Failure patterns are handled by existing P29-1 (directive signal)
            # and P29-5 (circuit breaker auto-experience). No new action needed.
            return

        # Success path: extract a success pattern
        try:
            # Build a compact summary of the successful workflow
            tool_sequence = " → ".join(tools_used[:10]) if tools_used else "None (Conversational/Chitchat)"
            prompt = (
                f"The user requested: {request_text[:300]}\n\n"
                f"The agent generated this response using these tools: "
                f"{tool_sequence}\n\n"
                f"Result summary: {final_content[:300]}\n\n"
                "⚠️ 熵密度约束 (ENTROPY DENSITY CONSTRAINT):\n"
                "仅当内容携带高密度的信息熵（例如明确的个人偏好、业务逻辑设定、关键知识点）时才执行写入。绝对忽略日常闲聊、早午安问候或无逻辑价值的短句。如果你认为内容无价值，请输出空对象的JSON: {}\n\n"
                "Extract a concise, reusable \"Success Pattern\" or \"Preference\" for similar future "
                "requests. Return ONLY a valid JSON object:\n"
                "{\n"
                '  "trigger": "A short phrase describing the type of request '
                '(e.g., \'Send sales report email\')",\n'
                '  "prompt": "The recommended tool sequence or key preference '
                '(e.g., \'Use outlook.read_email → attachment_analyzer → message\')"\n'
                "}\n"
                "No markdown fences."
            )

            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a metacognitive component. Respond ONLY in strict JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=200,
            )

            text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            import json_repair
            result = json_repair.loads(text)

            if (isinstance(result, dict)
                    and "trigger" in result and "prompt" in result
                    and self.knowledge_workflow.knowledge_store):
                self.knowledge_workflow.knowledge_store.add_experience(
                    context_trigger=result["trigger"],
                    tactical_prompt=f"SUCCESS PATTERN: {result['prompt']}",
                    action_type="success_pattern",
                )
                logger.info(
                    f"L3: Extracted success pattern for '{result['trigger'][:60]}'"
                )

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"L3: Success pattern extraction failed: {e}")
