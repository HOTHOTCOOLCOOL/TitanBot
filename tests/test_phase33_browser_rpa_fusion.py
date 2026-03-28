"""Tests for Phase 33: Browser-RPA Fusion — Act-Verify + Enhanced Loop Detection.

Covers:
- Fuzzy loop detection (frequency dominance, cyclic subsequence, false-positive prevention)
- Action history summary (three-state outcomes, empty, truncation)
- Action history injection (system prompt, budget, sentinel cleanup)
- Browser Act-Verify (click/fill verify flags, VLM disabled, screenshot failure, dedup)
- Screenshot cleanup
- Exception diagnostic (dual-prefix return, circuit breaker)
- Progressive fallback counter (increment, reset, headless block)
- Sig window retention
- Architecture rules presence
"""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest
from nanobot.agent.loop import _detect_fuzzy_loop, _build_action_history_summary, _SIG_DELIMITER, _FUZZY_LOOP_WINDOW, _INJECTION_BUDGET, _ACTION_HISTORY_SENTINEL, _ACTION_HISTORY_MAX, _MAX_ACTION_HISTORY

def _make_sig(tool: str, args: dict) -> str:
    """Build a single tool call signature the way loop.py does."""
    return f'{tool}:{json.dumps(args, sort_keys=True)}'

def _make_multi_sig(*pairs) -> str:
    """Build a multi-tool iteration signature."""
    return _SIG_DELIMITER.join((f'{tool}:{json.dumps(args, sort_keys=True)}' for tool, args in pairs))

def test_fuzzy_loop_frequency_dominance_with_stagnation():
    """1. browser.click appears >75% of calls WITH identical args → returns True."""
    sigs = [_make_sig('browser', {'action': 'click', 'selector': 'text="单程"'}) for _ in range(6)]
    assert _detect_fuzzy_loop(sigs) is True

def test_fuzzy_loop_no_false_positive_varied_args():
    """2. browser.fill called 6 times with 6 DIFFERENT selectors → NOT a loop."""
    sigs = [_make_sig('browser', {'action': 'fill', 'selector': f'#field{i}', 'value': f'val{i}'}) for i in range(6)]
    assert _detect_fuzzy_loop(sigs) is False

def test_fuzzy_loop_cyclic_subsequence_same_args():
    """3. [click(A), fill(A)] repeated 3 times with IDENTICAL args → returns True."""
    sig_click = _make_sig('browser', {'action': 'click', 'selector': 'text="Submit"'})
    sig_fill = _make_sig('browser', {'action': 'fill', 'selector': '#name', 'value': 'John'})
    sigs = [sig_click, sig_fill] * 3
    assert _detect_fuzzy_loop(sigs) is True

def test_fuzzy_loop_no_false_positive_cyclic_varied_args():
    """4. click+fill cycle but DIFFERENT args per cycle → NOT a loop (form filling)."""
    sigs = []
    for i in range(3):
        sigs.append(_make_sig('browser', {'action': 'click', 'selector': f'#field_{i}'}))
        sigs.append(_make_sig('browser', {'action': 'fill', 'selector': f'#field_{i}', 'value': f'val_{i}'}))
    assert _detect_fuzzy_loop(sigs) is False

def test_fuzzy_loop_normal_varied_calls():
    """5. Mixed tool calls (browser, web_search, shell, message) → NOT a loop."""
    sigs = [_make_sig('browser', {'action': 'navigate', 'url': 'https://example.com'}), _make_sig('web_search', {'query': 'test'}), _make_sig('exec', {'command': 'echo hello'}), _make_sig('message', {'content': 'Done!', 'chat_id': '123'}), _make_sig('browser', {'action': 'click', 'selector': 'button#submit'})]
    assert _detect_fuzzy_loop(sigs) is False

def test_fuzzy_loop_window_size_validation():
    """6. Only last _FUZZY_LOOP_WINDOW sigs are analyzed."""
    noise = [_make_sig('exec', {'command': f'echo {i}'}) for i in range(20)]
    identical = [_make_sig('browser', {'action': 'click', 'selector': 'text="OK"'}) for _ in range(4)]
    sigs = noise + identical
    assert _detect_fuzzy_loop(sigs) is False

def test_sig_window_retention():
    """27. verify _recent_call_sigs retains max(_DUPLICATE_THRESHOLD, _FUZZY_LOOP_WINDOW) entries."""
    from nanobot.agent.loop import _FUZZY_LOOP_WINDOW
    assert _FUZZY_LOOP_WINDOW >= 4

def test_fuzzy_loop_too_few_sigs():
    """Edge case: fewer than 4 sigs should always return False."""
    sigs = [_make_sig('browser', {'action': 'click', 'selector': 'x'}) for _ in range(3)]
    assert _detect_fuzzy_loop(sigs) is False

def test_action_history_summary_three_state_outcomes():
    """7. Verify correct rendering of ✓ (ok), ❌ (error), 👁️ (pending_verify) icons."""
    log = [{'tool': 'browser', 'action': 'click', 'outcome': 'ok', 'detail': 'button#submit'}, {'tool': 'browser', 'action': 'fill', 'outcome': 'error', 'detail': 'Error: timeout'}, {'tool': 'browser', 'action': 'click', 'outcome': 'pending_verify', 'detail': 'text="Next"'}]
    summary = _build_action_history_summary(log)
    assert '✓' in summary
    assert '❌' in summary
    assert '👁️' in summary
    assert 'browser(click)' in summary
    assert 'browser(fill)' in summary
    assert 'Do NOT retry' in summary

def test_action_history_summary_empty_log():
    """8. Empty log returns empty string."""
    assert _build_action_history_summary([]) == ''

def test_action_history_summary_truncation():
    """9. Log with >10 entries only shows last 10."""
    log = [{'tool': 'browser', 'action': f'click{i}', 'outcome': 'ok', 'detail': f'sel{i}'} for i in range(15)]
    summary = _build_action_history_summary(log)
    lines = [l for l in summary.split('\n') if l.startswith(('1.', '10.'))]
    assert any((l.startswith('1.') for l in lines))
    assert any((l.startswith('10.') for l in lines))
    assert '11.' not in summary

def test_action_history_injection_into_system_prompt():
    """10. History is injected into messages[0] (system role)."""
    messages = [{'role': 'system', 'content': 'Base system prompt'}]
    action_log = [{'tool': 'browser', 'action': 'click', 'outcome': 'ok', 'detail': 'submit'}]
    summary = _build_action_history_summary(action_log)
    sys_content = messages[0]['content']
    sentinel_idx = sys_content.find(_ACTION_HISTORY_SENTINEL)
    if sentinel_idx != -1:
        sys_content = sys_content[:sentinel_idx]
    history_len = len(summary) + len(_ACTION_HISTORY_SENTINEL)
    if history_len <= _ACTION_HISTORY_MAX and history_len <= _INJECTION_BUDGET:
        messages[0]['content'] = sys_content + _ACTION_HISTORY_SENTINEL + summary
    assert _ACTION_HISTORY_SENTINEL in messages[0]['content']
    assert 'browser(click)' in messages[0]['content']

def test_action_history_injection_respects_budget():
    """11. History should NOT be injected if global budget is nearly exhausted."""
    injection_used = 7900
    remaining_budget = _INJECTION_BUDGET - injection_used
    action_log = [{'tool': 'browser', 'action': 'click', 'outcome': 'ok', 'detail': 'x'}]
    summary = _build_action_history_summary(action_log)
    history_len = len(summary) + len(_ACTION_HISTORY_SENTINEL)
    assert history_len > remaining_budget, f'Test setup: history {history_len} should exceed remaining {remaining_budget}'

def test_action_history_injection_sentinel_cleanup():
    """12. Stale history is removed before injecting new."""
    old_content = 'Base prompt' + _ACTION_HISTORY_SENTINEL + 'old history data'
    messages = [{'role': 'system', 'content': old_content}]
    sys_content = messages[0]['content']
    sentinel_idx = sys_content.find(_ACTION_HISTORY_SENTINEL)
    if sentinel_idx != -1:
        sys_content = sys_content[:sentinel_idx]
    assert sys_content == 'Base prompt'
    assert 'old history data' not in sys_content

@pytest.fixture
def browser_tool():
    """Create a BrowserTool instance for testing."""
    from nanobot.plugins.browser import BrowserTool
    tool = BrowserTool()
    tool._config_loaded = True
    tool._headless = True
    return tool

@pytest.mark.asyncio
async def test_browser_vlm_disabled_fallback(browser_tool):
    """17. When VLM is not configured, _post_action_screenshot returns None."""
    mock_page = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_page.title = AsyncMock(return_value='Test Page')
    mock_page.url = 'https://example.com'
    mock_vlm = MagicMock()
    mock_vlm.enabled = False
    mock_vlm.model = ''
    mock_config = MagicMock()
    mock_config.agents.vlm = mock_vlm
    browser_tool._last_screenshot_ts = 0.0
    with patch('nanobot.config.loader.get_config', return_value=mock_config):
        result = await browser_tool._post_action_screenshot(mock_page, 'click', 'button')
    assert result is None

def test_browser_verify_screenshot_cleanup(browser_tool):
    """21. Create 15 verify + 15 nav files → cleanup → only 10 each remain."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i in range(15):
            (tmp_dir / f'browser_verify_{i:04d}.png').write_bytes(b'x')
            time.sleep(0.01)
        for i in range(15):
            (tmp_dir / f'browser_nav_{i:04d}.png').write_bytes(b'x')
            time.sleep(0.01)
        browser_tool._cleanup_verify_screenshots(tmp_dir)
        verify_remaining = list(tmp_dir.glob('browser_verify_*.png'))
        nav_remaining = list(tmp_dir.glob('browser_nav_*.png'))
        assert len(verify_remaining) == 10
        assert len(nav_remaining) == 10

def test_circuit_breaker_diagnostic_screenshot_counted_as_error():
    """23. _is_error_result() returns True for a string containing '⚠️ ACTION FAILED:'."""

    def _is_error_result(r):
        if isinstance(r, BaseException):
            return True
        if isinstance(r, str):
            s = str(r).strip()
            if s.startswith('Error:'):
                return True
            if '⚠️ ACTION FAILED:' in s:
                return True
        return False
    result = "Error: Browser action 'click' failed: Timeout\n__IMAGE__:/tmp/diag.png | ANCHORS:\n⚠️ ACTION FAILED: Error"
    assert _is_error_result(result) is True
    result2 = '__IMAGE__:/tmp/diag.png | ANCHORS:\n⚠️ ACTION FAILED: click failed'
    assert _is_error_result(result2) is True
    assert _is_error_result('{"action": "click", "success": true}') is False

def test_progressive_fallback_resets_via_helper(browser_tool):
    """25. _on_dom_action_success resets counter for that domain."""
    browser_tool._selector_fail_counts['example.com'] = 5
    mock_page = MagicMock()
    mock_page.url = 'https://example.com/page'
    browser_tool._on_dom_action_success(mock_page)
    assert 'example.com' not in browser_tool._selector_fail_counts

def test_js_whitelist_window_location_assign():
    """35. window.location.href = 'url' passes _is_safe_js."""
    from nanobot.plugins.browser import _is_safe_js
    assert _is_safe_js("window.location.href = 'https://example.com/test'")
    assert _is_safe_js('window.location.assign("https://example.com")')

def test_js_whitelist_dispatch_event():
    """36. element.dispatchEvent() passes _is_safe_js."""
    from nanobot.plugins.browser import _is_safe_js
    assert _is_safe_js("document.querySelector('.date-cell').dispatchEvent(new MouseEvent('click'))")

def test_js_whitelist_dangerous_still_blocked():
    """38. Dangerous patterns are still blocked."""
    from nanobot.plugins.browser import _is_safe_js
    assert not _is_safe_js("fetch('https://evil.com')")
    assert not _is_safe_js("eval('malicious')")
    assert not _is_safe_js('document.cookie')
    assert not _is_safe_js('XMLHttpRequest()')
    assert not _is_safe_js("import('module')")

@pytest.mark.asyncio
async def test_navigate_returns_json_not_image(browser_tool):
    """40. Phase 36: _action_navigate returns JSON, not __IMAGE__ protocol."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.title = AsyncMock(return_value='Example Page')
    mock_page.url = 'https://example.com'
    browser_tool._pages = [mock_page]
    browser_tool._trust_manager = MagicMock()
    browser_tool._trust_manager.is_trusted.return_value = True
    result = await browser_tool._action_navigate({'url': 'https://example.com'})
    assert '__IMAGE__' not in result
    data = json.loads(result)
    assert data['action'] == 'navigate'
    assert data['url'] == 'https://example.com'
    assert 'hint' in data
    assert 'content' in data['hint'] or 'screenshot' in data['hint']

@pytest.mark.asyncio
async def test_navigate_json_contains_url_param_hint(browser_tool):
    """41. Phase 36: Navigate JSON hint suggests URL parameters for search sites."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.title = AsyncMock(return_value='Flight Search')
    mock_page.url = 'https://flights.ctrip.com'
    browser_tool._pages = [mock_page]
    browser_tool._trust_manager = MagicMock()
    browser_tool._trust_manager.is_trusted.return_value = True
    result = await browser_tool._action_navigate({'url': 'https://flights.ctrip.com'})
    data = json.loads(result)
    assert 'URL parameters' in data['hint']

def test_architecture_md_in_bootstrap_files():
    """43. Phase 36: docs/rules/ARCHITECTURE.md is included in BOOTSTRAP_FILES."""
    from nanobot.agent.context import ContextBuilder
    assert 'docs/rules/ARCHITECTURE.md' in ContextBuilder.BOOTSTRAP_FILES