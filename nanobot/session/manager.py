"""Session management for conversation history."""

__all__ = ["Session", "SessionManager"]

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename


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
    last_task_key: str | None = None  # Last completed task key (for implicit feedback tracking)
    last_tool_calls: list[dict[str, Any]] | None = None  # Last tool calls (for silent steps update)
    message_count_since_consolidation: int = 0  # Auto-consolidation trigger counter
    
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
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name"):
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
        self.last_tool_calls = None
        self.message_count_since_consolidation = 0
        self.updated_at = datetime.now()


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
        self.identity_mapping: dict[str, str] = {}
    
    def set_identity_mapping(self, mapping: dict[str, str]) -> None:
        """Set the master identities mapping to resolve raw keys to master keys."""
        self.identity_mapping = mapping
        
    def resolve_key(self, raw_key: str) -> str:
        """Resolve a raw channel-specific key to a master identity if mapped."""
        return self.identity_mapping.get(raw_key, raw_key)
    
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
            msg_count_since_consolidation = 0
            last_task_key = None
            last_tool_calls = None

            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
                        last_consolidated = data.get("last_consolidated", 0)
                        pending_knowledge = data.get("pending_knowledge")
                        pending_save = data.get("pending_save")
                        pending_upgrade = data.get("pending_upgrade")
                        msg_count_since_consolidation = data.get("message_count_since_consolidation", 0)
                        last_task_key = data.get("last_task_key")
                        last_tool_calls = data.get("last_tool_calls")
                    else:
                        messages.append(data)

            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                updated_at=updated_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
                pending_knowledge=pending_knowledge,
                pending_save=pending_save,
                pending_upgrade=pending_upgrade,
                last_task_key=last_task_key,
                last_tool_calls=last_tool_calls,
                message_count_since_consolidation=msg_count_since_consolidation,
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """Save a session to disk."""
        resolved_key = self.resolve_key(session.key)
        
        # Ensure the session key reflects its resolved identity to avoid mismatches
        session.key = resolved_key
        path = self._get_session_path(resolved_key)

        with open(path, "w") as f:
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated,
                "pending_knowledge": session.pending_knowledge,
                "pending_save": session.pending_save,
                "pending_upgrade": session.pending_upgrade,
                "last_task_key": session.last_task_key,
                "last_tool_calls": session.last_tool_calls,
                "message_count_since_consolidation": session.message_count_since_consolidation,
            }
            f.write(json.dumps(metadata_line) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")

        self._cache[session.key] = session
        self._evict_lru()
    
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
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Skipping session {path.name}: {e}")
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
