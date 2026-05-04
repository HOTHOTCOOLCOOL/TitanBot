"""ADR-66 Adversarial Tests: SSRS Fatal Rule False Positive Prevention (Fix D3).

Tests that _check_rule_ssrs_fatal:
  - Correctly detects the standard JSON error format
  - Correctly detects loose/reformatted variants
  - Does NOT trigger on unrelated messages containing the bare keyword in context
  - Does NOT use DOTALL cross-message matching (the core false-positive risk)
"""
import pytest
from unittest.mock import MagicMock
from nanobot.agent.verification import _check_rule_ssrs_fatal


def _make_tc(name: str, action: str = "") -> MagicMock:
    tc = MagicMock()
    tc.name = name
    tc.arguments = {"action": action}
    return tc


def _make_messages(*contents_by_role) -> list[dict]:
    """Build a message list from (role, content) pairs."""
    return [{"role": role, "content": content} for role, content in contents_by_role]


OUTLOOK_TC = [_make_tc("outlook", action="find_emails")]


class TestSSRSFatalDetection:
    """Positive tests: rule MUST trigger when SSRS has failed."""

    def test_standard_json_format_detected(self):
        """Standard JSON format with quotes and colon must be detected."""
        messages = _make_messages(
            ("tool", '{"error_type": "DependencyFatal", "detail": "SSRS unavailable"}'),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert result, "Standard JSON DependencyFatal format not detected"

    def test_loose_format_detected(self):
        """Reformatted/loose variant without exact quotes must still be detected."""
        messages = _make_messages(
            ("tool", "error_type: DependencyFatal (SSRS connection refused)"),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert result, "Loose DependencyFatal variant not detected"

    def test_bare_keyword_detected(self):
        """Bare 'DependencyFatal' keyword in message must trigger rule."""
        messages = _make_messages(
            ("tool", "Fatal error encountered: DependencyFatal. Aborting."),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert result, "Bare DependencyFatal keyword not detected"

    def test_only_outlook_search_blocked(self):
        """After SSRS failure, only outlook search actions must be blocked."""
        messages = _make_messages(
            ("tool", '{"error_type": "DependencyFatal"}'),
        )
        non_outlook_tc = [_make_tc("exec", action="")]
        result = _check_rule_ssrs_fatal(non_outlook_tc, messages=messages)
        assert not result, "Non-outlook tool was incorrectly blocked by SSRS rule"


class TestSSRSFatalFalsePositives:
    """Negative tests: rule must NOT trigger on irrelevant content."""

    def test_no_ssrs_error_no_block(self):
        """Normal conversation without SSRS error must not trigger rule."""
        messages = _make_messages(
            ("user", "Please search my email for the quarterly report"),
            ("assistant", "I'll search your inbox now."),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert not result, "False positive: SSRS rule triggered with no error in history"

    def test_user_asking_about_dependencyfatal_no_block(self):
        """User question containing 'DependencyFatal' must NOT trigger rule.

        This is the core DOTALL false positive scenario from ADR-66 C6:
        A user asks 'what is DependencyFatal?' in the same conversation
        where error_type appeared in an earlier unrelated message.
        """
        messages = _make_messages(
            ("tool", '{"status": "ok", "error_type": "none"}'),  # 'error_type' present but not fatal
            ("user", "what is DependencyFatal and how do I fix it?"),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert not result, (
            "FALSE POSITIVE: User question about DependencyFatal triggered SSRS block! "
            "DOTALL cross-message matching is causing false positives."
        )

    def test_dependencyfatal_in_resolved_message_no_block(self):
        """If DependencyFatal appeared before a user turn, it should not trigger.

        Rule only looks back within the current conversation turn (stops at 'user' role).
        """
        messages = _make_messages(
            ("tool", '{"error_type": "DependencyFatal"}'),  # Old error
            ("user", "Ok, try a different approach"),       # User turn resets context
            ("assistant", "I'll search emails instead"),
        )
        # The check should stop at the 'user' role and not see the old tool error
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert not result, (
            "False positive: SSRS error from before user turn is incorrectly triggering rule."
        )

    def test_empty_messages_no_block(self):
        """Empty message list must not trigger rule."""
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=[])
        assert not result

    def test_none_messages_no_block(self):
        """None messages must not trigger rule."""
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=None)
        assert not result

    def test_similar_error_type_no_block(self):
        """Different error_type values must not trigger SSRS rule."""
        messages = _make_messages(
            ("tool", '{"error_type": "NetworkTimeout", "detail": "connection refused"}'),
        )
        result = _check_rule_ssrs_fatal(OUTLOOK_TC, messages=messages)
        assert not result, "False positive: NetworkTimeout error triggered SSRS rule"
