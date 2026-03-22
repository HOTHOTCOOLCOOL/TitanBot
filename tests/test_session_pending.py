"""Tests for Session pending_knowledge and pending_save persistence."""

import json
import pytest
from pathlib import Path
from typing import Any

from nanobot.session.manager import Session, SessionManager


@pytest.fixture
def temp_manager(tmp_path: Path) -> SessionManager:
    """Create a SessionManager backed by a temporary directory."""
    return SessionManager(tmp_path)


class TestSessionPendingFields:
    """Test that pending_knowledge and pending_save fields work correctly."""

    def test_initial_pending_none(self):
        """New session has None pending fields."""
        session = Session(key="test:1")
        assert session.pending_knowledge is None
        assert session.pending_save is None

    def test_set_pending_knowledge(self):
        """Can set pending_knowledge dict."""
        session = Session(key="test:1")
        session.pending_knowledge = {
            "key": "weather",
            "steps": [{"tool": "web_search"}],
            "_original_request": "what's the weather?",
        }
        assert session.pending_knowledge is not None
        assert session.pending_knowledge["key"] == "weather"

    def test_set_pending_save(self):
        """Can set pending_save dict."""
        session = Session(key="test:1")
        session.pending_save = {
            "key": "list_files",
            "steps": [{"tool": "exec", "args": {"cmd": "ls"}}],
            "user_request": "list files",
        }
        assert session.pending_save is not None
        assert session.pending_save["key"] == "list_files"

    def test_clear_resets_pending(self):
        """clear() resets both pending fields to None."""
        session = Session(key="test:1")
        session.pending_knowledge = {"key": "test"}
        session.pending_save = {"key": "save_test"}

        session.clear()

        assert session.pending_knowledge is None
        assert session.pending_save is None
        assert session.messages == []
        assert session.last_consolidated == 0


class TestSessionPendingPersistence:
    """Test that pending fields persist across save/load cycles."""

    def test_pending_knowledge_persists(self, temp_manager: SessionManager):
        """pending_knowledge survives save/load cycle."""
        session = temp_manager.get_or_create("test:persist_knowledge")
        session.pending_knowledge = {
            "key": "search task",
            "steps": [{"tool": "web_search"}],
            "_original_request": "search for info",
        }
        session.add_message("user", "hello")
        temp_manager.save(session)

        # Invalidate cache and reload
        temp_manager.invalidate("test:persist_knowledge")
        reloaded = temp_manager.get_or_create("test:persist_knowledge")

        assert reloaded.pending_knowledge is not None
        assert reloaded.pending_knowledge["key"] == "search task"
        assert reloaded.pending_knowledge["_original_request"] == "search for info"

    def test_pending_save_persists(self, temp_manager: SessionManager):
        """pending_save survives save/load cycle."""
        session = temp_manager.get_or_create("test:persist_save")
        session.pending_save = {
            "key": "compile",
            "steps": [{"tool": "exec", "args": {"cmd": "make"}}],
            "user_request": "compile project",
            "result_summary": "Build succeeded",
        }
        session.add_message("user", "compile project")
        temp_manager.save(session)

        temp_manager.invalidate("test:persist_save")
        reloaded = temp_manager.get_or_create("test:persist_save")

        assert reloaded.pending_save is not None
        assert reloaded.pending_save["key"] == "compile"
        assert reloaded.pending_save["result_summary"] == "Build succeeded"

    def test_none_pending_persists(self, temp_manager: SessionManager):
        """None pending values persist correctly (no spurious data)."""
        session = temp_manager.get_or_create("test:persist_none")
        session.add_message("user", "hello")
        temp_manager.save(session)

        temp_manager.invalidate("test:persist_none")
        reloaded = temp_manager.get_or_create("test:persist_none")

        assert reloaded.pending_knowledge is None
        assert reloaded.pending_save is None

    def test_clear_and_save_persists(self, temp_manager: SessionManager):
        """clear() followed by save removes pending data from disk."""
        session = temp_manager.get_or_create("test:clear_save")
        session.pending_knowledge = {"key": "to_be_cleared"}
        session.pending_save = {"key": "to_be_cleared_too"}
        session.add_message("user", "hello")
        temp_manager.save(session)

        session.clear()
        temp_manager.save(session)

        temp_manager.invalidate("test:clear_save")
        reloaded = temp_manager.get_or_create("test:clear_save")

        assert reloaded.pending_knowledge is None
        assert reloaded.pending_save is None
        assert reloaded.messages == []
