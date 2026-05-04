import json
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import app


runner = CliRunner()
STUB = "<!-- HARNESS:STUB -->"


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def local_tmp_path() -> Path:
    base = Path(".pytest_tmp_harness_cli")
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=str(base.resolve())))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_fake_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    _write(repo_root / ".agent/workflows/harness_lite.md", "# harness marker\n")
    return repo_root


def _artifact_dir(repo_root: Path, job_id: str) -> Path:
    return repo_root / ".agent/artifacts/harness_lite" / job_id


def _ready_problem_statement(job_id: str) -> str:
    return f"""# Problem Statement

Job ID
{job_id}

Goal
Test goal

Source Context
docs/spec.md

In Scope
lite-only orchestration

Out of Scope
heavy mode

Expected Output
launcher + artifacts
"""


def _ready_baseline() -> str:
    return """# Baseline

Claim / Evidence / Status

Source of Truth Files
- .agent/workflows/harness_lite.md

Unknowns
- none

Questions the Critic Must Attack
- test attack surface
"""


def _ready_draft() -> str:
    return """# Draft V1

当前方案摘要
- draft summary

关键 trade-off
- keep lite-only

风险与假设
- launcher must be exact

仍待验证的点
- status derivation
"""


def _ready_review_packet() -> str:
    return """# Review Packet

Findings
- F1

Must Keep
- lite-only

Weak Claims / Unverified Claims
- none

Acceptance Checklist
| A# | Claim | Evidence Method | Expected Result | If Fail |
| --- | --- | --- | --- | --- |
| A1 | demo | demo | demo | demo |
"""


def _ready_candidate() -> str:
    return """# Candidate

Adopted Criticisms
- adopted

Rejected Criticisms
- rejected

Final Candidate
- final

Residual Risks
- low

Evidence Plan
- A1
"""


def _ready_evidence_gate() -> str:
    return """# Evidence Gate

A# / Status / Evidence / Meaning

| A# | Status | Evidence | Meaning |
| --- | --- | --- | --- |
| A1 | PASS | demo | demo |

PASS

Decision
done
"""


def _bad_evidence_gate() -> str:
    return """# Evidence Gate

PASS

Decision
done
"""


def _seed_lite_artifacts(
    repo_root: Path,
    job_id: str,
    *,
    review_ready: bool = False,
    candidate_ready: bool = False,
    evidence_gate: str = STUB,
    state_stage: str = "INIT",
) -> Path:
    artifact_dir = _artifact_dir(repo_root, job_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    _write(artifact_dir / "problem_statement.md", _ready_problem_statement(job_id))
    _write(artifact_dir / "baseline.md", _ready_baseline())
    _write(artifact_dir / "draft_v1.md", _ready_draft())
    _write(
        artifact_dir / "review_packet.md",
        _ready_review_packet() if review_ready else STUB,
    )
    _write(
        artifact_dir / "candidate.md",
        _ready_candidate() if candidate_ready else STUB,
    )
    _write(artifact_dir / "evidence_gate.md", evidence_gate)
    _write(
        artifact_dir / "state.json",
        json.dumps(
            {
                "job_id": job_id,
                "mode": "lite",
                "derived_stage": state_stage,
                "blockers": ["stale snapshot"],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return artifact_dir


def _expected_start_launcher(job_id: str, source: str, goal: str) -> str:
    return f"""请按 harness_lite 工作流启动任务。
job_id: {job_id}
source: {source}
goal: {goal}"""


def _expected_critic_launcher(job_id: str) -> str:
    return f"""请按 harness_lite 的 Critic 阶段执行。
先读取 `.agent/artifacts/harness_lite/{job_id}/problem_statement.md`
再读取 `.agent/artifacts/harness_lite/{job_id}/baseline.md`
再读取 `.agent/artifacts/harness_lite/{job_id}/draft_v1.md`
必要时只额外读取上述 Artifact 中明确点名的 repo 文件。
不要读取其他聊天历史，不要润色，不要替作者圆方案。
把结果写入 `.agent/artifacts/harness_lite/{job_id}/review_packet.md`
如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。"""


def _expected_synthesis_launcher(job_id: str) -> str:
    return f"""继续 harness_lite 综合与核验，job_id={job_id}
请先读取 `.agent/artifacts/harness_lite/{job_id}/review_packet.md`
然后写出 `candidate.md` 并执行 Evidence Gate，结果写入 `evidence_gate.md`。
若有关键项 FAIL 或 BLOCKED，不得宣称完成。"""


def test_harness_start_lite_scaffolds_repo_local_artifacts_and_prints_exact_launcher(
    local_tmp_path: Path, monkeypatch
):
    repo_root = _make_fake_repo(local_tmp_path)
    monkeypatch.chdir(repo_root)

    result = runner.invoke(
        app,
        [
            "harness",
            "start",
            "--mode",
            "lite",
            "--goal",
            "Implement Harness Orchestration",
            "--source",
            "docs/harness_orchestration_blueprint.md",
        ],
    )

    assert result.exit_code == 0

    artifact_root = repo_root / ".agent/artifacts/harness_lite"
    jobs = [path.name for path in artifact_root.iterdir() if path.is_dir()]
    assert len(jobs) == 1
    job_id = jobs[0]

    for filename in [
        "problem_statement.md",
        "baseline.md",
        "draft_v1.md",
        "review_packet.md",
        "candidate.md",
        "evidence_gate.md",
        "state.json",
    ]:
        assert (artifact_root / job_id / filename).exists()

    assert _normalize(result.output) == _expected_start_launcher(
        job_id,
        "docs/harness_orchestration_blueprint.md",
        "Implement Harness Orchestration",
    )


def test_harness_start_rejects_heavy_as_deferred_phase1_scope(
    local_tmp_path: Path, monkeypatch
):
    repo_root = _make_fake_repo(local_tmp_path)
    monkeypatch.chdir(repo_root)

    result = runner.invoke(
        app,
        [
            "harness",
            "start",
            "--mode",
            "heavy",
            "--goal",
            "Heavy flow",
            "--source",
            "docs/spec.md",
        ],
    )

    assert result.exit_code != 0
    assert "heavy deferred to later phase" in _normalize(result.output).lower()
    assert not (repo_root / ".agent/artifacts/harness_heavy").exists()


def test_harness_advance_prints_exact_critic_launcher_when_draft_v1_is_ready(
    local_tmp_path: Path,
):
    repo_root = _make_fake_repo(local_tmp_path)
    job_id = "lite_20260425_demo"
    _seed_lite_artifacts(repo_root, job_id, state_stage="INIT")

    result = runner.invoke(
        app,
        ["harness", "advance", "--job", job_id, "--root", str(repo_root)],
    )

    assert result.exit_code == 0
    assert _normalize(result.output) == _expected_critic_launcher(job_id)


def test_harness_advance_prints_exact_synthesis_launcher_when_review_packet_is_ready(
    local_tmp_path: Path,
):
    repo_root = _make_fake_repo(local_tmp_path)
    job_id = "lite_20260425_demo"
    _seed_lite_artifacts(repo_root, job_id, review_ready=True, state_stage="INIT")

    result = runner.invoke(
        app,
        ["harness", "advance", "--job", job_id, "--root", str(repo_root)],
    )

    assert result.exit_code == 0
    assert _normalize(result.output) == _expected_synthesis_launcher(job_id)


def test_harness_advance_blocks_when_evidence_gate_lacks_structural_contract(
    local_tmp_path: Path,
):
    repo_root = _make_fake_repo(local_tmp_path)
    job_id = "lite_20260425_demo"
    _seed_lite_artifacts(
        repo_root,
        job_id,
        review_ready=True,
        candidate_ready=True,
        evidence_gate=_bad_evidence_gate(),
        state_stage="INIT",
    )

    result = runner.invoke(
        app,
        ["harness", "advance", "--job", job_id, "--root", str(repo_root)],
    )

    assert result.exit_code != 0
    assert "blocked" in _normalize(result.output).lower()
    assert "A#" in _normalize(result.output)


def test_harness_start_resolves_repo_root_from_subdirectory_cwd(
    local_tmp_path: Path, monkeypatch
):
    repo_root = _make_fake_repo(local_tmp_path)
    work_dir = repo_root / "nested" / "docs"
    work_dir.mkdir(parents=True)
    monkeypatch.chdir(work_dir)

    result = runner.invoke(
        app,
        [
            "harness",
            "start",
            "--mode",
            "lite",
            "--goal",
            "Nested start",
            "--source",
            "docs/spec.md",
        ],
    )

    assert result.exit_code == 0
    assert (repo_root / ".agent/artifacts/harness_lite").exists()


def test_harness_start_fails_closed_outside_repo_without_explicit_root(
    local_tmp_path: Path, monkeypatch
):
    outside = local_tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)

    result = runner.invoke(
        app,
        [
            "harness",
            "start",
            "--mode",
            "lite",
            "--goal",
            "Outside repo",
            "--source",
            "docs/spec.md",
        ],
    )

    assert result.exit_code != 0
    normalized = _normalize(result.output).lower()
    assert "repo" in normalized
    assert "--root" in normalized


def test_harness_start_accepts_explicit_root_when_repo_and_cwd_are_separated(
    local_tmp_path: Path, monkeypatch
):
    repo_root = _make_fake_repo(local_tmp_path)
    outside = local_tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)

    result = runner.invoke(
        app,
        [
            "harness",
            "start",
            "--mode",
            "lite",
            "--goal",
            "Separated root",
            "--source",
            "docs/spec.md",
            "--root",
            str(repo_root),
        ],
    )

    assert result.exit_code == 0
    assert (repo_root / ".agent/artifacts/harness_lite").exists()


def test_harness_status_recomputes_stage_from_artifacts_and_refreshes_stale_state_snapshot(
    local_tmp_path: Path,
):
    repo_root = _make_fake_repo(local_tmp_path)
    job_id = "lite_20260425_demo"
    artifact_dir = _seed_lite_artifacts(repo_root, job_id, state_stage="INIT")

    result = runner.invoke(
        app,
        ["harness", "status", "--job", job_id, "--root", str(repo_root)],
    )

    assert result.exit_code == 0
    assert "DRAFT_V1_READY" in _normalize(result.output)

    state = json.loads((artifact_dir / "state.json").read_text(encoding="utf-8"))
    assert state["derived_stage"] == "DRAFT_V1_READY"
    assert state["blockers"] == []
