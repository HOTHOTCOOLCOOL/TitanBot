"""Cron service for scheduling agent tasks."""

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

from nanobot.cron.types import CronJob, CronJobState, CronPayload, CronSchedule, CronStore


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Compute next run time in ms."""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None
    
    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        # Next interval from now
        return now_ms + schedule.every_ms
    
    if schedule.kind == "cron" and schedule.expr:
        try:
            from croniter import croniter
            from zoneinfo import ZoneInfo
            # Use caller-provided reference time for deterministic scheduling
            base_time = now_ms / 1000
            tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
            base_dt = datetime.fromtimestamp(base_time, tz=tz)
            cron = croniter(schedule.expr, base_dt)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)
        except Exception:
            return None
    
    return None


class CronService:
    """Service for managing and executing scheduled jobs."""
    
    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None
    ):
        self.store_path = store_path
        self.on_job = on_job  # Callback to execute job, returns response text
        self._store: CronStore | None = None
        self._timer_task: asyncio.Task | None = None
        self._running = False
        # 执行记录文件：记录每个 job 的执行时间
        self._exec_log_path = store_path.parent / "executions.json"
        self._exec_log: dict[str, list[int]] = {}  # job_id -> list of execution timestamps
    
    def _load_exec_log(self) -> dict[str, list[int]]:
        """Load execution log from disk."""
        if self._exec_log_path.exists():
            try:
                data = json.loads(self._exec_log_path.read_text())
                return data.get("executions", {})
            except Exception:
                return {}
        return {}
    
    def _save_exec_log(self) -> None:
        """Save execution log to disk."""
        self._exec_log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"executions": self._exec_log}
        self._exec_log_path.write_text(json.dumps(data, indent=2))
    
    def _get_today_start_ms(self) -> int:
        """Get today's start timestamp in ms (midnight)."""
        import zoneinfo
        now = datetime.now()
        tz = zoneinfo.ZoneInfo("Asia/Shanghai")
        today = datetime(now.year, now.month, now.day, tzinfo=tz)
        return int(today.timestamp() * 1000)
    
    def _was_executed_today(self, job_id: str, scheduled_time_ms: int) -> bool:
        """Check if job was already executed today at the scheduled time."""
        today_start = self._get_today_start_ms()
        executions = self._exec_log.get(job_id, [])
        
        for exec_time in executions:
            # 如果执行时间在今天之内，认为已执行
            if exec_time >= today_start:
                return True
        return False
    
    def _record_execution(self, job_id: str) -> None:
        """Record a job execution."""
        if job_id not in self._exec_log:
            self._exec_log[job_id] = []
        self._exec_log[job_id].append(_now_ms())
        self._save_exec_log()
    
    def _load_store(self) -> CronStore:
        """Load jobs from disk."""
        if self._store:
            return self._store
        
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text())
                jobs = []
                for j in data.get("jobs", []):
                    jobs.append(CronJob(
                        id=j["id"],
                        name=j["name"],
                        enabled=j.get("enabled", True),
                        schedule=CronSchedule(
                            kind=j["schedule"]["kind"],
                            at_ms=j["schedule"].get("atMs"),
                            every_ms=j["schedule"].get("everyMs"),
                            expr=j["schedule"].get("expr"),
                            tz=j["schedule"].get("tz"),
                        ),
                        payload=CronPayload(
                            kind=j["payload"].get("kind", "agent_turn"),
                            message=j["payload"].get("message", ""),
                            deliver=j["payload"].get("deliver", False),
                            channel=j["payload"].get("channel"),
                            to=j["payload"].get("to"),
                        ),
                        state=CronJobState(
                            next_run_at_ms=j.get("state", {}).get("nextRunAtMs"),
                            last_run_at_ms=j.get("state", {}).get("lastRunAtMs"),
                            last_status=j.get("state", {}).get("lastStatus"),
                            last_error=j.get("state", {}).get("lastError"),
                        ),
                        created_at_ms=j.get("createdAtMs", 0),
                        updated_at_ms=j.get("updatedAtMs", 0),
                        delete_after_run=j.get("deleteAfterRun", False),
                    ))
                self._store = CronStore(jobs=jobs)
            except Exception as e:
                logger.warning(f"Failed to load cron store: {e}")
                self._store = CronStore()
        else:
            self._store = CronStore()
        
        return self._store
    
    def _save_store(self) -> None:
        """Save jobs to disk."""
        if not self._store:
            return
        
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "version": self._store.version,
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule": {
                        "kind": j.schedule.kind,
                        "atMs": j.schedule.at_ms,
                        "everyMs": j.schedule.every_ms,
                        "expr": j.schedule.expr,
                        "tz": j.schedule.tz,
                    },
                    "payload": {
                        "kind": j.payload.kind,
                        "message": j.payload.message,
                        "deliver": j.payload.deliver,
                        "channel": j.payload.channel,
                        "to": j.payload.to,
                    },
                    "state": {
                        "nextRunAtMs": j.state.next_run_at_ms,
                        "lastRunAtMs": j.state.last_run_at_ms,
                        "lastStatus": j.state.last_status,
                        "lastError": j.state.last_error,
                    },
                    "createdAtMs": j.created_at_ms,
                    "updatedAtMs": j.updated_at_ms,
                    "deleteAfterRun": j.delete_after_run,
                }
                for j in self._store.jobs
            ]
        }
        
        self.store_path.write_text(json.dumps(data, indent=2))
    
    async def start(self) -> None:
        """Start the cron service."""
        self._running = True
        self._store = None  # Force reload from disk
        self._load_store()
        self._exec_log = self._load_exec_log()  # 加载执行记录
        
        # Bug 2 fix: 先检查 missed jobs（使用当前存储的 next_run_at_ms）
        await self._run_missed_jobs()
        
        # 然后重新计算下次运行时间
        self._recompute_next_runs()
        
        self._save_store()
        self._arm_timer()
        logger.info(f"Cron service started with {len(self._store.jobs if self._store else [])} jobs")
    
    def _compute_today_run_time(self, schedule: CronSchedule) -> int | None:
        """计算今天应该执行的时间。返回今天第一个执行时间（无论是否已错过）。"""
        if schedule.kind != "cron" or not schedule.expr:
            return None
        
        try:
            from croniter import croniter
            from zoneinfo import ZoneInfo
            
            now = datetime.now()
            tz = ZoneInfo(schedule.tz) if schedule.tz else now.astimezone().tzinfo
            now_dt = now.astimezone(tz)
            
            # 获取今天开始的时间
            today_start = datetime(now_dt.year, now_dt.month, now_dt.day, tzinfo=tz)
            
            # 使用 croniter 获取今天的执行时间
            cron = croniter(schedule.expr, today_start)
            
            # 获取今天的第一个执行时间
            next_dt = cron.get_next(datetime)
            
            # 如果今天的已经全部错过，返回 None
            if next_dt.date() > today_start.date():
                return None
            
            # 返回今天第一个执行时间（无论是否已错过）
            return int(next_dt.timestamp() * 1000)
        except Exception:
            return None
    
    async def _run_missed_jobs(self) -> None:
        """Run jobs that were missed because the service was down.
        
        检查执行记录，避免重复执行同一天的 job。
        """
        if not self._store:
            return
        
        now = _now_ms()
        missed_jobs = []
        
        for job in self._store.jobs:
            if not job.enabled:
                continue
            
            if not job.state.next_run_at_ms:
                continue
            
            # 对于 cron job，需要计算今天应该执行的时间
            if job.schedule.kind == "cron":
                today_run_time = self._compute_today_run_time(job.schedule)
                
                if today_run_time is None:
                    # 今天的执行时间已经全部错过或还没到
                    continue
                
                # 如果当前时间 >= 今天应该执行的时间
                if now >= today_run_time:
                    # 检查今天是否已执行
                    if self._was_executed_today(job.id, today_run_time):
                        logger.info(f"Cron: job '{job.name}' already executed today, skipping")
                        continue
                    
                    missed_jobs.append(job)
                    logger.info(f"Cron: missed job '{job.name}' ({job.id}), scheduled at {datetime.fromtimestamp(today_run_time/1000)}")
            else:
                # 对于 other job types，使用存储的 next_run_at_ms
                if now >= job.state.next_run_at_ms:
                    missed_jobs.append(job)
                    logger.info(f"Cron: missed job '{job.name}' ({job.id}), scheduled at {datetime.fromtimestamp(job.state.next_run_at_ms/1000)}")
        
        # 执行所有错过的 jobs
        for job in missed_jobs:
            # 注意：_execute_job 中会调用 _record_execution
            # 更新下次运行时间（避免重复执行）
            job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
            await self._execute_job(job)
    
    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
    
    def _recompute_next_runs(self) -> None:
        """Recompute next run times for all enabled jobs."""
        if not self._store:
            return
        now = _now_ms()
        for job in self._store.jobs:
            if job.enabled:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
    
    def _get_next_wake_ms(self) -> int | None:
        """Get the earliest next run time across all jobs."""
        if not self._store:
            return None
        times = [j.state.next_run_at_ms for j in self._store.jobs 
                 if j.enabled and j.state.next_run_at_ms]
        return min(times) if times else None
    
    def _arm_timer(self) -> None:
        """Schedule the next timer tick."""
        if self._timer_task:
            self._timer_task.cancel()
        
        if not self._running:
            return
        
        # 修复: 即使没有 job，也要保持一个基础 timer 运行
        # 这样可以检测新添加的 job
        next_wake = self._get_next_wake_ms()
        
        if next_wake:
            # 有 job，按下次运行时间安排
            delay_ms = max(0, next_wake - _now_ms())
            delay_s = delay_ms / 1000
        else:
            # 没有 job，每 60 秒检查一次文件变化
            delay_s = 60
        
        async def tick():
            await asyncio.sleep(delay_s)
            if self._running:
                # 每次 tick 都重新加载 jobs（检测新添加的 job）
                self._load_store()
                await self._on_timer()
        
        self._timer_task = asyncio.create_task(tick())
        
        if not next_wake:
            logger.debug("Cron: no jobs, running background monitor (checking every 60s)")
    
    async def _on_timer(self) -> None:
        """Handle timer tick - run due jobs."""
        if not self._store:
            return
        
        now = _now_ms()
        due_jobs = [
            j for j in self._store.jobs
            if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
        ]
        
        for job in due_jobs:
            await self._execute_job(job)
        
        self._save_store()
        self._arm_timer()
    
    async def _execute_job(self, job: CronJob) -> None:
        """Execute a single job."""
        start_ms = _now_ms()
        logger.info(f"Cron: executing job '{job.name}' ({job.id})")
        
        try:
            response = None
            if self.on_job:
                response = await self.on_job(job)
            
            job.state.last_status = "ok"
            job.state.last_error = None
            logger.info(f"Cron: job '{job.name}' completed")
            
        except Exception as e:
            job.state.last_status = "error"
            job.state.last_error = str(e)
            logger.error(f"Cron: job '{job.name}' failed: {e}")
        
        job.state.last_run_at_ms = start_ms
        job.updated_at_ms = _now_ms()
        
        # 记录执行（用于防止重复执行）
        self._record_execution(job.id)
        
        # Handle one-shot jobs
        if job.schedule.kind == "at":
            if job.delete_after_run:
                self._store.jobs = [j for j in self._store.jobs if j.id != job.id]
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            # Compute next run
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())
    
    # ========== Public API ==========
    
    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        """List all jobs."""
        store = self._load_store()
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.state.next_run_at_ms or float('inf'))
    
    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool = False,
        channel: str | None = None,
        to: str | None = None,
        delete_after_run: bool = False,
    ) -> CronJob:
        """Add a new job."""
        store = self._load_store()
        now = _now_ms()
        
        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
            ),
            state=CronJobState(next_run_at_ms=_compute_next_run(schedule, now)),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )
        
        store.jobs.append(job)
        self._save_store()
        self._arm_timer()
        
        logger.info(f"Cron: added job '{name}' ({job.id})")
        return job
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        store = self._load_store()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before
        
        if removed:
            self._save_store()
            self._arm_timer()
            logger.info(f"Cron: removed job {job_id}")
        
        return removed
    
    def enable_job(self, job_id: str, enabled: bool = True) -> CronJob | None:
        """Enable or disable a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                job.enabled = enabled
                job.updated_at_ms = _now_ms()
                if enabled:
                    job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())
                else:
                    job.state.next_run_at_ms = None
                self._save_store()
                self._arm_timer()
                return job
        return None
    
    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually run a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                if not force and not job.enabled:
                    return False
                await self._execute_job(job)
                self._save_store()
                self._arm_timer()
                return True
        return False
    
    def status(self) -> dict:
        """Get service status."""
        store = self._load_store()
        return {
            "enabled": self._running,
            "jobs": len(store.jobs),
            "next_wake_at_ms": self._get_next_wake_ms(),
        }
