"""Artifact scaffolding for the Phase 1 lite-only harness workflow."""

from __future__ import annotations

from pathlib import Path

from nanobot.agent.harness.job import utc_now_iso, write_state

STUB_SENTINEL = "<!-- HARNESS:STUB -->"
LITE_ARTIFACT_FILENAMES = (
    "problem_statement.md",
    "baseline.md",
    "draft_v1.md",
    "review_packet.md",
    "candidate.md",
    "evidence_gate.md",
    "state.json",
)


def artifact_rel_dir(job_id: str) -> str:
    return f".agent/artifacts/harness_lite/{job_id}"


def artifact_dir_for_job(repo_root: Path, job_id: str) -> Path:
    return repo_root / ".agent" / "artifacts" / "harness_lite" / job_id


def _problem_statement_template(job_id: str, source: str, goal: str) -> str:
    return (
        "# Problem Statement\n\n"
        f"{STUB_SENTINEL}\n\n"
        "Job ID\n"
        f"{job_id}\n\n"
        "Goal\n"
        f"{goal}\n\n"
        "Source Context\n"
        f"{source}\n\n"
        "In Scope\n"
        "- lite-only orchestration\n\n"
        "Out of Scope\n"
        "- heavy mode\n\n"
        "Expected Output\n"
        "- candidate.md\n"
        "- evidence_gate.md\n"
    )


def _baseline_template() -> str:
    return (
        "# Baseline\n\n"
        f"{STUB_SENTINEL}\n\n"
        "Claim / Evidence / Status\n\n"
        "Source of Truth Files\n"
        "- .agent/workflows/harness_lite.md\n\n"
        "Unknowns\n"
        "- <fill me>\n\n"
        "Questions the Critic Must Attack\n"
        "- <fill me>\n"
    )


def _draft_template() -> str:
    return (
        "# Draft V1\n\n"
        f"{STUB_SENTINEL}\n\n"
        "当前方案摘要\n"
        "- <fill me>\n\n"
        "关键 trade-off\n"
        "- <fill me>\n\n"
        "风险与假设\n"
        "- <fill me>\n\n"
        "仍待验证的点\n"
        "- <fill me>\n"
    )


def _review_packet_template() -> str:
    return (
        "# Review Packet\n\n"
        f"{STUB_SENTINEL}\n\n"
        "Findings\n"
        "- <fill me>\n\n"
        "Must Keep\n"
        "- <fill me>\n\n"
        "Weak Claims / Unverified Claims\n"
        "- <fill me>\n\n"
        "Acceptance Checklist\n"
        "| A# | Claim | Evidence Method | Expected Result | If Fail |\n"
        "| --- | --- | --- | --- | --- |\n"
    )


def _candidate_template() -> str:
    return (
        "# Candidate\n\n"
        f"{STUB_SENTINEL}\n\n"
        "Adopted Criticisms\n"
        "- <fill me>\n\n"
        "Rejected Criticisms\n"
        "- <fill me>\n\n"
        "Final Candidate\n"
        "- <fill me>\n\n"
        "Residual Risks\n"
        "- <fill me>\n\n"
        "Evidence Plan\n"
        "- <fill me>\n"
    )


def _evidence_gate_template() -> str:
    return (
        "# Evidence Gate\n\n"
        f"{STUB_SENTINEL}\n\n"
        "A# / Status / Evidence / Meaning\n\n"
        "| A# | Status | Evidence | Meaning |\n"
        "| --- | --- | --- | --- |\n\n"
        "BLOCKED\n\n"
        "Decision\n"
        "<fill me>\n"
    )


def scaffold_lite_job(repo_root: Path, job_id: str, source: str, goal: str) -> Path:
    """Create the Phase 1 lite-only artifact scaffold and initial snapshot."""
    artifact_dir = artifact_dir_for_job(repo_root, job_id)
    artifact_dir.mkdir(parents=True, exist_ok=False)

    templates = {
        "problem_statement.md": _problem_statement_template(job_id, source, goal),
        "baseline.md": _baseline_template(),
        "draft_v1.md": _draft_template(),
        "review_packet.md": _review_packet_template(),
        "candidate.md": _candidate_template(),
        "evidence_gate.md": _evidence_gate_template(),
    }

    for filename, content in templates.items():
        (artifact_dir / filename).write_text(content, encoding="utf-8")

    write_state(
        artifact_dir / "state.json",
        {
            "job_id": job_id,
            "mode": "lite",
            "goal": goal,
            "source": source,
            "artifact_dir": artifact_rel_dir(job_id),
            "created_at": utc_now_iso(),
            "last_checked_at": utc_now_iso(),
            "derived_stage": "INIT",
            "blockers": [
                "problem_statement.md is not ready",
                "baseline.md is not ready",
                "draft_v1.md is not ready",
            ],
        },
    )

    return artifact_dir
