"""Session management for conversation history.

Phase 22D: Added metadata dirty flag and append-only optimization.
"""

__all__ = ["Session", "SessionManager"]

import json
import os
import tempfile
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename, safe_replace

# I4: UTF-8 encoding constant for cross-platform consistency
_ENCODING = "utf-8"


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already consolidated to files
    pending_knowledge: dict[str, Any] | None = None  # Awaiting user reply on knowledge match
    pending_save: dict[str, Any] | None = None  # Awaiting user confirmation to save
    pending_upgrade: dict[str, Any] | None = None  # Awaiting user confirmation to upgrade skill
    pending_approval_task: dict[str, Any] | None = None  # Awaiting human-in-the-loop High-Risk approval
    last_task_key: str | None = None  # Last completed task key (for implicit feedback tracking)
    last_tool_calls: list[dict[str, Any]] | None = None  # Last tool calls (for silent steps update)
    message_count_since_consolidation: int = 0  # Auto-consolidation trigger counter
    evicted_context: str | None = None  # Virtual paging summary of dropped messages
    _last_saved_msg_count: int = 0  # I4/22D: track for append-only optimization
    _metadata_dirty: bool = True  # Phase 22D: when False, save() can use append-only
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Get recent messages in LLM format, preserving tool metadata."""
        out: list[dict[str, Any]] = []
        for m in self.messages[-max_messages:]:
            content = m.get("content")
            if content is None and m["role"] == "assistant" and "tool_calls" in m:
                pass # keep it None
            elif content is None:
                content = ""
            entry: dict[str, Any] = {"role": m["role"], "content": content}
            for k in ("tool_calls", "tool_call_id", "name", "media"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)
        return out
    
    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.last_consolidated = 0
        self.pending_knowledge = None
        self.pending_save = None
        self.pending_upgrade = None
        self.pending_approval_task = None
        self.last_tool_calls = None
        self.message_count_since_consolidation = 0
        self.evicted_context = None
        self.updated_at = datetime.now()
        self._metadata_dirty = True
        self._last_saved_msg_count = 0

    def clear_pending(self) -> None:
        """Clear all pending interactive states (L2: mutual exclusion)."""
        self.pending_knowledge = None
        self.pending_save = None
        self.pending_upgrade = None
        self.pending_approval_task = None
        self._metadata_dirty = True

    def mark_metadata_dirty(self) -> None:
        """Phase 22D: Explicitly mark metadata as needing a full rewrite on next save."""
        self._metadata_dirty = True

    def to_snapshot(self) -> dict:
        """返回用于后台任务的不可变快照（深拷贝字典）。"""
        import copy
        return {
            "key": self.key,
            "messages": copy.deepcopy(self.messages),
            "last_consolidated": self.last_consolidated,
            "evicted_context": self.evicted_context,
            "message_count_since_consolidation": self.message_count_since_consolidation,
            "metadata": copy.deepcopy(self.metadata),
        }


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored as JSONL files in the sessions directory.
    In-memory cache uses LRU eviction (maxsize=128) to prevent unbounded growth.
    """

    CACHE_MAX_SIZE: int = 128

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = Path.home() / ".nanobot" / "sessions"
        self._cache: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.identity_mapping: dict[str, str] = {}
        self.pending_approvals: dict[str, str] = {}  # short_id -> session_key
    
    def get_session_lock(self, key: str) -> asyncio.Lock:
        """获取 session 级别的排他锁。"""
        resolved = self.resolve_key(key)
        if resolved not in self._locks:
            self._locks[resolved] = asyncio.Lock()
        return self._locks[resolved]
    
    def set_identity_mapping(self, mapping: dict[str, str]) -> None:
        """Set the master identities mapping to resolve raw keys to master keys."""
        self.identity_mapping = mapping
        
    def resolve_key(self, raw_key: str) -> str:
        """Resolve a raw channel-specific key to a master identity if mapped."""
        return self.identity_mapping.get(raw_key, raw_key)
        
    def register_approval(self, short_id: str, session_key: str) -> None:
        """Register a high-risk operation's short ID to its origin session."""
        self.pending_approvals[short_id] = session_key

    def get_approval_session(self, short_id: str) -> str | None:
        """Retrieve the origin session for a pending remote approval."""
        return self.pending_approvals.get(short_id)
        
    def remove_approval(self, short_id: str) -> None:
        """Remove a remote approval mapping after handling."""
        self.pending_approvals.pop(short_id, None)
    
    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def _get_legacy_session_path(self, key: str) -> Path:
        """Legacy global session path (~/.nanobot/sessions/)."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.legacy_sessions_dir / f"{safe_key}.jsonl"
    
    def _evict_lru(self) -> None:
        """Evict the oldest cached session if cache exceeds max size."""
        while len(self._cache) > self.CACHE_MAX_SIZE:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)

    def get_or_create(self, key: str, expiry_hours: int = 24) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).
            expiry_hours: Number of hours before an inactive session expires.

        Returns:
            The session.
        """
        key = self.resolve_key(key)
        if key in self._cache:
            session = self._cache[key]
        else:
            session = self._load(key)

        if session is None:
            session = Session(key=key)
        else:
            # Check for session expiration
            from datetime import datetime, timedelta
            if datetime.now() - session.updated_at > timedelta(hours=expiry_hours):
                logger.info(f"Session {key} expired (inactive for > {expiry_hours}h). Starting fresh.")
                session.clear()

        self._cache[key] = session
        self._evict_lru()
        return session
    
    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        if not path.exists():
            legacy_path = self._get_legacy_session_path(key)
            if legacy_path.exists():
                import shutil
                shutil.move(str(legacy_path), str(path))
                logger.info(f"Migrated session {key} from legacy path")

        if not path.exists():
            return None

        try:
            messages = []
            metadata = {}
            created_at = None
            updated_at = None
            last_consolidated = 0
            # Store full data line to extract top-level fields
            pending_knowledge = None
            pending_save = None
            pending_upgrade = None
            pending_approval_task = None
            msg_count_since_consolidation = 0
            last_task_key = None
            last_tool_calls = None
            evicted_context = None

            original_key = None  # R13: stored original session key
            with open(path, encoding=_ENCODING) as f:  # B6: explicit UTF-8
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    # R3: Tolerate truncated JSON lines (e.g. crash during append)
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(f"Session {key}: skipping truncated line {line_num}")
                        continue

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        original_key = data.get("original_key")  # R13
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
                        last_consolidated = data.get("last_consolidated", 0)
                        pending_knowledge = data.get("pending_knowledge")
                        pending_save = data.get("pending_save")
                        pending_upgrade = data.get("pending_upgrade")
                        pending_approval_task = data.get("pending_approval_task")
                        msg_count_since_consolidation = data.get("message_count_since_consolidation", 0)
                        last_task_key = data.get("last_task_key")
                        last_tool_calls = data.get("last_tool_calls")
                        evicted_context = data.get("evicted_context")
                    else:
                        messages.append(data)

            return Session(
                key=original_key or key,  # R13: prefer stored original key
                messages=messages,
                created_at=created_at or datetime.now(),
                updated_at=updated_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
                pending_knowledge=pending_knowledge,
                pending_save=pending_save,
                pending_upgrade=pending_upgrade,
                pending_approval_task=pending_approval_task,
                last_task_key=last_task_key,
                last_tool_calls=last_tool_calls,
                message_count_since_consolidation=msg_count_since_consolidation,
                evicted_context=evicted_context,
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """Save a session to disk.

        Phase 22D: Uses append-only mode when metadata hasn't changed
        and only new messages need to be written. Falls back to full
        rewrite when metadata is dirty or messages were removed/reset.
        """
        resolved_key = self.resolve_key(session.key)

        # Ensure the session key reflects its resolved identity to avoid mismatches
        session.key = resolved_key
        path = self._get_session_path(resolved_key)

        new_msg_count = len(session.messages)
        can_append = (
            not session._metadata_dirty
            and path.exists()
            and new_msg_count >= session._last_saved_msg_count
            and session._last_saved_msg_count > 0
        )

        if can_append:
            # Append-only: just write new messages since last save
            new_messages = session.messages[session._last_saved_msg_count:]
            if new_messages:
                with open(path, "a", encoding=_ENCODING) as f:
                    for msg in new_messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                session._last_saved_msg_count = new_msg_count
                session.updated_at = datetime.now()  # F2/Phase 25
                # F2: Periodically flush metadata so timestamps are persisted
                if len(new_messages) >= 10:
                    session._metadata_dirty = True
                logger.debug(f"Session {session.key}: appended {len(new_messages)} messages")
        else:
            # Full rewrite: metadata changed or file needs regenerating
            self._full_rewrite(path, session)
            session._metadata_dirty = False
            session._last_saved_msg_count = new_msg_count

        self._cache[session.key] = session
        self._evict_lru()

    def _full_rewrite(self, path: Path, session: Session) -> None:
        """Full rewrite of the session JSONL file.

        R3: Uses tempfile + os.replace for atomic writes.  If the process
        crashes mid-write, the original file remains intact.
        """
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding=_ENCODING) as f:
                metadata_line = {
                    "_type": "metadata",
                    "original_key": session.key,  # R13: persist original key
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata,
                    "last_consolidated": session.last_consolidated,
                    "pending_knowledge": session.pending_knowledge,
                    "pending_save": session.pending_save,
                    "pending_upgrade": session.pending_upgrade,
                    "pending_approval_task": session.pending_approval_task,
                    "last_task_key": session.last_task_key,
                    "last_tool_calls": session.last_tool_calls,
                    "message_count_since_consolidation": session.message_count_since_consolidation,
                    "evicted_context": session.evicted_context,
                }
                f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
                for msg in session.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            safe_replace(tmp, str(path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    
    def invalidate(self, key: str) -> None:
        """Remove a session from the in-memory cache."""
        key = self.resolve_key(key)
        self._cache.pop(key, None)
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.
        
        Returns:
            List of session info dicts.
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path, encoding=_ENCODING) as f:  # B6: explicit UTF-8
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            # R13: prefer stored original_key over filename-derived key
                            sessions.append({
                                "key": data.get("original_key", path.stem.replace("_", ":")),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Skipping session {path.name}: {e}")
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    # ── Phase 40B-1: Checkpoint Management ──

    def get_checkpoint_dir(self) -> Path:
        """Return the checkpoint directory (lazily created)."""
        ckpt_dir = self.sessions_dir / ".checkpoints"
        ckpt_dir.mkdir(exist_ok=True)
        return ckpt_dir

    def write_checkpoint(self, session_key: str, tool_calls: list[dict]) -> Path | None:
        """Write a checkpoint file before tool execution.

        Returns the checkpoint path on success, or None on failure.
        The checkpoint is a lightweight JSON file recording:
        - session_key: which session was executing
        - tools: list of tool names about to execute
        - args_preview: truncated args for each tool (debug context)
        - timestamp: ISO timestamp of checkpoint creation

        Designed to be fast (<1ms) — minimal JSON serialization.
        """
        try:
            import json
            from datetime import datetime

            ckpt_dir = self.get_checkpoint_dir()
            safe_key = safe_filename(session_key.replace(":", "_"))
            ckpt_path = ckpt_dir / f"{safe_key}.ckpt.json"

            # Build minimal checkpoint payload
            tools_info = []
            for tc in tool_calls:
                name = tc.get("name") or tc.get("tool", "?")
                args = tc.get("arguments") or tc.get("args", {})
                args_preview = json.dumps(args, ensure_ascii=False)[:200]
                tools_info.append({"name": name, "args_preview": args_preview})

            payload = {
                "session_key": session_key,
                "tools": tools_info,
                "timestamp": datetime.now().isoformat(),
            }

            # Atomic write via tempfile + replace
            fd, tmp = tempfile.mkstemp(dir=str(ckpt_dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding=_ENCODING) as f:
                    json.dump(payload, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                safe_replace(tmp, str(ckpt_path))
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

            return ckpt_path
        except Exception as e:
            logger.warning(f"Phase 40B: Failed to write checkpoint: {e}")
            return None

    def clear_checkpoint(self, path: Path | None) -> None:
        """Remove a checkpoint file after successful tool execution."""
        if path and path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.debug(f"Phase 40B: Failed to clear checkpoint {path.name}: {e}")

    def scan_stale_checkpoints(self) -> list[dict]:
        """Scan for stale checkpoint files left by a previous crash.

        Returns a list of checkpoint payloads (dicts) found.
        Each stale checkpoint file is deleted after reading.
        """
        ckpt_dir = self.get_checkpoint_dir()
        stale = []
        for ckpt_file in ckpt_dir.glob("*.ckpt.json"):
            try:
                import json
                payload = json.loads(ckpt_file.read_text(encoding=_ENCODING))
                stale.append(payload)
                ckpt_file.unlink()
                logger.info(f"Phase 40B: Recovered stale checkpoint for session '{payload.get('session_key', '?')}'")
            except Exception as e:
                logger.warning(f"Phase 40B: Failed to read stale checkpoint {ckpt_file.name}: {e}")
                # Try to clean up corrupted checkpoint
                try:
                    ckpt_file.unlink()
                except OSError:
                    pass
        return stale

