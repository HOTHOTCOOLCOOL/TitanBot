import pytest
from unittest.mock import patch, MagicMock
from nanobot.channels.base import BaseChannel
from nanobot.bus.queue import MessageBus

class DummyChannel(BaseChannel):
    name = "dummy"
    async def start(self): pass
    async def stop(self): pass
    async def send(self, msg): pass

@pytest.fixture(autouse=True)
def reset_master_identity_cache():
    """Reset class-level cache between tests."""
    BaseChannel._master_identities = None
    yield
    BaseChannel._master_identities = None

@patch("nanobot.channels.base.BaseChannel._load_master_identities", return_value={})
def test_auth_rejection(_mock):
    """Test that messages from non-whitelisted IDs are rejected securely."""
    bus = MessageBus()
    
    # 1. Empty allowlist -> public mode (True)
    config_empty = MagicMock(allow_from=[])
    chan = DummyChannel(config_empty, bus)
    assert chan.is_allowed("unknown_user") is True
    
    # 2. Strict allowlist -> reject unknown (False)
    config_strict = MagicMock(allow_from=["allowed_user"])
    chan = DummyChannel(config_strict, bus)
    assert chan.is_allowed("unknown_user") is False
    assert chan.is_allowed("allowed_user") is True

def test_auth_master_identity():
    """If the user is mapped to a master identity in the allow_from, allow them."""
    # S8: Use cached master_identities instead of load_config per call
    with patch.object(BaseChannel, "_load_master_identities", return_value={"dummy:user1": "master:boss"}):
        bus = MessageBus()
        config_master = MagicMock(allow_from=["master:boss"])
        chan_master = DummyChannel(config_master, bus)
        
        # user1 is mapped to master:boss, which is in allow_from
        assert chan_master.is_allowed("user1") is True
        
        # user2 is not mapped, and not in allow_from
        assert chan_master.is_allowed("user2") is False

