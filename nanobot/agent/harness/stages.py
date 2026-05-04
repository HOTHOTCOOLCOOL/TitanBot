"""Artifact-derived stage computation for the Phase 1 lite-only harness flow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nanobot.agent.harness.scaffold import STUB_SENTINEL

PASS_FAIL_BLOCKED_RE = re.compile(r"(?mi)^\s*(PASS|FAIL|BLOCKED)\s*$")

PROBLEM_STATEMENT_SECTIONS = (
    "Job ID",
    "Goal",
    "Source Context",
    "In Scope",
    "Out of Scope",
    "Expected Output",
)
BASELINE_SECTIONS = (
    "Claim / Evidence / Status",
    "Source of Truth Files",
    "Unknowns",
    "Questions the Critic Must Attack",
)
DRAFT_SECTIONS = (
    "当前方案摘要",
    "关键 trade-off",
    "风险与假设",
    "仍待验证的点",
)
REVIEW_PACKET_SECTIONS = (
    "Findings",
    "Must Keep",
    "Weak Claims / Unverified Claims",
    "Acceptance Checklist",
)
CANDIDATE_SECTIONS = (
    "Adopted Criticisms",
    "Rejected Criticisms",
    "Final Candidate",
    "Residual Risks",
    "Evidence Plan",
)
EVIDENCE_GATE_SECTIONS = ("A#", "Status", "Evidence", "Meaning")


@dataclass(frozen=True)
class ArtifactStatus:
    state: str
    blockers: list[str]

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    @property
    def pending(self) -> bool:
        return self.state in {"missing", "stub"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _missing_sections(text: str, required_sections: tuple[str, ...]) -> list[str]:
    return [section for section in required_sections if section not in text]


def _check_artifact(path: Path, required_sections: tuple[str, ...] = ()) -> ArtifactStatus:
    if not path.exists():
        return ArtifactStatus("missing", ["missing file"])

    text = _read_text(path)
    if not text.strip():
        return ArtifactStatus("missing", ["empty file"])
    if STUB_SENTINEL in text:
        return ArtifactStatus("stub", ["still contains scaffold stub"])

    missing_sections = _missing_sections(text, required_sections)
    if missing_sections:
        joined = " / ".join(missing_sections)
        return ArtifactStatus("invalid", [f"missing required sections: {joined}"])

    return ArtifactStatus("ready", [])


def _check_evidence_gate(path: Path) -> tuple[ArtifactStatus, str | None]:
    status = _check_artifact(path, EVIDENCE_GATE_SECTIONS)
    if not status.ready:
        return status, None

    text = _read_text(path)
    match = PASS_FAIL_BLOCKED_RE.search(text)
    if not match:
        return (
            ArtifactStatus("invalid", ["missing required decision line: PASS / FAIL / BLOCKED"]),
            None,
        )

    return status, match.group(1).upper()


def _serialize(status: ArtifactStatus) -> dict[str, object]:
    return {"state": status.state, "ready": status.ready, "blockers": list(status.blockers)}


def _prefix_blockers(filename: str, blockers: list[str]) -> list[str]:
    return [f"{filename}: {blocker}" for blocker in blockers]


def derive_lite_state(artifact_dir: Path) -> dict[str, object]:
    """Compute the current lite harness stage from artifact truth on disk."""
    problem = _check_artifact(artifact_dir / "problem_statement.md", PROBLEM_STATEMENT_SECTIONS)
    baseline = _check_artifact(artifact_dir / "baseline.md", BASELINE_SECTIONS)
    draft = _check_artifact(artifact_dir / "draft_v1.md", DRAFT_SECTIONS)
    review = _check_artifact(artifact_dir / "review_packet.md", REVIEW_PACKET_SECTIONS)
    candidate = _check_artifact(artifact_dir / "candidate.md", CANDIDATE_SECTIONS)
    evidence_gate, gate_result = _check_evidence_gate(artifact_dir / "evidence_gate.md")

    artifacts_status = {
        "problem_statement.md": _serialize(problem),
        "baseline.md": _serialize(baseline),
        "draft_v1.md": _serialize(draft),
        "review_packet.md": _serialize(review),
        "candidate.md": _serialize(candidate),
        "evidence_gate.md": _serialize(evidence_gate),
    }

    derived_stage = "INIT"
    blockers: list[str] = []
    next_launcher_key: str | None = None

    if not problem.ready:
        blockers = _prefix_blockers("problem_statement.md", problem.blockers)
    elif not baseline.ready:
        blockers = _prefix_blockers("baseline.md", baseline.blockers)
    elif not draft.ready:
        derived_stage = "BASELINE_READY"
        blockers = _prefix_blockers("draft_v1.md", draft.blockers)
    elif not review.ready:
        derived_stage = "DRAFT_V1_READY"
        if review.pending:
            next_launcher_key = "critic"
        else:
            blockers = _prefix_blockers("review_packet.md", review.blockers)
    elif not candidate.ready:
        derived_stage = "REVIEW_PACKET_READY"
        if candidate.pending:
            next_launcher_key = "synthesis"
        else:
            blockers = _prefix_blockers("candidate.md", candidate.blockers)
    elif not evidence_gate.ready:
        derived_stage = "CANDIDATE_READY"
        blockers = _prefix_blockers("evidence_gate.md", evidence_gate.blockers)
    elif gate_result == "PASS":
        derived_stage = "DONE"
    else:
        derived_stage = "EVIDENCE_GATE_READY"
        blockers = [f"evidence_gate.md decision is {gate_result}"]

    return {
        "derived_stage": derived_stage,
        "blockers": blockers,
        "next_launcher_key": next_launcher_key,
        "gate_result": gate_result,
        "artifacts_status": artifacts_status,
    }
