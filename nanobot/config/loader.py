"""Configuration loading utilities."""

import json
from pathlib import Path

from nanobot.config.schema import Config


# ── I1: Process-level Config singleton ──────────────────────────
_config_singleton: Config | None = None


def get_config() -> Config:
    """Return the cached Config singleton (I1: avoids repeated instantiations).

    Call ``invalidate_config()`` to force a reload (e.g. on ``/reload``).
    """
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = load_config()
    return _config_singleton


def invalidate_config() -> None:
    """Reset the Config singleton so the next ``get_config()`` re-reads disk."""
    global _config_singleton
    _config_singleton = None


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from ~/.nanobot/config.json (or a custom path).

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()
    data = {}

    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            data = _migrate_config(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config(**data)


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    F4/Phase 25: Uses atomic write (tempfile + os.replace) to prevent
    corruption if the process crashes mid-write.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    import os
    import tempfile

    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)
    content = json.dumps(data, indent=2)

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
