"""ADR-66 Adversarial Tests: Tool Result Truncation Safety (Fix D2).

Tests that _normalize_tool_result:
  - Does NOT call json.loads() (no OOM risk)
  - Preserves tail content (error stacktraces survive)
  - Never exceeds max_chars in output
  - Handles 1MB+ payloads without memory issues
  - Handles CJK and multi-byte unicode without corruption
"""
import sys
import pytest
from nanobot.agent.loop import _normalize_tool_result


class TestTruncationBehavior:

    def test_short_result_returned_unchanged(self):
        """Results under max_chars must be returned verbatim."""
        text = "hello world"
        result = _normalize_tool_result(text, "exec")
        assert result == text

    def test_output_never_exceeds_max_chars(self):
        """After truncation, output length must never exceed max_chars."""
        big = "x" * 100_000
        result = _normalize_tool_result(big, "exec", max_chars=16_000)
        assert len(result) <= 16_000 + 200, (
            f"Truncated output exceeds max_chars: {len(result)} chars"
        )

    def test_tail_preserved_over_head(self):
        """Error stacktrace at the tail must survive truncation."""
        # Build a 100K string: mostly junk, but a unique error at the very end
        tail_marker = "CRITICAL_EXCEPTION: NullPointerError at line 9999"
        head_junk = "INFO: processing..." * 3000  # ~60K chars
        payload = head_junk + tail_marker

        result = _normalize_tool_result(payload, "exec", max_chars=16_000)
        assert tail_marker in result, (
            "REGRESSION: The tail error message was lost during truncation! "
            "Stacktraces will be invisible to the agent."
        )

    def test_truncation_marker_present(self):
        """Truncated output must include a clear TRUNCATED marker."""
        big = "A" * 50_000
        result = _normalize_tool_result(big, "exec")
        assert "TRUNCATED" in result, "Missing truncation marker in output"

    def test_1mb_payload_no_oom(self):
        """1MB payload must not raise MemoryError or OOM."""
        mega = "z" * 1_024 * 1_024  # 1 MB
        try:
            result = _normalize_tool_result(mega, "exec", max_chars=16_000)
        except MemoryError:
            pytest.fail("MemoryError on 1MB payload — json.loads was likely called")
        assert len(result) <= 16_000 + 200

    def test_exception_result_formatted_correctly(self):
        """BaseException instances must be stringified with 'Error:' prefix."""
        exc = ValueError("something went wrong")
        result = _normalize_tool_result(exc, "exec")
        assert result.startswith("Error:")
        assert "something went wrong" in result

    def test_none_result_returns_empty_marker(self):
        """None results must be represented as '(empty)'."""
        result = _normalize_tool_result(None, "exec")
        assert result == "(empty)"

    def test_cjk_unicode_not_corrupted(self):
        """CJK characters must not be split mid-codepoint during truncation.

        Python str slicing is codepoint-aware (not byte-aware), so truncation
        should never produce replacement characters (U+FFFD) or encoding errors.
        """
        cjk_char = "测"  # 3 bytes in UTF-8, but 1 Unicode codepoint
        payload = cjk_char * 20_000  # 20K chars, ~60K bytes
        result = _normalize_tool_result(payload, "exec", max_chars=16_000)
        # If slicing split a multi-byte char, round-tripping through UTF-8 would raise
        try:
            encoded = result.encode("utf-8")
            decoded = encoded.decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            pytest.fail(f"CJK character corruption detected: {e}")
        # Also verify no replacement character (U+FFFD) crept in
        assert "\ufffd" not in result, "Replacement character U+FFFD found — CJK corruption detected"


    def test_large_json_list_no_json_loads(self):
        """A valid JSON list > max_chars must be truncated as plain text, not parsed."""
        # If json.loads is called, this would be very slow/OOM on large input
        import json
        big_list = json.dumps(["item"] * 10_000)  # ~80K chars
        # Should complete near-instantly (no json.loads)
        import time
        start = time.monotonic()
        result = _normalize_tool_result(big_list, "exec", max_chars=16_000)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Truncation took {elapsed:.2f}s — json.loads may have been called"
        assert len(result) <= 16_000 + 200


class TestTruncationRatio:
    """Verify the 10/90 head/tail ratio is correctly applied."""

    def test_head_is_approximately_10_percent(self):
        """Head of truncated output should be ~10% of max_chars."""
        big = "H" * 8_000 + "T" * 100_000  # Head marker vs tail marker
        result = _normalize_tool_result(big, "exec", max_chars=16_000)
        # First section before TRUNCATED marker should be ~1600 chars of "H"
        parts = result.split("TRUNCATED")
        head_section = parts[0]
        h_count = head_section.count("H")
        assert 1400 <= h_count <= 1800, (
            f"Head section has {h_count} 'H' chars — expected ~1600 (10% of 16000)"
        )
