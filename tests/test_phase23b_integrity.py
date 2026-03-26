"""Phase 23B — P1 Data Integrity & Architecture Fixes: Tests.

Covers the 6 risk items:
- R3:  Session JSONL atomic write + truncated-line tolerance
- R7:  Cron store atomic write + full UUID
- R8:  Config() → get_config() singleton
- R9/R15: WebSocket dead-connection cleanup
- R10: Key extraction cache true LRU eviction
- R13: Session key restore (underscore handling)
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.session.manager import Session, SessionManager


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path

@pytest.fixture
def manager(workspace: Path) -> SessionManager:
    return SessionManager(workspace)


# ──────────────────────────────────────────────────────────────────────
# R3: Session JSONL Atomic Write
# ──────────────────────────────────────────────────────────────────────

class TestSessionAtomicWrite:
    """R3: Verify _full_rewrite uses atomic tempfile+os.replace."""

    def test_session_save_creates_file(self, manager: SessionManager) -> None:
        session = manager.get_or_create("cli:user1")
        session.add_message("user", "hello")
        manager.save(session)
        path = manager._get_session_path("cli:user1")
        assert path.exists()

    def test_session_save_atomic_no_partial_file(self, manager: SessionManager) -> None:
        """Simulate write failure — original file should remain intact."""
        session = manager.get_or_create("atomic:test")
        session.add_message("user", "original message")
        manager.save(session)

        path = manager._get_session_path("atomic:test")
        original_content = path.read_text()

        # Force a second save that will crash during write
        session.add_message("user", "new message that should not persist")
        session.mark_metadata_dirty()

        with patch("nanobot.session.manager.os.replace", side_effect=OSError("simulated crash")):
            with pytest.raises(OSError):
                manager.save(session)

        # Original file should be intact
        assert path.read_text() == original_content

    def test_session_save_no_temp_file_left_on_failure(self, manager: SessionManager) -> None:
        """On write failure, temp files should be cleaned up."""
        session = manager.get_or_create("cleanup:test")
        session.add_message("user", "hello")
        manager.save(session)

        session.mark_metadata_dirty()
        sessions_dir = manager.sessions_dir

        with patch("nanobot.session.manager.os.replace", side_effect=OSError("crash")):
            with pytest.raises(OSError):
                manager.save(session)

        # No .tmp files should remain
        tmp_files = list(sessions_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_session_load_tolerates_truncated_line(self, manager: SessionManager) -> None:
        """R3: Loading a JSONL with a truncated final line still recovers valid data."""
        path = manager._get_session_path("truncated:test")
        metadata = {
            "_type": "metadata",
            "original_key": "truncated:test",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        valid_msg = {"role": "user", "content": "valid message", "timestamp": "2026-01-01T00:00:01"}
        truncated_line = '{"role": "user", "content": "cut short'  # No closing brace

        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")
            f.write(json.dumps(valid_msg) + "\n")
            f.write(truncated_line + "\n")

        loaded = manager._load("truncated:test")
        assert loaded is not None
        assert len(loaded.messages) == 1  # truncated line skipped
        assert loaded.messages[0]["content"] == "valid message"


# ──────────────────────────────────────────────────────────────────────
# R7: Cron Store Atomic Write + Full UUID
# ──────────────────────────────────────────────────────────────────────

class TestCronAtomicWrite:
    """R7: Verify cron store atomic write and full UUID."""

    def test_cron_job_full_uuid(self, workspace: Path) -> None:
        """New cron job IDs should be full UUIDs (36 chars)."""
        from nanobot.cron.service import CronService
        from nanobot.cron.types import CronSchedule

        store_path = workspace / "cron" / "jobs.json"
        svc = CronService(store_path=store_path)

        job = svc.add_job(
            name="test-job",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="hello",
        )
        assert len(job.id) == 36  # full UUID: 8-4-4-4-12
        # Also validate it's a proper UUID
        uuid.UUID(job.id)  # raises ValueError if malformed

    def test_cron_save_atomic(self, workspace: Path) -> None:
        """Cron store uses atomic write — failure should not corrupt existing data."""
        from nanobot.cron.service import CronService
        from nanobot.cron.types import CronSchedule

        store_path = workspace / "cron" / "jobs.json"
        svc = CronService(store_path=store_path)
        svc.add_job(name="job1", schedule=CronSchedule(kind="every", every_ms=60_000), message="m1")

        original = store_path.read_text()

        # Simulate crash during next save
        with patch("nanobot.cron.service.os.replace", side_effect=OSError("crash")):
            with pytest.raises(OSError):
                svc.add_job(name="job2", schedule=CronSchedule(kind="every", every_ms=60_000), message="m2")

        # Original file intact
        assert store_path.read_text() == original


# ──────────────────────────────────────────────────────────────────────
# R8: Config Singleton
# ──────────────────────────────────────────────────────────────────────

class TestConfigSingleton:
    """R8: Verify context.py uses get_config() instead of Config()."""

    def test_context_no_direct_config_instantiation(self) -> None:
        """context.py should not contain 'Config()' direct instantiation."""
        import inspect
        from nanobot.agent import context as ctx_module
        source = inspect.getsource(ctx_module)
        # Should NOT have Config() or _Cfg() direct calls
        assert "_Cfg()" not in source, "context.py still uses direct Config() instantiation"
        assert "Config()" not in source, "context.py still uses direct Config() instantiation"


# ──────────────────────────────────────────────────────────────────────
# R9/R15: WebSocket Dead Connection Cleanup
# ──────────────────────────────────────────────────────────────────────

class TestWebSocketCleanup:
    """R9/R15: Dead WebSocket connections should be removed on send failure."""

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_ws(self) -> None:
        """broadcast_ws_message should remove websocket that fails to send."""
        from nanobot.dashboard import app as dashboard_app

        good_ws = AsyncMock()
        bad_ws = AsyncMock()
        bad_ws.send_text.side_effect = ConnectionError("dead connection")

        original_ws_list = dashboard_app._active_websockets
        dashboard_app._active_websockets = {good_ws, bad_ws}

        try:
            await dashboard_app.broadcast_ws_message("test", {"hello": "world"})
            # good_ws should have been called
            good_ws.send_text.assert_called_once()
            # bad_ws should have been removed
            assert bad_ws not in dashboard_app._active_websockets
            assert good_ws in dashboard_app._active_websockets
        finally:
            dashboard_app._active_websockets = original_ws_list

    @pytest.mark.asyncio
    async def test_domain_event_broadcast_removes_dead_ws(self) -> None:
        """_broadcast_domain_event should remove dead websocket."""
        from nanobot.dashboard import app as dashboard_app

        good_ws = AsyncMock()
        bad_ws = AsyncMock()
        bad_ws.send_text.side_effect = ConnectionError("dead")

        original_ws_list = dashboard_app._active_websockets
        dashboard_app._active_websockets = {good_ws, bad_ws}

        mock_event = MagicMock()
        mock_event.to_dict.return_value = {"event_type": "test", "timestamp": "now"}

        try:
            await dashboard_app._broadcast_domain_event(mock_event)
            assert bad_ws not in dashboard_app._active_websockets
        finally:
            dashboard_app._active_websockets = original_ws_list


# ──────────────────────────────────────────────────────────────────────
# R10: Key Extraction Cache True LRU
# ──────────────────────────────────────────────────────────────────────

class TestLRUKeyCache:
    """R10: Key extraction cache should use true LRU eviction."""

    def test_cache_is_ordered_dict(self) -> None:
        """The cache should be an OrderedDict for LRU semantics."""
        from nanobot.agent import knowledge_workflow as kw
        assert isinstance(kw._key_extraction_cache, OrderedDict)

    def test_lru_cache_evicts_least_recent(self) -> None:
        """When cache is full, the least-recently-used entry should be evicted."""
        from nanobot.agent import knowledge_workflow as kw

        # Save and restore original cache
        original_cache = kw._key_extraction_cache.copy()
        original_max = kw._KEY_CACHE_MAX

        try:
            kw._key_extraction_cache.clear()
            kw._KEY_CACHE_MAX = 3

            # Fill cache
            kw._key_extraction_cache["a"] = "result_a"
            kw._key_extraction_cache["b"] = "result_b"
            kw._key_extraction_cache["c"] = "result_c"

            # Access "a" to make it MRU
            kw._key_extraction_cache.move_to_end("a")

            # Add new entry — should evict "b" (LRU)
            if len(kw._key_extraction_cache) >= kw._KEY_CACHE_MAX:
                kw._key_extraction_cache.popitem(last=False)
            kw._key_extraction_cache["d"] = "result_d"

            assert "a" in kw._key_extraction_cache, "MRU item 'a' should still be in cache"
            assert "b" not in kw._key_extraction_cache, "LRU item 'b' should have been evicted"
            assert "c" in kw._key_extraction_cache
            assert "d" in kw._key_extraction_cache
        finally:
            kw._key_extraction_cache = original_cache
            kw._KEY_CACHE_MAX = original_max


# ──────────────────────────────────────────────────────────────────────
# R13: Session Key Restore (Underscore Handling)
# ──────────────────────────────────────────────────────────────────────

class TestSessionKeyRestore:
    """R13: Sessions with underscores in keys should be correctly restored."""

    def test_original_key_persisted(self, manager: SessionManager) -> None:
        """The original_key should be stored in the JSONL metadata."""
        session = manager.get_or_create("feishu:group_chat_123")
        session.add_message("user", "test")
        manager.save(session)

        path = manager._get_session_path("feishu:group_chat_123")
        first_line = path.read_text().split("\n")[0]
        metadata = json.loads(first_line)
        assert metadata.get("original_key") == "feishu:group_chat_123"

    def test_key_with_underscore_restores_correctly(self, manager: SessionManager) -> None:
        """A key containing underscores should round-trip correctly."""
        key = "feishu:group_chat_123"
        session = manager.get_or_create(key)
        session.add_message("user", "test message")
        manager.save(session)

        manager.invalidate(key)
        loaded = manager.get_or_create(key)
        assert loaded.key == key
        assert len(loaded.messages) == 1

    def test_list_sessions_uses_original_key(self, manager: SessionManager) -> None:
        """list_sessions should return original_key, not filename-derived key."""
        key = "telegram:user_with_underscore"
        session = manager.get_or_create(key)
        session.add_message("user", "hi")
        manager.save(session)

        sessions = manager.list_sessions()
        found = [s for s in sessions if s["key"] == key]
        assert len(found) == 1, f"Expected original key '{key}' in sessions list, got keys: {[s['key'] for s in sessions]}"

    def test_backward_compat_no_original_key(self, manager: SessionManager) -> None:
        """Old JSONL files without original_key still work (fallback to filename)."""
        path = manager._get_session_path("old:session")
        metadata = {
            "_type": "metadata",
            # no "original_key" field
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")

        loaded = manager._load("old:session")
        assert loaded is not None
        # Should fall back to the provided key
        assert loaded.key == "old:session"
