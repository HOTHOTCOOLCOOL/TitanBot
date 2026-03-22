"""Tests for conditional save prompt logic (Bug 2 fix).

Verifies that the save prompt is only shown when the workflow appears
to have succeeded — not when it failed to find emails or encountered errors.
"""

import pytest
from nanobot.session.manager import Session


# Fail indicators must match those in loop.py _execute_with_llm
# L3: 'no results' was removed — too generic
_FAIL_INDICATORS = [
    "找不到", "没有找到", "未找到", "没找到",
    "无法找到", "无法获取", "无法访问",
    "error:", "not found", "no emails found",
    "无法", "失败", "出错",
    "sorry", "抱歉",
]


def _check_workflow_succeeded(final_content: str) -> bool:
    """Mirror the success check logic from loop.py."""
    content_lower = (final_content or "").lower()
    return not any(ind in content_lower for ind in _FAIL_INDICATORS)


def _check_workflow_succeeded_with_strip(final_content: str) -> bool:
    """Mirror the success check logic from loop.py WITH think tag stripping."""
    from nanobot.utils.think_strip import strip_think_tags
    content = strip_think_tags(final_content) if final_content else ""
    content_lower = content.lower()
    return not any(ind in content_lower for ind in _FAIL_INDICATORS)


class TestFailureDetection:
    """Test that failure indicators are detected correctly."""

    @pytest.mark.parametrize("content", [
        "找不到匹配的邮件",
        "抱歉，没有找到 Harvey 的邮件",
        "Error: Could not connect to Outlook",
        "No emails found matching the criteria.",
        "搜索失败，请稍后重试",
        "无法找到指定的文件夹",
        "Sorry, I couldn't find that email.",
    ])
    def test_failure_detected(self, content: str):
        """Content with error indicators should NOT trigger save."""
        assert _check_workflow_succeeded(content) is False

    @pytest.mark.parametrize("content", [
        "找到了 3 封邮件，以下是结果...",
        "已成功发送邮件给 david@example.com",
        "邮件分析报告：SHV Daily FF&Sales...",
        "Here is the email from Harvey Chen...",
        "附件已保存到临时目录",
    ])
    def test_success_detected(self, content: str):
        """Content without error indicators SHOULD trigger save."""
        assert _check_workflow_succeeded(content) is True


class TestThinkTagStripping:
    """Test that <think> tag content does NOT trigger false failure detection."""

    def test_think_tags_with_failure_words_not_false_positive(self):
        """<think> block containing 无法 should NOT cause false failure."""
        content = (
            "<think>我已经成功将分析报告发送到了David的内部邮箱。"
            "虽然无法直接解析内容，但确认它存在</think>"
            "已成功发送邮件到 david@example.com"
        )
        # Without stripping, this would be a false failure
        assert _check_workflow_succeeded(content) is False
        # With stripping, the actual response is a success
        assert _check_workflow_succeeded_with_strip(content) is True

    def test_think_tags_with_multiple_failure_words(self):
        """<think> block with multiple failure words should still pass."""
        content = (
            "<think>查找了最近的邮件，无法获取附件，失败了一次但重试成功</think>"
            "邮件已找到，以下是内容摘要..."
        )
        assert _check_workflow_succeeded(content) is False
        assert _check_workflow_succeeded_with_strip(content) is True

    def test_actual_failure_not_masked(self):
        """Real failure (not in <think> tags) should still be detected."""
        content = (
            "<think>让我尝试搜索邮件</think>"
            "抱歉，没有找到匹配的邮件"
        )
        assert _check_workflow_succeeded_with_strip(content) is False

    def test_no_think_tags_unchanged(self):
        """Content without <think> tags should behave identically."""
        content = "已成功发送邮件给 Harvey Chen"
        assert _check_workflow_succeeded(content) is True
        assert _check_workflow_succeeded_with_strip(content) is True

    def test_unmatched_think_tag(self):
        """Unmatched <think> (no closing tag) should still be stripped."""
        content = (
            "<think>无法直接解析内容，但确认..."
        )
        # With stripping, unmatched <think> means everything after is stripped
        assert _check_workflow_succeeded_with_strip(content) is True


class TestSavePromptConditional:
    """Test that pending_save is only set on successful workflows."""

    def test_no_pending_save_on_failure(self):
        """When workflow fails, pending_save should NOT be set."""
        session = Session(key="test:1")
        final_content = "抱歉，没有找到匹配的邮件"
        tool_calls = [{"tool": "outlook", "args": {"action": "find_emails"}}]

        # Simulate the conditional logic from loop.py
        if tool_calls:
            if _check_workflow_succeeded(final_content):
                session.pending_save = {"key": "test", "steps": tool_calls}

        assert session.pending_save is None

    def test_pending_save_on_success(self):
        """When workflow succeeds, pending_save SHOULD be set."""
        session = Session(key="test:2")
        final_content = "找到了 Harvey 的邮件，内容如下..."
        tool_calls = [{"tool": "outlook", "args": {"action": "find_emails"}}]

        if tool_calls:
            if _check_workflow_succeeded(final_content):
                session.pending_save = {"key": "test", "steps": tool_calls}

        assert session.pending_save is not None
        assert session.pending_save["key"] == "test"

    def test_no_save_without_tools(self):
        """When no tools are used, pending_save should NOT be set."""
        session = Session(key="test:3")
        tool_calls = []

        if tool_calls:
            session.pending_save = {"key": "test", "steps": tool_calls}

        assert session.pending_save is None

