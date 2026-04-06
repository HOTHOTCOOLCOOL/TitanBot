import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from nanobot.agent.loop import AgentLoop, _normalize_tool_result, _MAX_TOOL_RESULT_CHARS
from nanobot.session.manager import SessionManager, Session
from nanobot.config.schema import AgentsConfig, ContextConfig
from nanobot.agent.memory_manager import MemoryManager

pytestmark = pytest.mark.asyncio

class TestPhase40AStability:

    @pytest.mark.asyncio
    async def test_tool_result_truncation(self):
        """P40A-1: Test tool result truncation"""
        # Test short string
        short_res = "short result"
        assert _normalize_tool_result(short_res, "test", 100) == short_res
        
        # Test exact length string
        exact_res = "a" * 100
        assert _normalize_tool_result(exact_res, "test", 100) == exact_res
        
        # Test long string
        long_res = "a" * 60 + "b" * 60
        trunc_res = _normalize_tool_result(long_res, "test", 100)
        assert len(trunc_res) > 100 # contains the injected truncation message
        assert trunc_res.startswith("a" * 50)
        assert trunc_res.endswith("b" * 50)
        assert "[TRUNCATED:" in trunc_res
        
        # Test exception
        exc = ValueError("Test error")
        assert _normalize_tool_result(exc, "test", 100) == "Error: Test error"
        
        # Test default constant usage
        very_long = "x" * (_MAX_TOOL_RESULT_CHARS + 1000)
        default_trunc = _normalize_tool_result(very_long, "test")
        assert len(default_trunc) < len(very_long)
        assert "[TRUNCATED:" in default_trunc


    @pytest.mark.asyncio
    async def test_session_concurrency_and_snapshot(self, tmp_path):
        """P40A-2: Test concurrency locks and snapshotting"""
        manager = SessionManager(tmp_path)
        
        # Test locking returns same lock
        lock1 = manager.get_session_lock("test:1")
        lock2 = manager.get_session_lock("test:1")
        assert lock1 is lock2
        assert isinstance(lock1, asyncio.Lock)
        
        # Test snapshot
        session = manager.get_or_create("test:snapshot")
        session.add_message("user", "msg1")
        session.evicted_context = "evicted text"
        
        snapshot = session.to_snapshot()
        assert snapshot["key"] == "test:snapshot"
        assert len(snapshot["messages"]) == 1
        assert snapshot["evicted_context"] == "evicted text"
        
        # Modify original, snapshot should be unaffected
        session.add_message("assistant", "msg2")
        session.evicted_context = "new text"
        
        assert len(snapshot["messages"]) == 1
        assert snapshot["evicted_context"] == "evicted text"

    @pytest.mark.asyncio
    async def test_token_budget_snip(self, tmp_path):
        """P40A-3: Test token-budget clipping logic"""
        loop = AgentLoop(bus=Mock(), provider=Mock(), workspace=tmp_path)
        # mock max_tokens so context_window infers appropriately
        loop.max_tokens = 4096
        
        # Construct large message history
        # Let's say each message has 10 chars -> ~2.5 tokens
        # We need enough to trigger snip
        messages = [
            {"role": "system", "content": "You are AI."},
        ]
        
        for i in range(100):
            messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i} {'x' * 100}"})
            
        # Create a small window so it has to clip
        # budget = 2000 - 4096 (but wait, budget formula is: context_window - max_tokens - _INJECTION_BUDGET(8000) - 1024
        # Wait, if context_window is low it might be <=0
        small_window = 4096 + 8000 + 1024 + 500  # Budget = 500 tokens
        
        with patch("litellm.token_counter", return_value=50): # suppose each msg is 50 tokens
            snipped = loop._snip_history(list(messages), context_window=small_window)
            
            # budget is 500, system is 50
            # remains 450, which allows up to 9 messages
            # Wait, exact count depends on the logic, let's just make sure it's smaller
            assert len(snipped) < len(messages)
            
            # Verify system msg is kept
            assert snipped[0]["role"] == "system"
            
            # Verify it starts with a 'user' msg after system
            assert snipped[1]["role"] == "user"
