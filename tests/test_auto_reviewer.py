from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest


def _load_auto_reviewer():
    script_path = Path(__file__).resolve().parents[1] / ".agent" / "scripts" / "auto_reviewer.py"
    spec = importlib.util.spec_from_file_location("auto_reviewer_test_module", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def local_tmp_path() -> Path:
    base = Path(".pytest_tmp_auto_reviewer")
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=str(base.resolve())))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_auto_reviewer_infers_allowed_write_set_from_latest_execute_phase_handoff(local_tmp_path: Path):
    auto_reviewer = _load_auto_reviewer()
    auto_reviewer.REPO_ROOT = local_tmp_path

    artifact_dir = local_tmp_path / ".agent" / "artifacts" / "execute_phase" / "job_demo"
    artifact_dir.mkdir(parents=True)
    handoff = artifact_dir / "codex_handoff.md"
    handoff.write_text(
        """# Codex Handoff

## Allowed Write Set

- `nanobot/cli/commands.py`
- `tests/test_harness_cli.py`
- `.agent/scripts/auto_reviewer.py`
""",
        encoding="utf-8",
    )

    (local_tmp_path / "nanobot" / "cli").mkdir(parents=True)
    (local_tmp_path / "tests").mkdir(parents=True)
    (local_tmp_path / ".agent" / "scripts").mkdir(parents=True)
    (local_tmp_path / "nanobot" / "cli" / "commands.py").write_text("", encoding="utf-8")
    (local_tmp_path / "tests" / "test_harness_cli.py").write_text("", encoding="utf-8")
    (local_tmp_path / ".agent" / "scripts" / "auto_reviewer.py").write_text("", encoding="utf-8")

    resolved = auto_reviewer._resolve_review_files([])

    assert resolved == [
        "nanobot/cli/commands.py",
        "tests/test_harness_cli.py",
        ".agent/scripts/auto_reviewer.py",
    ]


def test_auto_reviewer_local_fallback_passes_clean_python_plus_tests_scope():
    auto_reviewer = _load_auto_reviewer()

    findings = auto_reviewer._classify_local_findings(
        ["nanobot/cli/commands.py", "tests/test_harness_cli.py"],
        """diff --git a/nanobot/cli/commands.py b/nanobot/cli/commands.py
+def demo():
+    return "ok"
diff --git a/tests/test_harness_cli.py b/tests/test_harness_cli.py
+def test_demo():
+    assert True
""",
    )

    assert findings == {"A": [], "B": [], "C": []}


def test_auto_reviewer_local_fallback_flags_unresolved_merge_markers():
    auto_reviewer = _load_auto_reviewer()

    findings = auto_reviewer._classify_local_findings(
        ["nanobot/cli/commands.py"],
        """diff --git a/nanobot/cli/commands.py b/nanobot/cli/commands.py
+<<<<<<< HEAD
+print("debug")
+=======
+print("other")
+>>>>>>> branch
""",
    )

    assert findings["A"] == ["Diff still contains unresolved merge-conflict markers."]
