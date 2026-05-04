"""Repo-root resolution for harness commands."""

import os
from pathlib import Path

REPO_MARKER = Path(".agent/workflows/harness_lite.md")


def _has_repo_marker(candidate: Path) -> bool:
    return (candidate / REPO_MARKER).is_file()


def _should_stop_search(candidate: Path) -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ and candidate.name.startswith(".pytest_")


def resolve_repo_root(explicit_root: str | None, cwd: Path | None = None) -> Path:
    """Resolve the harness repo root using an explicit path or marker search."""
    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()
        if _has_repo_marker(root):
            return root
        raise ValueError(
            "repo root marker not found at the provided --root path. "
            "Pass the repository root that contains .agent/workflows/harness_lite.md."
        )

    current = (cwd or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if _has_repo_marker(candidate):
            return candidate
        if _should_stop_search(candidate):
            break

    raise ValueError(
        "repo root not found. Run the command inside the repository or pass --root <repo_root>."
    )
