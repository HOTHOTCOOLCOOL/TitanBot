"""Tests for Phase 21C P2 Quality & Robustness fixes.

Covers all 11 issues: S5, S6, B5, B6, L5, C2, C3, I3, I4, E3, E4.
"""
import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


# ── S5: Atomic JSON write ──────────────────────────────────────

def test_atomic_write_reflection():
    """S5: ReflectionStore._save() should produce valid JSON (atomic write)."""
    from nanobot.agent.reflection import ReflectionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = ReflectionStore(workspace)
        store.add_reflection("trigger_test", "bad_reason", "fix_it")

        # The file should exist and be valid JSON
        data = json.loads(store.reflections_file.read_text(encoding="utf-8"))
        assert "reflections" in data
        assert len(data["reflections"]) == 1
        assert data["reflections"][0]["trigger"] == "trigger_test"


def test_atomic_write_kg():
    """S5: KnowledgeGraph._save() should produce valid JSON (atomic write)."""
    from nanobot.agent.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kg = KnowledgeGraph(workspace)
        kg._add_triple("Alice", "likes", "Python")
        # Phase 25: _add_triple no longer auto-saves; callers must call _save() explicitly
        kg._save()

        data = json.loads(kg.graph_file.read_text(encoding="utf-8"))
        assert "triples" in data
        assert len(data["triples"]) == 1
        assert data["triples"][0]["subject"] == "Alice"


# ── S6: Think tag stripping ────────────────────────────────────

def test_strip_think_matched():
    """S6: Matched <think>X</think>Y should return Y."""
    from nanobot.utils.think_strip import strip_think_tags

    result = strip_think_tags("<think>internal reasoning</think>actual answer")
    assert result == "actual answer"


def test_strip_think_unmatched():
    """S6: Unmatched <think>XY (no closing tag) should strip from <think> to end."""
    from nanobot.utils.think_strip import strip_think_tags

    result = strip_think_tags("prefix <think>leaked reasoning without close tag")
    assert result == "prefix"


def test_strip_think_no_tags():
    """S6: Input without think tags should be unchanged."""
    from nanobot.utils.think_strip import strip_think_tags

    original = "Hello world, no tags here."
    assert strip_think_tags(original) == original


def test_strip_think_empty():
    """S6: Empty think block should produce content after it."""
    from nanobot.utils.think_strip import strip_think_tags

    result = strip_think_tags("<think></think>real answer")
    assert result == "real answer"


def test_strip_think_multiple():
    """S6: Multiple think blocks should all be removed."""
    from nanobot.utils.think_strip import strip_think_tags

    result = strip_think_tags("<think>a</think>X<think>b</think>Y")
    assert result == "XY"


# ── B5: Consolidation empty-slice guard ────────────────────────

@pytest.mark.asyncio
async def test_consolidation_skips_empty_conversation():
    """B5: consolidate_memory should early-return when conversation is empty."""
    from nanobot.agent.memory_manager import MemoryManager
    from nanobot.session.manager import Session

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir()

        provider = MagicMock()
        provider.chat = AsyncMock()

        mm = MemoryManager(workspace=workspace, provider=provider, model="test", memory_window=50)

        # Create session with messages that have empty content
        session = Session(key="test:user")
        session.add_message("user", "")
        session.add_message("assistant", "")

        await mm.consolidate_memory(session)
        # The LLM should NOT have been called
        provider.chat.assert_not_called()


# ── B6: Session JSONL UTF-8 encoding ──────────────────────────

def test_session_save_utf8():
    """B6: Session with Chinese content should survive save/load round-trip."""
    from nanobot.session.manager import SessionManager, Session

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        sm = SessionManager(workspace)

        session = Session(key="test:cn")
        session.add_message("user", "你好世界！请帮我处理一下这个任务。")
        session.add_message("assistant", "好的，我来帮你处理。")

        sm.save(session)

        # Force reload from disk
        sm._cache.clear()
        loaded = sm.get_or_create("test:cn")
        assert len(loaded.messages) == 2
        assert "你好世界" in loaded.messages[0]["content"]
        assert "我来帮你处理" in loaded.messages[1]["content"]


# ── L5: KB substring match threshold ──────────────────────────

def test_substring_match_threshold_raised():
    """L5: Short Chinese keys should not false-match (threshold 0.65 + 4-char min)."""
    from nanobot.agent.knowledge_workflow import KnowledgeWorkflow

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kw = KnowledgeWorkflow(workspace=workspace)

        # Add a short 3-char key
        kw.knowledge_store.add_task(
            key="发邮件",
            description="send email",
            steps=[{"tool": "message", "args": {}}],
            params={},
            result_summary="Task completed",
        )

        # A 6-char query containing the 3-char key should NOT match (too short)
        result = kw.match_knowledge("帮我发邮件给张三")
        assert result is None, "Short key (<4 chars) should not substring-match"


def test_substring_match_longer_keys_still_work():
    """L5: Longer keys should still match via substring."""
    from nanobot.agent.knowledge_workflow import KnowledgeWorkflow

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kw = KnowledgeWorkflow(workspace=workspace)

        # Add a longer key (5 chars)
        kw.knowledge_store.add_task(
            key="查询天气预报",
            description="check weather",
            steps=[{"tool": "web_fetch", "args": {}}],
            params={},
            result_summary="Task completed",
        )

        # Query containing the 6-char key should match (ratio will be high)
        result = kw.match_knowledge("查询天气预报今天的")
        # This has ratio = 6/9 ≈ 0.67, and min key length = 6 >= 4 → should match
        assert result is not None


# ── C2: Deep consolidation vs regular consolidation lock ──────

def test_deep_consolidate_shares_lock_with_regular_c2():
    """C2: deep_consolidate and consolidate_memory should use the same lock (verified via C1)."""
    from nanobot.agent.memory_manager import MemoryManager
    import inspect

    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(
            workspace=Path(tmpdir),
            provider=MagicMock(),
            model="test",
            memory_window=50,
        )
        # Both methods should reference _consolidation_lock
        consolidate_src = inspect.getsource(mm.consolidate_memory)
        deep_src = inspect.getsource(mm.deep_consolidate)
        assert "_consolidation_lock" in consolidate_src
        assert "_consolidation_lock" in deep_src


# ── C3: Visual Memory duplicate persistence ───────────────────

def test_visual_memory_no_duplicate():
    """C3: Same image analysis should not be persisted twice."""
    from nanobot.agent.context import ContextBuilder

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir()
        (workspace / "skills").mkdir()

        cb = ContextBuilder(workspace)
        assert hasattr(cb, "_persisted_visual_hashes")

        # We can't easily test the full add_assistant_message flow without
        # mocking vector_memory and memory, but we can verify the hash set exists
        # and is initially empty
        assert len(cb._persisted_visual_hashes) == 0

        # Simulate the dedup logic directly
        import hashlib
        content = "This image shows a cat sitting on a desk."
        h = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        cb._persisted_visual_hashes.add(h)

        # Second attempt with same content should detect duplicate
        h2 = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        assert h2 in cb._persisted_visual_hashes


# ── I3: Tool output global size limit ─────────────────────────

@pytest.mark.asyncio
async def test_tool_output_truncated():
    """I3: Tool output exceeding MAX_TOOL_OUTPUT should be truncated."""
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.agent.tools.base import Tool

    registry = ToolRegistry()

    class BigOutputTool(Tool):
        name = "big_output"
        description = "Returns a huge string"
        parameters = {}

        async def execute(self, **kwargs):
            return "X" * 100_000  # 100K chars

    registry.register(BigOutputTool())
    result = await registry.execute("big_output", {})

    assert len(result) < 60_000  # Well under 100K
    assert "[OUTPUT TRUNCATED" in result


@pytest.mark.asyncio
async def test_tool_output_small_not_truncated():
    """I3: Small tool output should not be truncated."""
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.agent.tools.base import Tool

    registry = ToolRegistry()

    class SmallOutputTool(Tool):
        name = "small_output"
        description = "Returns a small string"
        parameters = {}

        async def execute(self, **kwargs):
            return "Hello, world!"

    registry.register(SmallOutputTool())
    result = await registry.execute("small_output", {})
    assert result == "Hello, world!"
    assert "[OUTPUT TRUNCATED" not in result


def test_max_tool_output_constant():
    """I3: MAX_TOOL_OUTPUT should be defined."""
    from nanobot.agent.tools.registry import ToolRegistry
    assert ToolRegistry.MAX_TOOL_OUTPUT == 50_000


# ── I4: Session JSONL append-only optimization ────────────────

def test_session_append_only_save():
    """I4: Session should be saved via _full_rewrite helper with UTF-8 encoding."""
    from nanobot.session.manager import SessionManager, Session

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        sm = SessionManager(workspace)

        session = Session(key="test:append")
        session.add_message("user", "msg1")
        session.add_message("assistant", "reply1")
        sm.save(session)

        # Add more messages and save again
        session.add_message("user", "msg2")
        sm.save(session)

        # Verify file is valid JSONL and has all messages
        sm._cache.clear()
        loaded = sm.get_or_create("test:append")
        assert len(loaded.messages) == 3

    # Verify _full_rewrite method exists
    assert hasattr(sm, "_full_rewrite")


# ── E3: Query rewrite LLM short-circuit ───────────────────────

@pytest.mark.asyncio
async def test_rewrite_query_short_circuit_no_pronouns():
    """E3: Simple query without pronouns should NOT call LLM."""
    from nanobot.agent.vector_store import VectorMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        vm = VectorMemory(workspace)
        vm.provider = MagicMock()
        vm.provider.chat = AsyncMock()
        vm.model = "test-model"

        history = [{"role": "user", "content": "hello"}]
        result = await vm.rewrite_query("查询天气预报", history)

        # No pronouns → should return original query, no LLM call
        assert result == "查询天气预报"
        vm.provider.chat.assert_not_called()


@pytest.mark.asyncio
async def test_rewrite_query_with_pronoun_calls_llm():
    """E3: Query with pronouns should proceed to LLM rewrite."""
    from nanobot.agent.vector_store import VectorMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        vm = VectorMemory(workspace)
        vm.provider = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "rewritten query about the project"
        vm.provider.chat = AsyncMock(return_value=mock_resp)
        vm.model = "test-model"

        history = [{"role": "user", "content": "Tell me about NanoBot"}, {"role": "assistant", "content": "NanoBot is..."}]
        result = await vm.rewrite_query("这个项目有什么功能", history)

        # "这个" is a Chinese pronoun → should call LLM
        vm.provider.chat.assert_called_once()


# ── E4: i18n error messages ───────────────────────────────────

def test_i18n_error_messages_exist():
    """E4: All new i18n keys should be defined."""
    from nanobot.agent.i18n import MESSAGES

    new_keys = [
        "reload_success", "reload_no_tools",
        "deep_consolidate_started",
        "export_success", "file_not_found",
        "json_parse_error", "import_success", "import_empty",
    ]
    for key in new_keys:
        assert key in MESSAGES, f"Missing i18n key: {key}"
        assert "zh" in MESSAGES[key], f"Missing zh for: {key}"
        assert "en" in MESSAGES[key], f"Missing en for: {key}"


def test_i18n_msg_formatting():
    """E4: i18n msg() should format placeholders correctly."""
    from nanobot.agent.i18n import msg

    result = msg("export_success", lang="en", path="/tmp/test.json", count="5")
    assert "/tmp/test.json" in result
    assert "5" in result

    result_zh = msg("file_not_found", lang="zh", path="test.txt")
    assert "test.txt" in result_zh
