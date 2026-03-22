"""Tests for Dashboard API endpoints.

Uses FastAPI TestClient to exercise all REST endpoints without starting a real server.
Updated in Phase 18A to include Bearer token authentication.
"""
import json
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from nanobot.dashboard.app import app, init_dashboard, _active_websockets

TEST_TOKEN = "test-api-token-xyz"


@pytest.fixture(autouse=True)
def setup_dashboard(tmp_path):
    """Initialize dashboard with a temp workspace and known token for each test."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "memory").mkdir()
    init_dashboard(bus=None, workspace=workspace, token=TEST_TOKEN)
    yield workspace
    # Cleanup websockets list
    _active_websockets.clear()


@pytest.fixture
def client():
    return TestClient(app)


def auth():
    """Return auth headers for convenience."""
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


# ── Status ──────────────────────────────────────────────────────

def test_get_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


# ── Memory ──────────────────────────────────────────────────────

def test_get_memory_empty(client):
    resp = client.get("/api/memory", headers=auth())
    assert resp.status_code == 200
    assert resp.json()["content"] == ""


def test_post_and_get_memory(client, setup_dashboard):
    # Write
    resp = client.post("/api/memory", json={"content": "# My Memory\nHello"}, headers=auth())
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Read back
    resp = client.get("/api/memory", headers=auth())
    assert resp.status_code == 200
    assert "My Memory" in resp.json()["content"]


# ── Tasks ───────────────────────────────────────────────────────

def test_get_tasks_empty(client):
    resp = client.get("/api/tasks", headers=auth())
    assert resp.status_code == 200
    assert resp.json()["tasks"] == {}


def test_post_and_get_tasks(client, setup_dashboard):
    task_data = {
        "tasks": {
            "send_email": {
                "key": "send_email",
                "steps": [{"tool": "outlook", "args": {}}],
                "success_count": 3,
            }
        }
    }
    resp = client.post("/api/tasks", json=task_data, headers=auth())
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp = client.get("/api/tasks", headers=auth())
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert "send_email" in tasks
    assert tasks["send_email"]["success_count"] == 3


# ── Preferences ─────────────────────────────────────────────────

def test_get_preferences_empty(client):
    resp = client.get("/api/preferences", headers=auth())
    assert resp.status_code == 200
    assert resp.json()["preferences"] == {}


def test_get_preferences_with_data(client, setup_dashboard):
    prefs = {"language": "zh", "timezone": "Asia/Shanghai"}
    prefs_file = setup_dashboard / "memory" / "preferences.json"
    prefs_file.write_text(json.dumps(prefs), encoding="utf-8")

    resp = client.get("/api/preferences", headers=auth())
    assert resp.status_code == 200
    assert resp.json()["preferences"]["language"] == "zh"


# ── Stats ───────────────────────────────────────────────────────

def test_get_stats(client):
    resp = client.get("/api/stats", headers=auth())
    assert resp.status_code == 200
    data = resp.json()
    # Should have the metrics structure (timings, counters, tokens)
    assert "timings" in data
    assert "counters" in data
    assert "tokens" in data


# ── Index page ──────────────────────────────────────────────────

def test_index_returns_html(client, setup_dashboard):
    # Create a minimal template so the endpoint doesn't 500
    templates_dir = Path(__file__).parent.parent / "nanobot" / "dashboard" / "templates"
    index_file = templates_dir / "index.html"
    if not index_file.exists():
        pytest.skip("index.html template not present")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
