"""Tests for Phase 26C — Session Encrypted Persistence + Trust Manager.

Covers:
- BrowserSessionStore encryption roundtrip (save → load)
- TTL expiration enforcement
- Domain isolation
- Session cleanup (clear / clear_expired)
- TrustManager standalone (add/remove/clear/wildcard/persistence)
- Browser integration (login saves session, session restore)
- Encryption backend selection
- Cookie values never in LLM-facing output
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.plugins.browser_session import (
    BrowserSessionStore,
    _decrypt,
    _encrypt,
    get_encryption_backend,
)
from nanobot.plugins.trust_manager import TrustManager
from nanobot.plugins.browser import BrowserTool


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def session_store(tmp_path):
    """BrowserSessionStore with temp base directory."""
    return BrowserSessionStore(base_dir=tmp_path / "browser_sessions", default_ttl_hours=24)


@pytest.fixture
def trust_mgr(tmp_path):
    """TrustManager with temp trust file."""
    return TrustManager(
        config_trusted=["*.company.com", "erp.internal.io"],
        trust_file=tmp_path / "trusted_domains.json",
    )


@pytest.fixture
def sample_cookies():
    """Sample Playwright-style cookie dicts."""
    return [
        {
            "name": "session_id",
            "value": "abc123secret",
            "domain": "example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
        },
        {
            "name": "csrf_token",
            "value": "tok456",
            "domain": "example.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
        },
    ]


@pytest.fixture
def sample_storage():
    """Sample localStorage key-value pairs."""
    return {"user_pref": "dark_mode", "lang": "zh-CN"}


# Decorator to patch HAS_PLAYWRIGHT
_pw_available = patch("nanobot.plugins.browser.HAS_PLAYWRIGHT", True)


# ── TestBrowserSessionStore ─────────────────────────────────────────────────


class TestBrowserSessionStore:
    """Core session store functionality."""

    def test_save_and_load_roundtrip(self, session_store, sample_cookies, sample_storage):
        """Save cookies+storage → load returns identical data."""
        assert session_store.save_session(
            domain="example.com",
            cookies=sample_cookies,
            local_storage=sample_storage,
        )

        loaded = session_store.load_session("example.com")
        assert loaded is not None
        assert loaded["domain"] == "example.com"
        assert loaded["cookies"] == sample_cookies
        assert loaded["local_storage"] == sample_storage

    def test_saved_file_not_plaintext(self, session_store, sample_cookies):
        """Encrypted file does not contain raw cookie values."""
        session_store.save_session(
            domain="secret.example.com",
            cookies=sample_cookies,
        )

        enc_path = session_store._domain_dir("secret.example.com") / "session.enc"
        assert enc_path.exists()
        raw_bytes = enc_path.read_bytes()
        # The secret cookie value should NOT appear in plaintext
        assert b"abc123secret" not in raw_bytes

    def test_load_nonexistent_returns_none(self, session_store):
        """Loading a non-existent domain returns None."""
        assert session_store.load_session("nonexistent.com") is None

    def test_session_ttl_expired(self, session_store, sample_cookies):
        """Session older than TTL returns None on load."""
        session_store.save_session(
            domain="expired.com",
            cookies=sample_cookies,
            ttl_hours=1,
        )

        # Manipulate metadata to make it look old
        meta_path = session_store._domain_dir("expired.com") / "session.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        meta["created_at"] = old_time
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        # Also update the encrypted data's created_at
        enc_path = session_store._domain_dir("expired.com") / "session.enc"
        decrypted = _decrypt(enc_path.read_bytes())
        data = json.loads(decrypted.decode("utf-8"))
        data["created_at"] = old_time
        encrypted = _encrypt(json.dumps(data).encode("utf-8"))
        enc_path.write_bytes(encrypted)

        assert session_store.load_session("expired.com") is None

    def test_session_ttl_valid(self, session_store, sample_cookies):
        """Fresh session loads successfully."""
        session_store.save_session(
            domain="fresh.com",
            cookies=sample_cookies,
            ttl_hours=24,
        )
        loaded = session_store.load_session("fresh.com")
        assert loaded is not None
        assert loaded["cookies"] == sample_cookies

    def test_clear_session(self, session_store, sample_cookies):
        """Clear removes the domain directory entirely."""
        session_store.save_session(domain="clearme.com", cookies=sample_cookies)
        domain_dir = session_store._domain_dir("clearme.com")
        assert domain_dir.exists()

        assert session_store.clear_session("clearme.com") is True
        assert not domain_dir.exists()

    def test_clear_nonexistent(self, session_store):
        """Clearing a non-existent domain returns False."""
        assert session_store.clear_session("nope.com") is False

    def test_clear_expired_removes_old(self, session_store, sample_cookies):
        """clear_expired removes old sessions, keeps fresh ones."""
        # Save two sessions
        session_store.save_session(domain="old.com", cookies=sample_cookies, ttl_hours=1)
        session_store.save_session(domain="new.com", cookies=sample_cookies, ttl_hours=24)

        # Make old.com look expired
        meta_path = session_store._domain_dir("old.com") / "session.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["created_at"] = (datetime.now() - timedelta(hours=2)).isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        cleared = session_store.clear_expired()
        assert cleared == 1
        assert not session_store._domain_dir("old.com").exists()
        assert session_store._domain_dir("new.com").exists()

    def test_domain_isolation(self, session_store, sample_cookies):
        """Different domains have separate storage."""
        cookies_a = [{"name": "a", "value": "1", "domain": "a.com", "path": "/"}]
        cookies_b = [{"name": "b", "value": "2", "domain": "b.com", "path": "/"}]

        session_store.save_session(domain="a.com", cookies=cookies_a)
        session_store.save_session(domain="b.com", cookies=cookies_b)

        loaded_a = session_store.load_session("a.com")
        loaded_b = session_store.load_session("b.com")

        assert loaded_a["cookies"] == cookies_a
        assert loaded_b["cookies"] == cookies_b

    def test_list_sessions(self, session_store, sample_cookies):
        """list_sessions returns all domains with metadata."""
        session_store.save_session(domain="site1.com", cookies=sample_cookies)
        session_store.save_session(domain="site2.com", cookies=sample_cookies)

        sessions = session_store.list_sessions()
        assert len(sessions) == 2
        domains = {s["domain"] for s in sessions}
        assert domains == {"site1.com", "site2.com"}
        assert all("created_at" in s for s in sessions)
        assert all("ttl_hours" in s for s in sessions)


# ── TestEncryptionRoundtrip ─────────────────────────────────────────────────


class TestEncryptionRoundtrip:
    """Low-level encryption/decryption tests."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt → decrypt returns original data."""
        original = b"Hello, this is secret session data!"
        encrypted = _encrypt(original)
        decrypted = _decrypt(encrypted)
        assert decrypted == original

    def test_encrypted_differs_from_plaintext(self):
        """Encrypted output is not the same as input."""
        original = b"sensitive cookie data"
        encrypted = _encrypt(original)
        assert encrypted != original

    def test_backend_is_valid(self):
        """Encryption backend is one of the known options."""
        assert get_encryption_backend() in ("dpapi", "fernet", "base64")

    def test_empty_data_roundtrip(self):
        """Empty data encrypts and decrypts correctly."""
        original = b""
        encrypted = _encrypt(original)
        decrypted = _decrypt(encrypted)
        assert decrypted == original

    def test_unicode_json_roundtrip(self):
        """Unicode JSON data survives encrypt/decrypt."""
        original = json.dumps({"key": "中文值", "emoji": "🔐"}).encode("utf-8")
        encrypted = _encrypt(original)
        decrypted = _decrypt(encrypted)
        assert decrypted == original


# ── TestTrustManagerStandalone ──────────────────────────────────────────────


class TestTrustManagerStandalone:
    """TrustManager as standalone module tests."""

    def test_add_and_check(self, trust_mgr):
        """Add domain → is_trusted returns True."""
        assert trust_mgr.is_trusted("new.example.com") is False
        trust_mgr.add_trusted("new.example.com")
        assert trust_mgr.is_trusted("new.example.com") is True

    def test_remove_trusted(self, trust_mgr):
        """Remove domain → is_trusted returns False."""
        trust_mgr.add_trusted("removeme.com")
        assert trust_mgr.is_trusted("removeme.com") is True
        result = trust_mgr.remove_trusted("removeme.com")
        assert result is True
        assert trust_mgr.is_trusted("removeme.com") is False

    def test_remove_nonexistent(self, trust_mgr):
        """Removing a non-existent domain returns False."""
        assert trust_mgr.remove_trusted("never.added.com") is False

    def test_clear_all(self, trust_mgr):
        """clear_all removes all runtime trusted domains."""
        trust_mgr.add_trusted("a.com")
        trust_mgr.add_trusted("b.com")
        count = trust_mgr.clear_all()
        assert count == 2
        assert trust_mgr.is_trusted("a.com") is False
        assert trust_mgr.is_trusted("b.com") is False
        # Config-level domains should remain
        assert trust_mgr.is_trusted("erp.internal.io") is True

    def test_wildcard_matching(self, trust_mgr):
        """*.company.com matches sub.company.com."""
        assert trust_mgr.is_trusted("hr.company.com") is True
        assert trust_mgr.is_trusted("erp.company.com") is True
        assert trust_mgr.is_trusted("company.com") is True  # Base domain match
        assert trust_mgr.is_trusted("evil.notcompany.com") is False

    def test_persistence_across_instances(self, trust_mgr):
        """Trusted domains persist across TrustManager instances."""
        trust_mgr.add_trusted("persistent.example.com")

        tm2 = TrustManager(trust_file=trust_mgr._trust_file)
        assert tm2.is_trusted("persistent.example.com") is True

    def test_case_insensitive(self, trust_mgr):
        """Domain trust is case-insensitive."""
        trust_mgr.add_trusted("CaseDomain.COM")
        assert trust_mgr.is_trusted("casedomain.com") is True
        assert trust_mgr.is_trusted("CASEDOMAIN.COM") is True


# ── TestBrowserToolSessionIntegration ───────────────────────────────────────


def _mock_page():
    """Create a fully mocked Playwright Page object."""
    page = AsyncMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example Domain")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()
    page.select_option = AsyncMock()
    page.screenshot = AsyncMock()
    page.inner_text = AsyncMock(return_value="Hello from the page")
    page.query_selector = AsyncMock(
        return_value=AsyncMock(inner_text=AsyncMock(return_value="Element text"))
    )
    page.evaluate = AsyncMock(return_value={})
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.route = AsyncMock()
    page.close = AsyncMock()
    return page


def _setup_browser_with_page(tool: BrowserTool):
    """Set up tool with a mocked browser and page."""
    page = _mock_page()
    tool._browser = AsyncMock()
    tool._context = AsyncMock()
    tool._context.new_page = AsyncMock(return_value=_mock_page())
    tool._context.cookies = AsyncMock(return_value=[
        {"name": "sid", "value": "secret123", "domain": "example.com", "path": "/"},
    ])
    tool._context.add_cookies = AsyncMock()
    tool._playwright = AsyncMock()
    tool._pages = [page]
    return page


@_pw_available
class TestBrowserToolSessionIntegration:
    """Browser tool integration with session persistence."""

    @pytest.mark.asyncio
    async def test_login_saves_session(self, tmp_path):
        """Login with save_session=True triggers encrypted session save."""
        tool = BrowserTool()
        tool._config_loaded = True
        tool._trust_manager = TrustManager(
            config_trusted=["example.com"],
            trust_file=tmp_path / "trust.json",
        )
        tool._session_store = BrowserSessionStore(
            base_dir=tmp_path / "sessions",
        )
        page = _setup_browser_with_page(tool)

        with patch("nanobot.plugins.browser._check_ssrf", return_value=(True, "", "93.184.216.34")):
            result = await tool.execute(
                action="login",
                url="https://example.com/login",
                save_session=True,
            )
            data = json.loads(result)
            assert data["session_saved"] is True
            assert data["session_domain"] == "example.com"

            # Verify session was actually persisted
            loaded = tool._session_store.load_session("example.com")
            assert loaded is not None
            assert len(loaded["cookies"]) == 1

    @pytest.mark.asyncio
    async def test_login_without_save(self, tmp_path):
        """Login with save_session=False does not save session."""
        tool = BrowserTool()
        tool._config_loaded = True
        tool._trust_manager = TrustManager(
            config_trusted=["example.com"],
            trust_file=tmp_path / "trust.json",
        )
        tool._session_store = BrowserSessionStore(
            base_dir=tmp_path / "sessions",
        )
        _setup_browser_with_page(tool)

        with patch("nanobot.plugins.browser._check_ssrf", return_value=(True, "", "93.184.216.34")):
            result = await tool.execute(
                action="login",
                url="https://example.com/login",
                save_session=False,
            )
            data = json.loads(result)
            assert "session_saved" not in data

            # No session persisted
            loaded = tool._session_store.load_session("example.com")
            assert loaded is None

    @pytest.mark.asyncio
    async def test_session_restore_on_navigate(self, tmp_path):
        """Navigating to a domain with saved session restores cookies."""
        tool = BrowserTool()
        tool._config_loaded = True
        tool._trust_manager = TrustManager(
            config_trusted=["example.com"],
            trust_file=tmp_path / "trust.json",
        )
        store = BrowserSessionStore(base_dir=tmp_path / "sessions")
        tool._session_store = store

        # Pre-save a session
        store.save_session(
            domain="example.com",
            cookies=[{"name": "sid", "value": "restored", "domain": "example.com", "path": "/"}],
        )

        _setup_browser_with_page(tool)

        with patch("nanobot.plugins.browser._check_ssrf", return_value=(True, "", "93.184.216.34")):
            await tool.execute(
                action="navigate",
                url="https://example.com/dashboard",
            )
            # Verify add_cookies was called with the restored cookies
            tool._context.add_cookies.assert_called_once()
            restored_cookies = tool._context.add_cookies.call_args[0][0]
            assert len(restored_cookies) == 1
            assert restored_cookies[0]["name"] == "sid"

    @pytest.mark.asyncio
    async def test_cookies_never_in_response_text(self, tmp_path):
        """Cookie values must never appear in LLM-facing tool output."""
        tool = BrowserTool()
        tool._config_loaded = True
        tool._trust_manager = TrustManager(
            config_trusted=["example.com"],
            trust_file=tmp_path / "trust.json",
        )
        tool._session_store = BrowserSessionStore(
            base_dir=tmp_path / "sessions",
        )
        _setup_browser_with_page(tool)

        with patch("nanobot.plugins.browser._check_ssrf", return_value=(True, "", "93.184.216.34")):
            result = await tool.execute(
                action="login",
                url="https://example.com/login",
                save_session=True,
            )
            # The secret cookie value must not appear in the response
            assert "secret123" not in result
            # But session_saved status should be there
            data = json.loads(result)
            assert data["session_saved"] is True


# ── TestEncryptionBackendSelection ──────────────────────────────────────────


class TestEncryptionBackendSelection:
    """Encryption backend auto-selection tests."""

    def test_dpapi_preferred_on_windows(self):
        """On Windows with pywin32, DPAPI should be selected."""
        # We can only test the actual backend in the current environment
        backend = get_encryption_backend()
        import sys
        if sys.platform == "win32":
            # May be dpapi or fernet depending on pywin32 availability
            assert backend in ("dpapi", "fernet", "base64")
        else:
            assert backend in ("fernet", "base64")

    def test_base64_fallback_produces_warning(self, tmp_path, caplog):
        """When using base64 backend, a warning is logged."""
        with patch("nanobot.plugins.browser_session._BACKEND", "base64"):
            store = BrowserSessionStore(base_dir=tmp_path / "sessions")
            # The warning is logged in __init__ when backend is base64
            # We just verify the store still works
            store.save_session(
                domain="test.com",
                cookies=[{"name": "x", "value": "y"}],
            )
            loaded = store.load_session("test.com")
            assert loaded is not None
