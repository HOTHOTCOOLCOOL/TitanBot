from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.loop import AgentLoop
from nanobot.agent.task_tracker import TaskTracker, set_active_tracker


def _workspace() -> Path:
    root = Path(".pytest_tasktracker_transparency") / uuid4().hex
    (root / "memory").mkdir(parents=True)
    return root


def test_runtime_tracking_records_recent_steps_and_completed_status():
    workspace = _workspace()
    try:
        tracker = TaskTracker(workspace)
        stub = SimpleNamespace(
            task_tracker=tracker,
            _task_step_name_from_call=AgentLoop._task_step_name_from_call,
        )

        task_id = AgentLoop._track_request_start(
            stub,
            "请处理 Excel Book2 并生成摘要",
            "excel_book2_summary",
            "task",
        )
        AgentLoop._track_request_outcome(
            stub,
            task_id,
            tool_calls_with_args=[
                {"tool": "excel_actuator", "args": {"action": "list_sheets"}},
                {"tool": "excel_actuator", "args": {"action": "inspect_pivot"}},
                {"tool": "write_artifact", "args": {"path": "report.md"}},
            ],
            exit_kind="success",
            pending_review=False,
            final_content="报告已生成。",
        )

        task = tracker.get_active_task()
        assert task is not None
        assert task.status.value == "completed"
        assert len(task.steps) == 3
        assert task.steps[0].status == "completed"
        assert task.steps[-1].status == "completed"
        progress = tracker.get_progress(task.task_id)
        assert progress["progress_percent"] == 100
        assert progress["current_step"] == task.steps[-1].name
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_context_injection_emits_debug_log_and_progress_snippet():
    workspace = _workspace()
    sink_id = None
    log_messages: list[str] = []
    try:
        tracker = TaskTracker(workspace)
        stub = SimpleNamespace(
            task_tracker=tracker,
            _task_step_name_from_call=AgentLoop._task_step_name_from_call,
        )
        task_id = AgentLoop._track_request_start(
            stub,
            "请处理 Excel Book2 并生成摘要",
            "excel_book2_summary",
            "task",
        )
        AgentLoop._track_request_outcome(
            stub,
            task_id,
            tool_calls_with_args=[
                {"tool": "excel_actuator", "args": {"action": "list_sheets"}},
                {"tool": "excel_actuator", "args": {"action": "inspect_pivot"}},
                {"tool": "write_artifact", "args": {"path": "report.md"}},
            ],
            exit_kind="success",
            pending_review=False,
            final_content="报告已生成。",
        )
        set_active_tracker(tracker)

        sink_id = logger.add(log_messages.append, level="DEBUG", format="{message}")
        ctx = ContextBuilder(workspace, language="zh")
        messages = ctx.build_messages(
            [],
            "你刚才进行到哪一步了？",
            context_limit=120000,
            pre_fetched_rag=[],
            pre_fetched_kg="",
        )
        system_prompt = messages[0]["content"]

        assert "Active Task Tracker" in system_prompt
        assert "Progress" in system_prompt
        assert "100%" in system_prompt
        assert "Current Step" in system_prompt
        assert "write_artifact: report.md" in system_prompt
        assert any("L0: Injected TaskTracker status for" in msg for msg in log_messages)
    finally:
        if sink_id is not None:
            logger.remove(sink_id)
        set_active_tracker(tracker if False else None)  # type: ignore[arg-type]
        shutil.rmtree(workspace, ignore_errors=True)
