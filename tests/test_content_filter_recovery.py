from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from loguru import logger

from nanobot.cron.service import CronService, _now_ms
from nanobot.cron.types import CronSchedule
from nanobot.utils.exceptions import AzureContentFilterException


@pytest.fixture
def content_filter_workspace():
    root = Path(".pytest_content_filter_recovery") / uuid4().hex
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_cron_content_filter_becomes_fatal_and_stops_retry(content_filter_workspace):
    store_path = content_filter_workspace / "cron" / "jobs.json"
    log_messages: list[str] = []
    notifications: list[tuple[str, str]] = []
    callback_calls = 0

    sink_id = logger.add(log_messages.append, level="DEBUG", format="{message}")

    try:
        async def on_job(_job):
            nonlocal callback_calls
            callback_calls += 1
            raise AzureContentFilterException("Synthetic Azure content_filter")

        async def on_notify(job_name: str, error_msg: str) -> None:
            notifications.append((job_name, error_msg))

        service = CronService(
            store_path,
            on_job=on_job,
            notification_callback=on_notify,
        )

        job = service.add_job(
            name="content-filter-probe",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="Synthetic content-filter probe",
        )
        job.state.next_run_at_ms = _now_ms() - 1
        service._save_store()

        await service._on_timer()

        assert callback_calls == 1
        assert job.enabled is False
        assert job.state.last_status == "error_fatal"
        assert job.state.next_run_at_ms is None
        assert notifications
        assert "Azure Content Filter" in notifications[0][1]
        assert any(
            "Cron: job 'content-filter-probe' reached fatal error state (Content Filter)"
            in msg
            for msg in log_messages
        )

        await service._on_timer()
        assert callback_calls == 1

        reloaded = CronService(store_path).list_jobs(include_disabled=True)[0]
        assert reloaded.enabled is False
        assert reloaded.state.last_status == "error_fatal"
        assert reloaded.state.next_run_at_ms is None
    finally:
        logger.remove(sink_id)
