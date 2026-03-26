"""Utility functions for nanobot."""

import os
import time
from datetime import datetime
from pathlib import Path

from loguru import logger


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    """Get the nanobot data directory (~/.nanobot)."""
    return ensure_dir(Path.home() / ".nanobot")


def get_workspace_path(workspace: str | None = None) -> Path:
    """
    Get the workspace path.
    
    Args:
        workspace: Optional workspace path. Defaults to ~/.nanobot/workspace.
    
    Returns:
        Expanded and ensured workspace path.
    """
    if workspace:
        path = Path(workspace).expanduser()
    else:
        path = Path.home() / ".nanobot" / "workspace"
    return ensure_dir(path)


def get_sessions_path() -> Path:
    """Get the sessions storage directory."""
    return ensure_dir(get_data_path() / "sessions")


def get_skills_path(workspace: Path | None = None) -> Path:
    """Get the skills directory within the workspace."""
    ws = workspace or get_workspace_path()
    return ensure_dir(ws / "skills")


def timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def truncate_string(s: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate a string to max length, adding suffix if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    # Replace unsafe characters
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()


def parse_session_key(key: str) -> tuple[str, str]:
    """
    Parse a session key into channel and chat_id.
    
    Args:
        key: Session key in format "channel:chat_id"
    
    Returns:
        Tuple of (channel, chat_id)
    """
    parts = key.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid session key: {key}")
    return parts[0], parts[1]


def safe_replace(src: str | Path, dst: str | Path, max_retries: int = 5, base_delay: float = 0.1) -> None:
    """
    Safely replace a file, with retry logic for Windows PermissionError.
    
    Anti-virus software (like Windows Defender) often temporarily locks newly created files,
    causing os.replace() to throw PermissionError on Windows (Phase 27).
    """
    src_str, dst_str = str(src), str(dst)
    for attempt in range(max_retries):
        try:
            os.replace(src_str, dst_str)
            return
        except PermissionError as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f"PermissionError on replace '{src_str}' -> '{dst_str}'. Retrying in {delay:.2f}s...")
                time.sleep(delay)
            else:
                logger.error(f"Failed to replace '{src_str}' -> '{dst_str}' after {max_retries} attempts.")
                raise e

