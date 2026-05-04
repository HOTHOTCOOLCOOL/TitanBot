r"""Manual verification script for Phase 62 Cron content-filter fuse.

Run from the repo root:
    .\.venv\Scripts\python.exe tests\verify_phase62_content_filter_fuse.py

What it verifies:
1. A cron job that hits AzureContentFilterException is marked error_fatal.
2. The job is disabled immediately.
3. The next run is cleared, so the timer does not retry it.
4. The expected fatal log line is emitted.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from loguru import logger

sys.path.insert(0, ".")

from nanobot.cron.service import CronService, _now_ms
from nanobot.cron.types import CronSchedule
from nanobot.utils.exceptions import AzureContentFilterException


async def main() -> None:
    root = Path(".phase62_content_filter_probe") / uuid4().hex
    store_path = root / "cron" / "jobs.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    keep_artifacts = "--keep-artifacts" in sys.argv

    log_messages: list[str] = []
    notifications: list[tuple[str, str]] = []
    callback_calls = 0

    sink_id = logger.add(log_messages.append, level="DEBUG", format="{message}")

    try:
        async def on_job(_job):
            nonlocal callback_calls
            callback_calls += 1
            raise AzureContentFilterException(
                "Synthetic Azure content_filter from Phase 62 probe"
            )

        async def on_notify(job_name: str, error_msg: str) -> None:
            notifications.append((job_name, error_msg))

        service = CronService(
            store_path,
            on_job=on_job,
            notification_callback=on_notify,
        )

        job = service.add_job(
            name="Phase62 Content Filter Fuse Probe",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="Synthetic content filter probe",
        )
        job.state.next_run_at_ms = _now_ms() - 1
        service._save_store()

        await service._on_timer()
        first_snapshot = service.list_jobs(include_disabled=True)[0]

        await service._on_timer()
        second_snapshot = service.list_jobs(include_disabled=True)[0]

        persisted = json.loads(store_path.read_text(encoding="utf-8"))
        persisted_job = persisted["jobs"][0]

        checks = [
            (
                "fatal log emitted",
                any(
                    "Cron: job 'Phase62 Content Filter Fuse Probe' reached fatal error state (Content Filter)"
                    in msg
                    for msg in log_messages
                ),
            ),
            ("job callback ran once", callback_calls == 1),
            ("job disabled", first_snapshot.enabled is False),
            ("status is error_fatal", first_snapshot.state.last_status == "error_fatal"),
            ("next run cleared", first_snapshot.state.next_run_at_ms is None),
            ("notification sent", len(notifications) == 1 and "Azure Content Filter" in notifications[0][1]),
            ("second timer tick did not retry", second_snapshot.state.retry_count == 0 and callback_calls == 1),
            ("persisted enabled=false", persisted_job["enabled"] is False),
            ("persisted lastStatus=error_fatal", persisted_job["state"]["lastStatus"] == "error_fatal"),
            ("persisted nextRunAtMs=null", persisted_job["state"]["nextRunAtMs"] is None),
        ]

        print("=== Phase 62 Content Filter Fuse Probe ===")
        print(f"Artifact dir: {root}")
        for label, ok in checks:
            print(f"- {label}: {'PASS' if ok else 'FAIL'}")

        print("\nCaptured notification:")
        if notifications:
            print(f"  job={notifications[0][0]}")
            print(f"  msg={notifications[0][1]}")
        else:
            print("  <none>")

        print("\nPersisted job state:")
        state = persisted_job["state"]
        print(f"  enabled={persisted_job['enabled']}")
        print(f"  lastStatus={state['lastStatus']}")
        print(f"  nextRunAtMs={state['nextRunAtMs']}")
        print(f"  lastError={state['lastError']}")

        fatal_lines = [
            msg for msg in log_messages if "Content Filter" in msg or "fatal error state" in msg
        ]
        print("\nRelevant log lines:")
        if fatal_lines:
            for line in fatal_lines:
                print(f"  {line}")
        else:
            print("  <none>")

        failed = [label for label, ok in checks if not ok]
        if failed:
            raise AssertionError("Probe failed: " + ", ".join(failed))

        print("\nResult: PASS")
        print("This validates the backend Cron fuse path, not just front-door refusal.")
        if keep_artifacts:
            print(f"Artifacts kept at: {root}")
    finally:
        logger.remove(sink_id)
        if not keep_artifacts:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
