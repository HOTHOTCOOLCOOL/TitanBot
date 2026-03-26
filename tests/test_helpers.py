"""Tests for helper utilities."""

import os
from pathlib import Path

from nanobot.utils.helpers import safe_replace


def test_safe_replace_success(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("hello")
    dst.write_text("old")
    
    safe_replace(src, dst)
    assert not src.exists()
    assert dst.read_text() == "hello"


def test_safe_replace_retry_success(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src2.txt"
    dst = tmp_path / "dst2.txt"
    src.write_text("hello")
    
    original_replace = os.replace
    call_count = [0]
    
    def mock_replace(s, d):
        call_count[0] += 1
        if call_count[0] < 3:
            raise PermissionError("Access denied (mock antivirus lock)")
        original_replace(s, d)
        
    monkeypatch.setattr(os, "replace", mock_replace)
    
    # Needs a small base delay for fast tests
    safe_replace(src, dst, max_retries=5, base_delay=0.01)
    
    assert call_count[0] == 3
    assert not src.exists()
    assert dst.read_text() == "hello"


def test_safe_replace_eventual_failure(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src3.txt"
    dst = tmp_path / "dst3.txt"
    src.write_text("hello")
    
    def mock_replace(s, d):
        raise PermissionError("Access denied forever")
        
    monkeypatch.setattr(os, "replace", mock_replace)
    
    import pytest
    with pytest.raises(PermissionError, match="Access denied forever"):
        safe_replace(src, dst, max_retries=3, base_delay=0.01)
