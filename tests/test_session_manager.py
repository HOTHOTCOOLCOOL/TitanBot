"""Tests for SessionManager CRUD, persistence, and edge cases."""

import json
import pytest
from pathlib import Path
from datetime import datetime

from nanobot.session.manager import Session, SessionManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    return tmp_path


@pytest.fixture
def manager(workspace: Path) -> SessionManager:
    """Create a SessionManager with a temporary workspace."""
    return SessionManager(workspace)


# ── Session Dataclass ──

class TestSession:
    """Unit tests for the Session dataclass."""

    def test_add_message(self) -> None:
        s = Session(key="test")
        s.add_message("user", "hello")
        assert len(s.messages) == 1
        assert s.messages[0]["role"] == "user"
        assert s.messages[0]["content"] == "hello"
        assert "timestamp" in s.messages[0]

    def test_add_message_with_kwargs(self) -> None:
        s = Session(key="test")
        s.add_message("assistant", "hi", tools_used=["exec"])
        assert s.messages[0]["tools_used"] == ["exec"]

    def test_get_history_format(self) -> None:
        s = Session(key="test")
        s.add_message("user", "hello")
        s.add_message("assistant", "hi there")
        history = s.get_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

    def test_get_history_max_messages(self) -> None:
        s = Session(key="test")
        for i in range(10):
            s.add_message("user", f"msg {i}")
        history = s.get_history(max_messages=3)
        assert len(history) == 3
        assert history[0]["content"] == "msg 7"

    def test_clear_resets_all(self) -> None:
        s = Session(key="test")
        s.add_message("user", "hello")
        s.pending_knowledge = {"key": "test"}
        s.pending_save = {"key": "test"}
        s.pending_upgrade = {"key": "test"}
        s.last_tool_calls = [{"tool": "exec"}]
        s.message_count_since_consolidation = 5

        s.clear()

        assert s.messages == []
        assert s.pending_knowledge is None
        assert s.pending_save is None
        assert s.pending_upgrade is None
        assert s.last_tool_calls is None
        assert s.message_count_since_consolidation == 0


# ── SessionManager CRUD ──

class TestSessionManagerCRUD:
    """Test create, save, load, invalidate cycle."""

    def test_get_or_create_new_session(self, manager: SessionManager) -> None:
        session = manager.get_or_create("cli:user1")
        assert session.key == "cli:user1"
        assert session.messages == []

    def test_get_or_create_returns_cached(self, manager: SessionManager) -> None:
        s1 = manager.get_or_create("cli:user1")
        s1.add_message("user", "cached message")
        s2 = manager.get_or_create("cli:user1")
        assert s2 is s1
        assert len(s2.messages) == 1

    def test_get_or_create_expires_old_session(self, manager: SessionManager) -> None:
        s1 = manager.get_or_create("cli:user1")
        s1.add_message("user", "old message")
        manager.save(s1)
        
        # Manually backdate the session
        from datetime import timedelta
        s1.updated_at -= timedelta(hours=25)
        s1.mark_metadata_dirty()  # Phase 22D: ensure backdated timestamp is written to disk
        manager.save(s1)
        manager.invalidate("cli:user1")
        
        # Get it again, it should be cleared due to expiry
        s2 = manager.get_or_create("cli:user1", expiry_hours=24)
        assert len(s2.messages) == 0
        assert s2.updated_at != s1.updated_at

    def test_save_and_load(self, manager: SessionManager) -> None:
        session = manager.get_or_create("cli:user1")
        session.add_message("user", "hello")
        session.add_message("assistant", "hi!")
        manager.save(session)

        # Clear cache and reload
        manager.invalidate("cli:user1")
        loaded = manager.get_or_create("cli:user1")
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["content"] == "hello"
        assert loaded.messages[1]["content"] == "hi!"

    def test_pending_states_persist(self, manager: SessionManager) -> None:
        session = manager.get_or_create("cli:user1")
        session.pending_knowledge = {"key": "test_task", "_original_request": "do stuff"}
        session.pending_save = {"key": "save_key"}
        session.last_task_key = "my_task"
        session.last_tool_calls = [{"tool": "exec", "args": {"command": "ls"}}]
        session.message_count_since_consolidation = 7
        manager.save(session)

        manager.invalidate("cli:user1")
        loaded = manager.get_or_create("cli:user1")
        assert loaded.pending_knowledge is not None
        assert loaded.pending_knowledge["key"] == "test_task"
        assert loaded.pending_save is not None
        assert loaded.last_task_key == "my_task"
        assert loaded.last_tool_calls is not None
        assert loaded.message_count_since_consolidation == 7

    def test_invalidate_removes_from_cache(self, manager: SessionManager) -> None:
        s = manager.get_or_create("cli:user1")
        s.add_message("user", "test")
        manager.save(s)
        manager.invalidate("cli:user1")
        assert "cli:user1" not in manager._cache


# ── JSONL Format ──

class TestJSONLFormat:
    """Verify the JSONL serialization format is correct."""

    def test_jsonl_file_structure(self, manager: SessionManager) -> None:
        session = manager.get_or_create("cli:user1")
        session.add_message("user", "hello")
        session.add_message("assistant", "world")
        manager.save(session)

        path = manager._get_session_path("cli:user1")
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3  # metadata + 2 messages

        metadata = json.loads(lines[0])
        assert metadata["_type"] == "metadata"
        assert "created_at" in metadata

        msg1 = json.loads(lines[1])
        assert msg1["role"] == "user"
        assert msg1["content"] == "hello"

        msg2 = json.loads(lines[2])
        assert msg2["role"] == "assistant"


# ── Edge Cases ──

class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_corrupted_jsonl_returns_session_with_skipped_lines(self, manager: SessionManager) -> None:
        """R3: Corrupted lines are skipped, valid session still returned."""
        path = manager._get_session_path("broken:session")
        path.write_text("this is not valid json\n{also broken\n")
        loaded = manager._load("broken:session")
        # R3: Invalid lines are now skipped, session returns with empty messages
        assert loaded is not None
        assert loaded.messages == []

    def test_empty_file_returns_none(self, manager: SessionManager) -> None:
        path = manager._get_session_path("empty:session")
        path.write_text("")
        loaded = manager._load("empty:session")
        # Empty file: no metadata, no messages → returns Session with empty state
        # (the loader handles this via the loop that reads nothing)
        assert loaded is not None
        assert loaded.messages == []

    def test_list_sessions(self, manager: SessionManager) -> None:
        for name in ["a:1", "b:2", "c:3"]:
            s = manager.get_or_create(name)
            s.add_message("user", f"msg for {name}")
            manager.save(s)

        sessions = manager.list_sessions()
        assert len(sessions) >= 3
        keys = [s["key"] for s in sessions]
        assert "a_1" in keys or "a:1" in keys  # safe_filename replaces ':'

    def test_special_characters_in_key(self, manager: SessionManager) -> None:
        """Session keys with special characters are safely handled."""
        key = "telegram:user@123/test"
        s = manager.get_or_create(key)
        s.add_message("user", "test")
        manager.save(s)
        manager.invalidate(key)
        loaded = manager.get_or_create(key)
        assert len(loaded.messages) == 1
