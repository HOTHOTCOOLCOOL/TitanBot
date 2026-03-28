import pytest
from pathlib import Path
from nanobot.agent.hitl_store import ApprovalStore

def test_approval_store_basic(tmp_path):
    store = ApprovalStore(tmp_path)
    
    # Initially not approved
    assert not store.is_approved("exec", {"action": "", "command": "rm -rf /"})
    
    # Add an approval match
    store.add_approval("exec", "", {"command": "rm -rf /tmp/*"})
    
    # Test strict match
    assert not store.is_approved("exec", {"action": "", "command": "rm -rf /"})
    assert store.is_approved("exec", {"action": "", "command": "rm -rf /tmp/*"})

def test_approval_store_wildcard(tmp_path):
    store = ApprovalStore(tmp_path)
    store.add_approval("outlook", "send_email", {"to": "*@company.com"})
    
    # Match domain
    assert store.is_approved("outlook", {"action": "send_email", "to": "alice@company.com"})
    assert store.is_approved("outlook", {"action": "send_email", "to": "bob@company.com"})
    
    # Reject outside domain
    assert not store.is_approved("outlook", {"action": "send_email", "to": "eve@hacker.com"})
    
    # Reject wrong action
    assert not store.is_approved("outlook", {"action": "delete_email", "to": "alice@company.com"})

def test_approval_store_persistence(tmp_path):
    store1 = ApprovalStore(tmp_path)
    store1.add_approval("browser", "click", {"selector": "#submit"})
    
    store2 = ApprovalStore(tmp_path)
    assert store2.is_approved("browser", {"action": "click", "selector": "#submit"})
