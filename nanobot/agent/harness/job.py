"""Job metadata helpers for harness orchestration."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nanobot.utils.helpers import safe_replace


def utc_now_iso() -> str:
    """Return a stable UTC timestamp string for snapshots."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return slug.strip("_")[:48] or "job"


def generate_job_id(goal: str, mode: str = "lite") -> str:
    """Generate a stable ASCII job id."""
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    return f"{mode}_{date_part}_{_slugify(goal)}"


def load_state(path: Path) -> dict[str, Any]:
    """Load a snapshot file if it exists and is valid JSON."""
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}

def write_state(path: Path, payload: dict[str, Any]) -> None:
    """Write a formatted JSON snapshot to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    safe_replace(temp_path, path)
