"""Test: token usage tracking in MetricsCollector."""

import pytest
from nanobot.utils.metrics import MetricsCollector


class TestTokenTracking:
    """Verify token usage recording and reporting."""

    def setup_method(self):
        self.m = MetricsCollector()

    def test_initial_state(self):
        """New collector should have zero token stats."""
        tokens = self.m.get_tokens()
        assert tokens["calls"] == 0
        assert tokens["prompt_tokens"] == 0
        assert tokens["completion_tokens"] == 0
        assert tokens["total_tokens"] == 0

    def test_record_single_call(self):
        """Recording a single call should update all fields."""
        self.m.record_tokens(prompt=100, completion=50, total=150)
        tokens = self.m.get_tokens()
        assert tokens["calls"] == 1
        assert tokens["prompt_tokens"] == 100
        assert tokens["completion_tokens"] == 50
        assert tokens["total_tokens"] == 150

    def test_record_multiple_calls(self):
        """Multiple calls should accumulate correctly."""
        self.m.record_tokens(prompt=100, completion=50, total=150)
        self.m.record_tokens(prompt=200, completion=80, total=280)
        self.m.record_tokens(prompt=50, completion=20, total=70)

        tokens = self.m.get_tokens()
        assert tokens["calls"] == 3
        assert tokens["prompt_tokens"] == 350
        assert tokens["completion_tokens"] == 150
        assert tokens["total_tokens"] == 500

    def test_auto_compute_total(self):
        """If total=0, it should be computed as prompt + completion."""
        self.m.record_tokens(prompt=100, completion=50, total=0)
        tokens = self.m.get_tokens()
        assert tokens["total_tokens"] == 150

    def test_explicit_total_overrides(self):
        """Explicit total should be used even if != prompt + completion."""
        self.m.record_tokens(prompt=100, completion=50, total=200)
        tokens = self.m.get_tokens()
        assert tokens["total_tokens"] == 200

    def test_report_includes_tokens(self):
        """Report should include token section when tokens are recorded."""
        self.m.record_tokens(prompt=500, completion=200, total=700)
        report = self.m.report()
        assert "Tokens" in report
        assert "LLM calls: 1" in report
        assert "prompt: 500" in report
        assert "completion: 200" in report
        assert "total: 700" in report

    def test_report_excludes_tokens_when_empty(self):
        """Report should not include token section when no tokens recorded."""
        self.m.increment("test_counter")
        report = self.m.report()
        assert "Tokens" not in report

    def test_reset_clears_tokens(self):
        """Reset should clear token stats."""
        self.m.record_tokens(prompt=100, completion=50, total=150)
        self.m.reset()
        tokens = self.m.get_tokens()
        assert tokens["calls"] == 0
        assert tokens["total_tokens"] == 0

    def test_zero_prompt_completion(self):
        """Zero prompt and completion should still count the call."""
        self.m.record_tokens(prompt=0, completion=0, total=0)
        tokens = self.m.get_tokens()
        assert tokens["calls"] == 1
        assert tokens["total_tokens"] == 0
