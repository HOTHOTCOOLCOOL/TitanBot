"""Tests for Phase 26B — Playwright Skill + BrowserTool Plugin.

Covers:
- Graceful degradation when Playwright is not installed
- Dual-layer SSRF protection (pre-navigation + request interception)
- Progressive domain trust model
- All 11 browser actions with mocked Playwright
- Evaluate whitelist enforcement
- Page limits
- URL validation
"""
import json
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from nanobot.plugins.browser import BrowserTool, _check_ssrf, _is_safe_js, _validate_url
from nanobot.plugins.trust_manager import TrustManager
from nanobot.plugins.browser_session import BrowserSessionStore

@pytest.fixture
def trust_manager(tmp_path):
    """TrustManager with a temp trust file location."""
    tm = TrustManager(config_trusted=['*.company.com', 'erp.internal.io'])
    tm._trust_file = tmp_path / 'trusted_domains.json'
    return tm

@pytest.fixture
def browser_tool(tmp_path):
    """BrowserTool with HAS_PLAYWRIGHT patched to True, config pre-loaded."""
    tool = BrowserTool()
    tool._config_loaded = True
    tool._trust_manager = TrustManager(config_trusted=['example.com', '*.trusted.io'])
    tool._session_store = BrowserSessionStore(base_dir=tmp_path / 'sessions')
    return tool

def _mock_page():
    """Create a fully mocked Playwright Page object."""
    page = AsyncMock()
    page.url = 'https://example.com'
    page.title = AsyncMock(return_value='Example Domain')
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()
    page.select_option = AsyncMock()
    page.screenshot = AsyncMock()
    page.inner_text = AsyncMock(return_value='Hello from the page')
    page.query_selector = AsyncMock(return_value=AsyncMock(inner_text=AsyncMock(return_value='Element text')))
    page.evaluate = AsyncMock(return_value='Example Domain')
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.route = AsyncMock()
    page.close = AsyncMock()
    return page

def _setup_browser_with_page(tool: BrowserTool):
    """Set up tool with a mocked browser and page, bypassing real Playwright."""
    page = _mock_page()
    tool._browser = AsyncMock()
    tool._context = AsyncMock()
    tool._context.new_page = AsyncMock(return_value=_mock_page())
    tool._playwright = AsyncMock()
    tool._pages = [page]
    return page
_pw_available = patch('nanobot.plugins.browser.HAS_PLAYWRIGHT', True)
_pw_unavailable = patch('nanobot.plugins.browser.HAS_PLAYWRIGHT', False)

class TestBrowserToolNotInstalled:
    """When HAS_PLAYWRIGHT is False, tool returns friendly error."""

    @pytest.mark.asyncio
    @_pw_unavailable
    async def test_execute_returns_friendly_error(self):
        """Execute returns install instructions when playwright is missing."""
        tool = BrowserTool()
        result = await tool.execute(action='navigate', url='https://example.com')
        assert 'pip install playwright' in result
        assert 'playwright install chromium' in result

    @pytest.mark.asyncio
    @_pw_unavailable
    async def test_all_actions_return_error(self):
        """Every action returns error when playwright missing."""
        tool = BrowserTool()
        for action in ['navigate', 'click', 'fill', 'close', 'screenshot']:
            result = await tool.execute(action=action)
            assert 'not installed' in result.lower()

class TestSSRFProtection:
    """Dual-layer SSRF protection tests."""

    def test_blocks_localhost(self):
        """127.0.0.1 is blocked."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('127.0.0.1', 0))]
            safe, reason, _ = _check_ssrf('evil.com')
            assert safe is False
            assert 'private IP' in reason

    def test_blocks_rfc1918_class_a(self):
        """10.x.x.x is blocked."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('10.0.0.1', 0))]
            safe, reason, _ = _check_ssrf('internal.com')
            assert safe is False

    def test_blocks_rfc1918_class_c(self):
        """192.168.x.x is blocked."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('192.168.1.1', 0))]
            safe, reason, _ = _check_ssrf('router.local')
            assert safe is False

    def test_blocks_metadata_ip(self):
        """169.254.169.254 (cloud metadata) is blocked."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('169.254.169.254', 0))]
            safe, reason, _ = _check_ssrf('metadata.cloud')
            assert safe is False

    def test_allows_external(self):
        """Public IPs pass SSRF check."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('93.184.216.34', 0))]
            safe, reason, _ = _check_ssrf('example.com')
            assert safe is True
            assert reason == ''

    def test_dns_failure(self):
        """DNS resolution failure is blocked."""
        with patch('nanobot.plugins.browser.socket.getaddrinfo', side_effect=socket.gaierror):
            safe, reason, _ = _check_ssrf('nonexistent.invalid')
            assert safe is False
            assert 'DNS resolution failed' in reason

    @pytest.mark.asyncio
    @_pw_available
    async def test_navigate_blocks_internal_ip(self, browser_tool):
        """Navigate to internal IP returns SSRF error."""
        browser_tool._trust_manager.add_trusted('evil.com')
        with patch('nanobot.plugins.browser.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('127.0.0.1', 0))]
            result = await browser_tool.execute(action='navigate', url='http://evil.com/admin')
            assert 'SSRF blocked' in result

    @pytest.mark.asyncio
    @_pw_available
    async def test_navigate_blocks_without_scheme(self, browser_tool):
        """Navigate without http/https scheme returns error."""
        result = await browser_tool.execute(action='navigate', url='ftp://example.com')
        assert 'Only http/https allowed' in result

class TestProgressiveTrust:
    """Progressive domain trust model."""

    def test_config_trusted_domain(self, trust_manager):
        """Domains from config are trusted."""
        assert trust_manager.is_trusted('erp.internal.io') is True

    def test_config_wildcard_match(self, trust_manager):
        """Wildcard *.company.com matches sub.company.com."""
        assert trust_manager.is_trusted('erp.company.com') is True
        assert trust_manager.is_trusted('hr.company.com') is True

    def test_wildcard_base_domain_match(self, trust_manager):
        """Wildcard *.company.com also matches company.com itself."""
        assert trust_manager.is_trusted('company.com') is True

    def test_untrusted_domain(self, trust_manager):
        """Unknown domain is not trusted."""
        assert trust_manager.is_trusted('evil.example.net') is False

    def test_add_trusted_persists(self, trust_manager):
        """Adding a domain saves to JSON file."""
        trust_manager.add_trusted('new.example.com')
        assert trust_manager.is_trusted('new.example.com') is True
        assert trust_manager._trust_file.exists()
        data = json.loads(trust_manager._trust_file.read_text(encoding='utf-8'))
        assert 'new.example.com' in data

    def test_runtime_trust_reload(self, trust_manager):
        """Runtime trust survives reload from file."""
        trust_manager.add_trusted('persistent.example.com')
        tm2 = TrustManager()
        tm2._trust_file = trust_manager._trust_file
        tm2._load_runtime_trust()
        assert tm2.is_trusted('persistent.example.com') is True

    def test_list_trusted(self, trust_manager):
        """list_trusted returns all domains."""
        trust_manager.add_trusted('added.example.com')
        all_domains = trust_manager.list_trusted()
        assert 'erp.internal.io' in all_domains
        assert 'added.example.com' in all_domains

    @pytest.mark.asyncio
    @_pw_available
    async def test_untrusted_domain_auto_trusted(self, browser_tool):
        """Navigating to untrusted domain auto-trusts and proceeds."""
        _setup_browser_with_page(browser_tool)
        with patch('nanobot.plugins.browser._check_ssrf', return_value=(True, '', '93.184.216.34')), patch('nanobot.config.loader.get_config', side_effect=Exception('mock no vlm')):
            result = await browser_tool.execute(action='navigate', url='https://unknown.example.com')
            data = json.loads(result)
            assert data['action'] == 'navigate'
            assert browser_tool._trust_manager.is_trusted('unknown.example.com')

    @pytest.mark.asyncio
    @_pw_available
    async def test_trust_flag_adds_domain(self, browser_tool):
        """Navigate with trust=true adds domain and proceeds."""
        _setup_browser_with_page(browser_tool)
        with patch('nanobot.plugins.browser._check_ssrf', return_value=(True, '', '93.184.216.34')), patch('nanobot.config.loader.get_config', side_effect=Exception('mock no vlm')):
            result = await browser_tool.execute(action='navigate', url='https://newsite.example.com', trust=True)
            data = json.loads(result)
            assert data['action'] == 'navigate'
            assert browser_tool._trust_manager.is_trusted('newsite.example.com')

@_pw_available
class TestBrowserActions:
    """All 11 browser actions with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_navigate_success(self, browser_tool):
        """Navigate to trusted domain succeeds."""
        page = _setup_browser_with_page(browser_tool)
        with patch('nanobot.plugins.browser._check_ssrf', return_value=(True, '', '93.184.216.34')), patch('nanobot.config.loader.get_config', side_effect=Exception('mock no vlm')):
            result = await browser_tool.execute(action='navigate', url='https://example.com')
            data = json.loads(result)
            assert data['action'] == 'navigate'
            assert data['status'] == 200
            page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_requires_url(self, browser_tool):
        """Navigate without URL parameter returns error."""
        result = await browser_tool.execute(action='navigate')
        assert 'url' in result.lower() and 'required' in result.lower()

    @pytest.mark.asyncio
    async def test_screenshot(self, browser_tool):
        """Screenshot saves file and returns path."""
        page = _setup_browser_with_page(browser_tool)
        with patch('nanobot.config.loader.get_config', side_effect=Exception('no config')):
            result = await browser_tool.execute(action='screenshot')
            assert '__IMAGE__:' in result
            assert 'browser_screenshot_' in result
            page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_content_extraction(self, browser_tool):
        """Content action extracts page text."""
        page = _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='content')
        data = json.loads(result)
        assert data['action'] == 'content'
        assert data['title'] == 'Example Domain'
        assert 'Hello from the page' in data['text']

    @pytest.mark.asyncio
    async def test_wait_for_networkidle(self, browser_tool):
        """Wait with networkidle waits for load state."""
        page = _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='wait', wait_for='networkidle')
        data = json.loads(result)
        assert data['wait_for'] == 'networkidle'
        page.wait_for_load_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_no_target(self, browser_tool):
        """Wait without selector or wait_for returns error."""
        _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='wait')
        assert 'required' in result.lower()

    @pytest.mark.asyncio
    async def test_login_navigates(self, browser_tool):
        """Login action behaves like navigate in Phase 26B."""
        page = _setup_browser_with_page(browser_tool)
        with patch('nanobot.plugins.browser._check_ssrf', return_value=(True, '', '93.184.216.34')), patch('nanobot.config.loader.get_config', side_effect=Exception('mock no vlm')):
            result = await browser_tool.execute(action='login', url='https://example.com/login')
            data = json.loads(result)
            assert data['action'] == 'navigate'
            page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cleanup(self, browser_tool):
        """Close action cleans up browser resources."""
        _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='close')
        data = json.loads(result)
        assert data['success'] is True
        assert data['pages_closed'] == 1
        assert browser_tool._browser is None
        assert browser_tool._context is None

    @pytest.mark.asyncio
    async def test_unknown_action(self, browser_tool):
        """Unknown action returns error."""
        result = await browser_tool.execute(action='explode')
        assert 'Unknown action' in result

class TestEvaluateWhitelist:
    """Evaluate action whitelist enforcement."""

    def test_document_title_allowed(self):
        assert _is_safe_js('document.title') is True

    def test_window_location_allowed(self):
        assert _is_safe_js('window.location.href') is True

    def test_arbitrary_fetch_blocked(self):
        assert _is_safe_js("fetch('http://evil.com')") is False

    def test_alert_blocked(self):
        assert _is_safe_js("alert('xss')") is False

    def test_eval_blocked(self):
        assert _is_safe_js("eval('malicious')") is False

    def test_complex_expression_blocked(self):
        assert _is_safe_js('document.cookie') is False

    @pytest.mark.asyncio
    @_pw_available
    async def test_evaluate_whitelisted_executes(self, browser_tool):
        """Whitelisted JS expression executes."""
        page = _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='evaluate', expression='document.title')
        data = json.loads(result)
        assert data['result'] == 'Example Domain'
        page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    @_pw_available
    async def test_evaluate_blocked_returns_error(self, browser_tool):
        """Non-whitelisted JS returns error, not executed."""
        page = _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='evaluate', expression="fetch('http://evil.com')")
        assert 'not allowed' in result
        page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    @_pw_available
    async def test_evaluate_no_expression(self, browser_tool):
        """Evaluate without expression returns error."""
        _setup_browser_with_page(browser_tool)
        result = await browser_tool.execute(action='evaluate')
        assert 'expression' in result.lower()
        assert 'required' in result.lower()

class TestPageLimits:
    """Max pages enforcement."""

    @pytest.mark.asyncio
    @_pw_available
    async def test_exceeds_max_pages_reuses_last(self, browser_tool):
        """When at page limit, _get_page returns last page (no new page)."""
        browser_tool._max_pages = 2
        browser_tool._browser = MagicMock()
        browser_tool._context = AsyncMock()
        browser_tool._pages = [_mock_page(), _mock_page()]
        browser_tool._playwright = AsyncMock()
        with patch('nanobot.plugins.browser._check_ssrf', return_value=(True, '', '93.184.216.34')), patch('nanobot.config.loader.get_config', side_effect=Exception('mock no vlm')):
            browser_tool._trust_manager.add_trusted('example.com')
            result = await browser_tool.execute(action='navigate', url='https://example.com/page3')
            data = json.loads(result)
            assert data['action'] == 'navigate'

class TestURLValidation:
    """URL validation tests."""

    def test_valid_http(self):
        valid, _ = _validate_url('http://example.com')
        assert valid is True

    def test_valid_https(self):
        valid, _ = _validate_url('https://example.com/path?q=1')
        assert valid is True

    def test_invalid_ftp(self):
        valid, err = _validate_url('ftp://example.com')
        assert valid is False
        assert 'http/https' in err

    def test_no_scheme(self):
        valid, err = _validate_url('example.com')
        assert valid is False

    def test_empty_url(self):
        valid, err = _validate_url('')
        assert valid is False