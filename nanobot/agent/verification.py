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

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
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
    "/.gnupg/", "\\.gnupg\\",
]

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
                to = tc.arguments.get("to", "")
                if not to or not str(to).strip():
                    violations.append(
                        "R04: 'outlook' send_email was called without a recipient. "
                        "Please specify the 'to' address."
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


def _check_rule_sensitive_path(tool_calls: list[Any]) -> list[str]:
    """R07: write_file / exec must not target sensitive system paths."""
    violations = []
    for tc in tool_calls:
        path_to_check = ""
        if tc.name == "write_file":
            path_to_check = tc.arguments.get("path", "")
        elif tc.name == "exec":
            path_to_check = tc.arguments.get("command", "")
        else:
            continue

        path_lower = path_to_check.lower()
        for sensitive in _SENSITIVE_PATHS:
            if sensitive in path_lower:
                violations.append(
                    f"R07: Operation targets a sensitive system path containing '{sensitive}'. "
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
        reflection_store: Any | None = None,
    ):
        self.config = config
        self.provider = provider
        self.model = model
        self.knowledge_workflow = knowledge_workflow
        self.reflection_store = reflection_store

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

        # 2. Metacognitive Reflection Memory (negative examples)
        if (getattr(memory_features, 'reflection_enabled', True)
                and self.reflection_store):
            try:
                reflections = self.reflection_store.search_reflections(request_text)
                if reflections:
                    reflection_text = "## ⚠️ Avoid Past Mistakes (Negative Examples)\n"
                    for r in reflections:
                        reflection_text += f"- **When**: {r.get('trigger', '')}\n"
                        reflection_text += f"  - **Mistake**: {r.get('failure_reason', '')}\n"
                        reflection_text += f"  - **Correction**: {r.get('corrective_action', '')}\n"
                    if injection_used + len(reflection_text) <= _INJECTION_BUDGET:
                        system_messages[0]["content"] += f"\n\n{reflection_text}"
                        injection_used += len(reflection_text)
            except Exception as e:
                logger.error(f"L0: Failed to inject reflection memory: {e}")

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

    def check_rules(self, tool_calls: list[Any]) -> RuleResult:
        """L1: Run all rigid rules against proposed tool calls.

        Called *after* the LLM proposes tool calls but *before* they execute.

        Args:
            tool_calls: List of ToolCall objects from the LLM response.

        Returns:
            RuleResult with pass/fail status and any violation messages.
        """
        if not self.config.l1_enabled:
            return RuleResult(passed=True)

        all_violations: list[str] = []
        for rule_fn in _L1_RULES:
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
                except Exception:
                    pass

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
        """
        if not self.config.l3_enabled:
            return

        if not self.knowledge_workflow or not self.provider:
            return

        min_tools = self.config.l3_success_pattern_min_tools

        # Only extract success patterns for non-trivial workflows
        if len(tools_used) < min_tools:
            return

        # Check if the workflow succeeded (no fail indicators)
        from nanobot.agent.loop import _FAIL_INDICATORS
        content_lower = (final_content or "").lower()
        workflow_failed = any(ind in content_lower for ind in _FAIL_INDICATORS)

        if workflow_failed:
            # Failure patterns are handled by existing P29-1 (directive signal)
            # and P29-5 (circuit breaker auto-experience). No new action needed.
            return

        # Success path: extract a success pattern
        try:
            # Build a compact summary of the successful workflow
            tool_sequence = " → ".join(tools_used[:10])
            prompt = (
                f"The user requested: {request_text[:300]}\n\n"
                f"The agent successfully completed the task using these tools: "
                f"{tool_sequence}\n\n"
                f"Result summary: {final_content[:300]}\n\n"
                "Extract a concise, reusable \"Success Pattern\" for similar future "
                "requests. Return ONLY a valid JSON object:\n"
                "{\n"
                '  "trigger": "A short phrase describing the type of request '
                '(e.g., \'Send sales report email\')",\n'
                '  "prompt": "The recommended tool sequence and key parameters '
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
            logger.error(f"L3: Success pattern extraction failed: {e}")
