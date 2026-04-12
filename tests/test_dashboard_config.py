import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the dashboard app
# Wait, we need to make sure the app can be imported properly
from nanobot.dashboard.app import app, _mask_sensitive_fields, _deep_merge, init_dashboard
from nanobot.config.loader import load_config, get_config_path

# ====================================================================
# Unit Tests for Config Helpers
# ====================================================================

def test_mask_sensitive_fields():
    data = {
        "providers": {
            "openai": {
                "api_key": "sk-12345",
                "api_base": "https://api.openai.com"
            },
            "slack": {
                "token": "xoxb-abc",
                "secret": "my-secret-123"
            }
        },
        "gateway": {
            "token": "admin-123"
        },
        "safe_field": "hello world"
    }
    
    masked = _mask_sensitive_fields(data)
    
    assert masked["providers"]["openai"]["api_key"] == "__MASKED__"
    assert masked["providers"]["openai"]["api_base"] == "https://api.openai.com"
    assert masked["providers"]["slack"]["token"] == "__MASKED__"
    assert masked["providers"]["slack"]["secret"] == "__MASKED__"
    assert masked["gateway"]["token"] == "__MASKED__"
    assert masked["safe_field"] == "hello world"


def test_deep_merge_skips_masked():
    original = {
        "providers": {
            "openai": {
                "api_key": "sk-12345",
                "api_base": "https://old.com"
            }
        },
        "safe_attr": "value1"
    }
    
    # Simulate a payload returned from the UI (where api_key is still masked, but api_base changed)
    updates = {
        "providers": {
            "openai": {
                "api_key": "__MASKED__",
                "api_base": "https://new.com"
            }
        },
        "safe_attr": "value2",
        "new_attr": "new_value"
    }
    
    merged = _deep_merge(original, updates)
    
    # The __MASKED__ value should be skipped, thus retaining the original secret.
    assert merged["providers"]["openai"]["api_key"] == "sk-12345"
    # But the other fields overwrite properly
    assert merged["providers"]["openai"]["api_base"] == "https://new.com"
    assert merged["safe_attr"] == "value2"
    assert merged["new_attr"] == "new_value"


# ====================================================================
# Integration Tests for Config API
# ====================================================================

@pytest.fixture
def client_with_auth():
    # Initialize dashboard with a known token and mock bus
    mock_bus = MagicMock()
    init_dashboard(bus=mock_bus, workspace=Path("/tmp/workspace"), token="test-token")
    return TestClient(app)


def test_optimistic_lock_rejects_stale(client_with_auth, tmp_path):
    # Setup mock config file
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"gateway": {"port": 8000}}))
    
    with patch("nanobot.config.loader.get_config_path", return_value=config_path):
        # Provide a stale hash
        stale_hash = "123456789.0"
        
        response = client_with_auth.post(
            "/api/config",
            headers={"Authorization": "Bearer test-token"},
            json={"config": {"gateway": {"port": 8080}}, "version_hash": stale_hash}
        )
        
        assert response.status_code == 409
        assert "Config modified on disk" in response.json()["detail"]


def test_post_config_success_creates_backup(client_with_auth, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"gateway": {"port": 8000}}))
    mtime = str(config_path.stat().st_mtime)
    
    with patch("nanobot.config.loader.get_config_path", return_value=config_path):
             
        response = client_with_auth.post(
            "/api/config",
            headers={"Authorization": "Bearer test-token"},
            json={"config": {"gateway": {"port": 9090}}, "version_hash": mtime}
        )
        
        assert response.status_code == 200
        
        # Check that the backup file was created by save_config_with_backup
        backup_path = config_path.with_suffix(".json.bak")
        assert backup_path.exists(), "Backup config file wasn't created"
        
        # Original should have had port 8000, new one has 9090
        backup_data = json.loads(backup_path.read_text())
        assert backup_data["gateway"]["port"] == 8000
        
        new_data = json.loads(config_path.read_text())
        assert new_data["gateway"]["port"] == 9090


def test_post_config_pydantic_validation(client_with_auth, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"gateway": {"port": 8000}}))
    mtime = str(config_path.stat().st_mtime)
    
    with patch("nanobot.config.loader.get_config_path", return_value=config_path):
        # We supply an invalid type for port (string 'invalid' instead of int)
        response = client_with_auth.post(
            "/api/config",
            headers={"Authorization": "Bearer test-token"},
            json={"config": {"gateway": {"port": "not-an-integer"}}, "version_hash": mtime}
        )
        
        # Should fail Pydantic validation and return 422
        assert response.status_code == 422
        assert "validation error" in response.json()["detail"].lower()
