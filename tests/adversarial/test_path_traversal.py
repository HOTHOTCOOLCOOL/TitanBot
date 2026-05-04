"""ADR-66 Adversarial Tests: Path Traversal Defense (Fix V1).

Tests that _check_rule_sensitive_path correctly blocks:
  - Standard sensitive paths
  - Relative path traversal (../) bypass attempts
  - Symlink-style paths (we can test the resolution logic even without real symlinks)
  - Windows vs Unix path normalization

These tests target the EXACT attack vectors identified in the pre-Phase 37 audit.
"""
import os
import pytest
from unittest.mock import MagicMock

from nanobot.agent.verification import _check_rule_sensitive_path


def _make_tc(name: str, **kwargs) -> MagicMock:
    """Build a fake ToolCall object."""
    tc = MagicMock()
    tc.name = name
    tc.arguments = kwargs
    return tc


# ── write_file tests ──────────────────────────────────────────────────────────

class TestWriteFilePathTraversal:
    def test_direct_sensitive_path_blocked(self):
        """Direct write to system32 must be blocked."""
        tc = _make_tc("write_file", path="c:\\windows\\system32\\evil.dll")
        result = _check_rule_sensitive_path([tc])
        assert result, "Expected violation for direct system32 path"
        assert "R07" in result[0]

    def test_traversal_bypass_blocked(self):
        """../  traversal into system32 must be blocked (ADR-66 core fix)."""
        tc = _make_tc("write_file", path="c:\\program files\\myapp\\..\\..\\windows\\system32\\evil.dll")
        result = _check_rule_sensitive_path([tc])
        assert result, (
            "REGRESSION: Path traversal via ../ was NOT blocked! "
            "realpath resolution is not working."
        )

    def test_forward_slash_traversal_blocked(self):
        """Forward-slash traversal must also be blocked."""
        tc = _make_tc("write_file", path="c:/users/public/../../windows/system32/evil.dll")
        result = _check_rule_sensitive_path([tc])
        assert result, "REGRESSION: Forward-slash traversal bypass not blocked."

    def test_safe_workspace_path_allowed(self):
        """Legitimate workspace writes must not be blocked."""
        tc = _make_tc("write_file", path="d:\\python\\nanobot\\output\\result.json")
        result = _check_rule_sensitive_path([tc])
        assert not result, f"False positive: legitimate path was blocked. Got: {result}"

    def test_similar_prefix_not_blocked(self):
        """Paths like 'c:\\windows_backup' must NOT match 'c:\\windows'."""
        tc = _make_tc("write_file", path="c:\\windows_backup\\report.txt")
        result = _check_rule_sensitive_path([tc])
        assert not result, (
            f"False positive: 'c:\\windows_backup' should not match 'c:\\windows'. Got: {result}"
        )

    def test_ssh_dir_blocked(self):
        """Write to .ssh directory must be blocked."""
        import os
        # Use a platform-correct path: expanduser resolves ~ to actual home dir
        ssh_path = os.path.join(os.path.expanduser("~"), ".ssh", "authorized_keys")
        tc = _make_tc("write_file", path=ssh_path)
        result = _check_rule_sensitive_path([tc])
        assert result, f"Expected violation for .ssh path write: {ssh_path}"

    def test_unix_etc_false_positive_on_windows(self):
        """writing to local drive \etc folder should not be blocked on Windows."""
        import sys
        if sys.platform == "win32":
            tc = _make_tc("write_file", path="d:\\etc\\config.json")
            result = _check_rule_sensitive_path([tc])
            assert not result, f"False positive: d:\\etc\\config.json was blocked on Windows! Got: {result}"

    def test_bare_keyword_false_positive(self):
        """writing to local CWD/system32 should not be blocked just because 'system32' is a keyword."""
        import sys
        if sys.platform == "win32":
            import os
            cwd_sys32 = os.path.join(os.getcwd(), "system32", "file.dll")
            tc = _make_tc("write_file", path=cwd_sys32)
            result = _check_rule_sensitive_path([tc])
            assert not result, f"False positive: {cwd_sys32} was blocked on Windows! Got: {result}"


# ── edit_file tests ───────────────────────────────────────────────────────────

class TestEditFilePathTraversal:
    def test_edit_system_file_blocked(self):
        """edit_file targeting program files must be blocked."""
        tc = _make_tc("edit_file", file_path="c:\\program files\\common files\\evil.cfg")
        result = _check_rule_sensitive_path([tc])
        assert result, "Expected violation for edit_file to program files"

    def test_edit_traversal_blocked(self):
        """edit_file with traversal must be blocked."""
        # Use a simple traversal from a Windows temp dir into system32
        tc = _make_tc("edit_file", file_path="c:\\temp\\..\\windows\\system32\\drivers\\etc\\hosts")
        result = _check_rule_sensitive_path([tc])
        assert result, "REGRESSION: edit_file traversal bypass not blocked."


# ── exec tests: must NOT use realpath (command is not a path) ─────────────────

class TestExecCommandHandling:
    def test_exec_with_system32_reference_blocked(self):
        """exec command mentioning system32 must still be caught by substring match."""
        tc = _make_tc("exec", command="copy malicious.exe c:\\windows\\system32\\svchost.exe")
        result = _check_rule_sensitive_path([tc])
        assert result, "Expected violation for exec command referencing system32"

    def test_exec_normal_command_allowed(self):
        """Normal exec commands must not be blocked."""
        tc = _make_tc("exec", command="python -m pytest tests/ -v")
        result = _check_rule_sensitive_path([tc])
        assert not result, f"False positive on normal exec command. Got: {result}"

    def test_exec_is_not_path_resolved(self):
        """Confirm exec does NOT apply realpath (would corrupt 'del /f ...' commands)."""
        # This command contains a path-like argument but is not a write_file call.
        # It should match on the 'system32' substring, NOT via realpath.
        tc = _make_tc("exec", command="del /f system32\\evil.dll")
        result = _check_rule_sensitive_path([tc])
        assert result, "Expected 'system32' substring match in exec command"
