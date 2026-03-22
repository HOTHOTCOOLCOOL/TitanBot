"""Tests for Dashboard Bearer Token authentication (Phase 18A).

Verifies that:
- Protected endpoints require valid Bearer token
- /api/status remains open (health check)
- WebSocket requires ?token= query parameter
"""
import pytest
from starlette.testclient import TestClient

from nanobot.dashboard.app import app, init_dashboard, _active_websockets, _dashboard_token
import nanobot.dashboard.app as dashboard_mod

TEST_TOKEN = "test-secret-token-abc123"


@pytest.fixture(autouse=True)
def setup_dashboard(tmp_path):
    """Initialize dashboard with a temp workspace and known token."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "memory").mkdir()
    init_dashboard(bus=None, workspace=workspace, token=TEST_TOKEN)
    yield workspace
    _active_websockets.clear()


@pytest.fixture
def client():
    return TestClient(app)


def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


# ── Unauthenticated requests should be rejected ────────────────

def test_get_memory_no_auth_returns_401(client):
    resp = client.get("/api/memory")
    assert resp.status_code == 401


def test_post_memory_no_auth_returns_401(client):
    resp = client.post("/api/memory", json={"content": "hack"})
    assert resp.status_code == 401


def test_get_tasks_no_auth_returns_401(client):
    resp = client.get("/api/tasks")
    assert resp.status_code == 401


def test_post_tasks_no_auth_returns_401(client):
    resp = client.post("/api/tasks", json={"tasks": {}})
    assert resp.status_code == 401


def test_get_preferences_no_auth_returns_401(client):
    resp = client.get("/api/preferences")
    assert resp.status_code == 401


def test_get_stats_no_auth_returns_401(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 401


# ── /api/status is always open as health check ──────────────────

def test_status_no_auth_returns_200(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


# ── Authenticated requests should succeed ───────────────────────

def test_get_memory_with_auth(client):
    resp = client.get("/api/memory", headers=auth_headers())
    assert resp.status_code == 200


def test_post_memory_with_auth(client):
    resp = client.post("/api/memory", json={"content": "ok"}, headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_get_tasks_with_auth(client):
    resp = client.get("/api/tasks", headers=auth_headers())
    assert resp.status_code == 200


def test_post_tasks_with_auth(client):
    resp = client.post("/api/tasks", json={"tasks": {"a": {}}}, headers=auth_headers())
    assert resp.status_code == 200


# ── Wrong token is rejected ─────────────────────────────────────

def test_wrong_token_returns_401(client):
    resp = client.get("/api/memory", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


# ── WebSocket auth ──────────────────────────────────────────────

def test_ws_without_token_is_rejected(client):
    """WebSocket without ?token= should be closed with 1008."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass  # Should not reach here


def test_ws_with_valid_token_connects(client):
    """WebSocket with valid ?token= should connect successfully."""
    with client.websocket_connect(f"/ws?token={TEST_TOKEN}") as ws:
        # Connection should be alive — we just verify no exception was raised
        pass
