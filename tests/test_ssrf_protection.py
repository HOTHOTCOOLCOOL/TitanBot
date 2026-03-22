"""Tests for SSRF protection in WebFetchTool (S10)."""

import json
import pytest
from unittest.mock import patch

from nanobot.agent.tools.web import WebFetchTool, _is_internal_address


# ── Unit tests for _is_internal_address ──

class TestIsInternalAddress:
    """Test the internal address detection helper."""

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_loopback_ipv4(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 0))]
        assert _is_internal_address("localhost") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_loopback_127_x(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.2", 0))]
        assert _is_internal_address("some-loopback") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_rfc1918_10(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
        assert _is_internal_address("internal-host") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_rfc1918_172(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("172.16.0.1", 0))]
        assert _is_internal_address("internal-host") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_rfc1918_192(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("192.168.1.1", 0))]
        assert _is_internal_address("internal-host") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_link_local_metadata(self, mock_dns):
        """Cloud metadata endpoint (169.254.169.254) must be blocked."""
        mock_dns.return_value = [(2, 1, 6, "", ("169.254.169.254", 0))]
        assert _is_internal_address("metadata.internal") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_ipv6_loopback(self, mock_dns):
        mock_dns.return_value = [(10, 1, 6, "", ("::1", 0, 0, 0))]
        assert _is_internal_address("ipv6-loopback") is True

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_external_ip_allowed(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
        assert _is_internal_address("example.com") is False

    @patch("nanobot.agent.tools.web.socket.getaddrinfo")
    def test_dns_failure_returns_false(self, mock_dns):
        """If DNS lookup fails, treat as non-internal (fetch will fail later anyway)."""
        import socket
        mock_dns.side_effect = socket.gaierror("Name or service not known")
        assert _is_internal_address("nonexistent.invalid") is False


# ── Integration tests for WebFetchTool.execute() ──

class TestWebFetchSSRF:
    """Ensure WebFetchTool blocks SSRF attempts end-to-end.

    Phase 23A R4: SSRF check moved to transport layer (_SSRFSafeTransport).
    Tests now mock socket.getaddrinfo to return private IPs, which the
    transport intercepts at connect time.
    """

    @pytest.fixture
    def tool(self):
        return WebFetchTool()

    @pytest.mark.asyncio
    @patch("nanobot.agent.tools.web.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.1", 0))])
    async def test_fetch_blocked_internal(self, mock_dns, tool):
        result = json.loads(await tool.execute("http://10.0.0.1/admin"))
        assert "error" in result
        assert "ssrf" in result["error"].lower() or "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("nanobot.agent.tools.web.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))])
    async def test_fetch_blocked_localhost(self, mock_dns, tool):
        result = json.loads(await tool.execute("http://127.0.0.1:5507/api/stats"))
        assert "error" in result
        assert "ssrf" in result["error"].lower() or "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("nanobot.agent.tools.web.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))])
    async def test_fetch_blocked_metadata(self, mock_dns, tool):
        result = json.loads(await tool.execute("http://169.254.169.254/latest/meta-data/"))
        assert "error" in result
