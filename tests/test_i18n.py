"""Tests for the i18n module."""

from nanobot.agent.i18n import msg, set_language, get_language, MESSAGES


class TestLanguageSettings:
    def test_default_language_is_en(self):
        set_language("en")
        assert get_language() == "en"

    def test_set_language_zh(self):
        set_language("zh")
        assert get_language() == "zh"
        set_language("en")  # reset

    def test_set_invalid_language_defaults_to_en(self):
        set_language("fr")
        assert get_language() == "en"


class TestGetMessage:
    def test_get_message_en(self):
        result = msg("save_confirmed", lang="en")
        assert "✅" in result
        assert "knowledge" in result.lower() or "saved" in result.lower()

    def test_get_message_zh(self):
        result = msg("save_confirmed", lang="zh")
        assert "✅" in result
        assert "知识库" in result

    def test_format_with_kwargs(self):
        result = msg("knowledge_match_prompt", lang="en", key="my_task")
        assert "my_task" in result

    def test_format_with_kwargs_zh(self):
        result = msg("knowledge_match_prompt", lang="zh", key="分析邮件")
        assert "分析邮件" in result

    def test_missing_key_returns_fallback(self):
        result = msg("nonexistent_key")
        assert "missing" in result.lower()

    def test_uses_current_language_when_not_specified(self):
        set_language("zh")
        result = msg("save_confirmed")
        assert "知识库" in result
        set_language("en")  # reset

    def test_all_messages_have_both_languages(self):
        """Ensure every message key has both zh and en translations."""
        for key, templates in MESSAGES.items():
            assert "zh" in templates, f"Missing 'zh' for message '{key}'"
            assert "en" in templates, f"Missing 'en' for message '{key}'"

    def test_processing_error_format(self):
        result = msg("processing_error", lang="en", error="timeout")
        assert "timeout" in result
