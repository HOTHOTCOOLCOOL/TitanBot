r"""Manual verification script for Phase 59 TaskTracker transparency.

Run from repo root:
    .\.venv\Scripts\python.exe tests\verify_phase59_tasktracker_transparency.py

Optional:
    .\.venv\Scripts\python.exe tests\verify_phase59_tasktracker_transparency.py --keep-artifacts
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from loguru import logger

sys.path.insert(0, ".")

from nanobot.agent.context import ContextBuilder
from nanobot.agent.loop import AgentLoop
from nanobot.agent.task_tracker import TaskTracker, set_active_tracker


def main() -> None:
    root = Path(".phase59_tasktracker_probe") / uuid4().hex
    (root / "memory").mkdir(parents=True)
    keep_artifacts = "--keep-artifacts" in sys.argv
    tracker = TaskTracker(root)

    stub = SimpleNamespace(
        task_tracker=tracker,
        _task_step_name_from_call=AgentLoop._task_step_name_from_call,
    )

    task_id = AgentLoop._track_request_start(
        stub,
        "请用 excel_actuator 处理 Excel Book2：先读取工作表，再检查 pivot/chart，最后输出简短报告。",
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

    log_messages: list[str] = []
    sink_id = logger.add(log_messages.append, level="DEBUG", format="{message}")
    set_active_tracker(tracker)

    try:
        ctx = ContextBuilder(root, language="zh")
        messages = ctx.build_messages(
            [],
            "你刚才进行到哪一步了？",
            context_limit=120000,
            pre_fetched_rag=[],
            pre_fetched_kg="",
        )
        system_prompt = messages[0]["content"]

        checks = [
            ("tasktracker log emitted", any("L0: Injected TaskTracker status for" in msg for msg in log_messages)),
            ("prompt contains tracker block", "Active Task Tracker" in system_prompt),
            ("prompt contains progress", "Progress" in system_prompt and "100%" in system_prompt),
            ("prompt contains current step", "Current Step" in system_prompt),
            ("prompt contains latest step", "write_artifact: report.md" in system_prompt),
        ]

        print("=== Phase 59 TaskTracker Transparency Probe ===")
        print(f"Artifact dir: {root}")
        for label, ok in checks:
            print(f"- {label}: {'PASS' if ok else 'FAIL'}")

        print("\nRelevant DEBUG lines:")
        matched = [msg for msg in log_messages if "TaskTracker" in msg]
        if matched:
            for msg in matched:
                print(f"  {msg}")
        else:
            print("  <none>")

        print("\nInjected prompt snippet:")
        marker = "## 📋 Active Task Tracker"
        if marker in system_prompt:
            snippet = system_prompt[system_prompt.index(marker): system_prompt.index(marker) + 320]
            print(snippet.encode("ascii", errors="backslashreplace").decode("ascii"))
        else:
            print("<tracker block missing>")

        if any(not ok for _, ok in checks):
            failed = [label for label, ok in checks if not ok]
            raise AssertionError("Probe failed: " + ", ".join(failed))

        print("\nResult: PASS")
        print("This validates the TaskTracker L0 transparency layer and its runtime-fed step summary.")
        if keep_artifacts:
            print(f"Artifacts kept at: {root}")
    finally:
        logger.remove(sink_id)
        set_active_tracker(None)  # type: ignore[arg-type]
        if not keep_artifacts:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
