import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTE_PHASE_WORKFLOW = REPO_ROOT / ".agent" / "workflows" / "execute_phase.md"
PHASE65_JOB_DIR = (
    REPO_ROOT
    / ".agent"
    / "artifacts"
    / "execute_phase"
    / "phase_20260425_harness_orchestration_phase1_mvp"
)
REASONING_JOB_DIR = (
    REPO_ROOT
    / ".agent"
    / "artifacts"
    / "execute_phase"
    / "job_20260503_trs_reasoning_skill"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains_all(text: str, required: tuple[str, ...]) -> None:
    missing = [item for item in required if item not in text]
    assert not missing, f"missing required content: {missing}"


def _extract_task_ids(task_text: str) -> list[str]:
    return re.findall(r"- \[[ xX]\] (T\d+)\b", task_text)


def test_execute_phase_workflow_keeps_artifact_first_launchers_and_rework_contract():
    workflow_text = _read(EXECUTE_PHASE_WORKFLOW)

    _assert_contains_all(
        workflow_text,
        (
            "`.agent/artifacts/execute_phase/<job_id>/codex_handoff.md`",
            "Artifact Registry",
            "Allowed Write Set",
            "Forbidden Write Set",
            "`.agent/artifacts/execute_phase/<job_id>/codex_result.md`",
            "`.agent/artifacts/execute_phase/<job_id>/codex_feedback.md`",
            "原样发送",
            "blocked",
        ),
    )
    assert "转告 Codex" not in workflow_text


def test_execute_phase_workflow_explicitly_supports_multiple_jobs_per_phase():
    workflow_text = _read(EXECUTE_PHASE_WORKFLOW)

    _assert_contains_all(
        workflow_text,
        (
            "同一 Phase 可以并行拆出多个 `job_id`",
            "回执、返工与验收都必须继续按各自 `job_id` 独立维护",
            "不要依赖“最新 Artifact”去猜当前目标 job",
        ),
    )


def test_phase65_job_handoff_has_required_execute_phase_contract_sections():
    implementation_plan = PHASE65_JOB_DIR / "implementation_plan.md"
    task = PHASE65_JOB_DIR / "task.md"
    handoff = PHASE65_JOB_DIR / "codex_handoff.md"

    assert implementation_plan.exists()
    assert task.exists()
    assert handoff.exists()

    handoff_text = _read(handoff)

    _assert_contains_all(
        handoff_text,
        (
            "Artifact Registry",
            "Codex Startup Checklist",
            "Goal",
            "Allowed Write Set",
            "Forbidden Write Set",
            "Red Tests to Satisfy",
            "Green Exit Criteria",
            "Stop Conditions",
            "Return Contract",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/implementation_plan.md",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/task.md",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_handoff.md",
        ),
    )


def test_phase65_job_result_reads_core_artifacts_and_covers_every_task():
    task_text = _read(PHASE65_JOB_DIR / "task.md")
    result_text = _read(PHASE65_JOB_DIR / "codex_result.md")
    task_ids = _extract_task_ids(task_text)

    assert task_ids

    _assert_contains_all(
        result_text,
        (
            "Artifacts Read",
            "Task Coverage",
            "Deviation from Plan",
            "Suggested Validation Steps",
            "Suggested Review Focus",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_handoff.md",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/implementation_plan.md",
            ".agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/task.md",
        ),
    )

    for task_id in task_ids:
        assert task_id in result_text, f"missing task coverage for {task_id}"


def test_phase65_job_feedback_is_structured_for_rework_instead_of_free_form_relay():
    feedback_text = _read(PHASE65_JOB_DIR / "codex_feedback.md")

    _assert_contains_all(
        feedback_text,
        (
            "Failed Commands",
            "Key Errors",
            "Severity A",
            "Severity B",
            "Must Fix Files",
            "Boundary Reminder",
            "Return Instructions",
            "Allowed Write Set",
            "Forbidden Write Set",
            "codex_result.md",
        ),
    )


def test_reasoning_skill_execute_phase_example_keeps_result_task_coverage_in_sync():
    task_text = _read(REASONING_JOB_DIR / "task.md")
    result_text = _read(REASONING_JOB_DIR / "codex_result.md")
    task_ids = _extract_task_ids(task_text)

    assert task_ids

    _assert_contains_all(
        result_text,
        (
            "Artifacts Read",
            "Task Coverage",
            "Deviation from Plan",
            "Suggested Validation Steps",
            "Suggested Review Focus",
            "tests/test_phase24_knowledge_graph.py",
            "tests/test_context_knowledge.py",
        ),
    )

    for task_id in task_ids:
        assert task_id in result_text, f"missing task coverage for {task_id}"
