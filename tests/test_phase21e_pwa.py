"""Tests for Phase 21E Dashboard PWA capabilities."""

from fastapi.testclient import TestClient
from nanobot.dashboard.app import app

client = TestClient(app)

def test_manifest_endpoint():
    """Verify /manifest.json is served with correct content type."""
    response = client.get("/manifest.json")
    assert response.status_code == 200
    assert "application/manifest+json" in response.headers.get("content-type", "")
    data = response.json()
    assert data.get("name") == "Nanobot Command Center"
    assert "start_url" in data

def test_service_worker_endpoint():
    """Verify /sw.js is served with correct content type and available at root."""
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "")
    assert "self.addEventListener('fetch'" in response.text
