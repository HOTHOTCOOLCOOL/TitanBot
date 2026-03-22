import pytest
from pathlib import Path
from nanobot.session.manager import SessionManager, Session

def test_identity_mapping(tmp_path: Path):
    """Test that SessionManager correctly resolves mapped identities."""
    workspace = tmp_path / "workspace"
    sm = SessionManager(workspace)
    
    # Set up master mapping
    master_id = "master:david"
    mapping = {
        "telegram:12345": master_id,
        "discord:67890": master_id,
        "feishu:abcde": master_id
    }
    sm.set_identity_mapping(mapping)
    
    # 1. Access via Telegram ID
    session_tg = sm.get_or_create("telegram:12345")
    assert session_tg.key == master_id, "Session key should be resolved to master identity"
    session_tg.add_message("user", "Hello from Telegram")
    sm.save(session_tg)
    
    # 2. Access via Discord ID
    # This should yield the exact same session object in memory/disk
    session_dc = sm.get_or_create("discord:67890")
    assert session_dc.key == master_id
    assert len(session_dc.messages) == 1
    assert session_dc.messages[0]["content"] == "Hello from Telegram"
    
    session_dc.add_message("user", "Hello from Discord")
    sm.save(session_dc)
    
    # 3. Access via Master ID directly
    session_master = sm.get_or_create(master_id)
    assert len(session_master.messages) == 2
    assert session_master.messages[1]["content"] == "Hello from Discord"

    # 4. Access via an unmapped ID
    session_other = sm.get_or_create("telegram:99999")
    assert session_other.key == "telegram:99999"
    assert len(session_other.messages) == 0

def test_identity_invalidation(tmp_path: Path):
    """Test that invalidating a raw key correctly translates to the master key."""
    workspace = tmp_path / "workspace"
    sm = SessionManager(workspace)
    
    master_id = "master:david"
    sm.set_identity_mapping({"telegram:12345": master_id})
    
    # Create and cache
    session = sm.get_or_create("telegram:12345")
    assert master_id in sm._cache
    
    # Invalidate using raw key
    sm.invalidate("telegram:12345")
    assert master_id not in sm._cache
