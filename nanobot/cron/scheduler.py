"""
Unified Scheduler Service - 统一调度服务

整合 CronService 和 HeartbeatService 到一个统一的事件循环中，
避免多个 Timer 相互干扰，提高可靠性。

设计原则：
1. 单一事件循环 - 避免多个 timer 相互干扰
2. 故障隔离 - 一个组件失败不影响其他组件
3. 可观测性 - 统一的日志和状态监控
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from nanobot.cron.types import CronJob, CronJobState, CronPayload, CronSchedule, CronStore


def _now_ms() -> int:
    return int(time.time() * 1000)


class TaskType(Enum):
    """任务类型"""
    CRON = "cron"
    HEARTBEAT = "heartbeat"
    ONCE = "once"


@dataclass
class ScheduledTask:
    """调度的任务"""
    id: str
    name: str
    task_type: TaskType
    
    # Cron 任务专用
    schedule: CronSchedule | None = None
    payload: CronPayload | None = None
    
    # 时间控制
    next_run_ms: int | None = None
    interval_ms: int | None = None  # for heartbeat
    
    # 回调
    callback: Callable[..., Coroutine] | None = None
    
    # 状态
    enabled: bool = True
    last_run_ms: int | None = None
    last_status: str | None = None
    last_error: str | None = None
    
    def should_run(self, now_ms: int) -> bool:
        """检查是否应该运行"""
        if not self.enabled:
            return False
        if self.next_run_ms is None:
            return False
        return now_ms >= self.next_run_ms
    
    def compute_next_run(self, now_ms: int) -> int | None:
        """计算下次运行时间"""
        if self.task_type == TaskType.HEARTBEAT and self.interval_ms:
            return now_ms + self.interval_ms
        
        if self.task_type == TaskType.CRON and self.schedule:
            return _compute_next_run(self.schedule, now_ms)
        
        return None


def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """计算下次运行时间"""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None
    
    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        return now_ms + schedule.every_ms
    
    if schedule.kind == "cron" and schedule.expr:
        try:
            from croniter import croniter
            from zoneinfo import ZoneInfo
            
            base_time = now_ms / 1000
            tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
            base_dt = datetime.fromtimestamp(base_time, tz=tz)
            cron = croniter(schedule.expr, base_dt)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)
        except Exception:
            return None
    
    return None


class UnifiedScheduler:
    """
    统一调度器
    
    将 Cron jobs 和 Heartbeat 整合到一个事件循环中：
    - 每秒检查一次所有任务
    - 自动执行到期的任务
    - 支持动态添加/删除任务
    """
    
    def __init__(
        self,
        cron_store_path: Path | None = None,
        heartbeat_interval_s: int = 30 * 60,  # 默认 30 分钟
    ):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._main_task: asyncio.Task | None = None
        
        # 心跳配置
        self._heartbeat_interval_s = heartbeat_interval_s
        self._heartbeat_callback: Callable[[str], Coroutine[Any, Any, str]] | None = None
        self._heartbeat_prompt = "Read HEARTBEAT.md in your workspace. If nothing needs attention, reply: HEARTBEAT_OK"
        
        # Cron 配置
        self._cron_store_path = cron_store_path
        self._cron_callback: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None
        self._cron_store: CronStore | None = None
        
        # 健康检查
        self._last_heartbeat_ms: int | None = None
        self._consecutive_failures: int = 0
    
    @property
    def cron_store_path(self) -> Path | None:
        return self._cron_store_path
    
    @cron_store_path.setter
    def cron_store_path(self, path: Path):
        """设置 cron store 路径并加载"""
        self._cron_store_path = path
        self._load_cron_jobs()
    
    def _load_cron_jobs(self):
        """从文件加载 cron jobs"""
        if not self._cron_store_path:
            return
        
        if self._cron_store_path.exists():
            try:
                data = json.loads(self._cron_store_path.read_text())
                jobs = []
                for j in data.get("jobs", []):
                    job = CronJob(
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
                    )
                    jobs.append(job)
                
                self._cron_store = CronStore(jobs=jobs)
                
                # 转换为内部任务
                now_ms = _now_ms()
                for job in jobs:
                    if job.enabled:
                        task = ScheduledTask(
                            id=f"cron_{job.id}",
                            name=job.name,
                            task_type=TaskType.CRON,
                            schedule=job.schedule,
                            payload=job.payload,
                            next_run_ms=job.state.next_run_at_ms or _compute_next_run(job.schedule, now_ms),
                            enabled=job.enabled,
                        )
                        self._tasks[task.id] = task
                
                logger.info(f"Loaded {len(jobs)} cron jobs from {self._cron_store_path}")
                
            except Exception as e:
                logger.error(f"Failed to load cron jobs: {e}")
                self._cron_store = CronStore()
    
    def _save_cron_jobs(self):
        """保存 cron jobs 到文件"""
        if not self._cron_store_path or not self._cron_store:
            return
        
        try:
            self._cron_store_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": self._cron_store.version,
                "jobs": []
            }
            
            for task in self._tasks.values():
                if task.task_type != TaskType.CRON:
                    continue
                
                job_data = {
                    "id": task.id.replace("cron_", ""),
                    "name": task.name,
                    "enabled": task.enabled,
                    "schedule": {
                        "kind": task.schedule.kind if task.schedule else "every",
                        "atMs": task.schedule.at_ms if task.schedule else None,
                        "everyMs": task.schedule.every_ms if task.schedule else None,
                        "expr": task.schedule.expr if task.schedule else None,
                        "tz": task.schedule.tz if task.schedule else None,
                    },
                    "payload": {
                        "kind": task.payload.kind if task.payload else "agent_turn",
                        "message": task.payload.message if task.payload else "",
                        "deliver": task.payload.deliver if task.payload else False,
                        "channel": task.payload.channel if task.payload else None,
                        "to": task.payload.to if task.payload else None,
                    },
                    "state": {
                        "nextRunAtMs": task.next_run_ms,
                        "lastRunAtMs": task.last_run_ms,
                        "lastStatus": task.last_status,
                        "lastError": task.last_error,
                    },
                    "createdAtMs": 0,
                    "updatedAtMs": _now_ms(),
                    "deleteAfterRun": False,
                }
                data["jobs"].append(job_data)
            
            self._cron_store_path.write_text(json.dumps(data, indent=2))
            
        except Exception as e:
            logger.error(f"Failed to save cron jobs: {e}")
    
    # ========== 心跳管理 ==========
    
    def set_heartbeat_callback(self, callback: Callable[[str], Coroutine[Any, Any, str]]):
        """设置心跳回调"""
        self._heartbeat_callback = callback
    
    def _setup_heartbeat(self):
        """设置心跳任务"""
        if not self._heartbeat_callback:
            return
        
        now_ms = _now_ms()
        task = ScheduledTask(
            id="heartbeat",
            name="heartbeat",
            task_type=TaskType.HEARTBEAT,
            interval_ms=self._heartbeat_interval_s * 1000,
            next_run_ms=now_ms + self._heartbeat_interval_s * 1000,
            callback=self._heartbeat_callback,
            enabled=True,
        )
        self._tasks["heartbeat"] = task
        logger.info(f"Heartbeat scheduled every {self._heartbeat_interval_s}s")
    
    # ========== Cron 管理 ==========
    
    def set_cron_callback(self, callback: Callable[[CronJob], Coroutine[Any, Any, str | None]]):
        """设置 cron 回调"""
        self._cron_callback = callback
    
    def reload_cron_jobs(self):
        """重新加载 cron jobs"""
        self._load_cron_jobs()
    
    # ========== 生命周期 ==========
    
    async def start(self) -> None:
        """启动统一调度器"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        
        # 设置心跳
        if self._heartbeat_callback:
            self._setup_heartbeat()
        
        # 加载 cron jobs
        if self._cron_store_path:
            self._load_cron_jobs()
        
        # 启动主循环
        self._main_task = asyncio.create_task(self._run_loop())
        
        logger.info(f"Unified scheduler started with {len(self._tasks)} tasks")
    
    async def stop(self) -> None:
        """停止统一调度器"""
        self._running = False
        
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Unified scheduler stopped")
    
    async def _run_loop(self) -> None:
        """主循环 - 每秒检查所有任务"""
        while self._running:
            try:
                now_ms = _now_ms()
                
                # 检查并执行到期的任务
                tasks_to_run = [
                    task for task in self._tasks.values()
                    if task.should_run(now_ms)
                ]
                
                for task in tasks_to_run:
                    await self._execute_task(task)
                
                # 保存 cron 状态
                if tasks_to_run:
                    self._save_cron_jobs()
                
                # 健康检查
                await self._health_check(now_ms)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            await asyncio.sleep(1)  # 每秒检查
    
    async def _execute_task(self, task: ScheduledTask):
        """执行单个任务"""
        now_ms = _now_ms()
        task.last_run_ms = now_ms
        task.last_status = "running"
        
        logger.info(f"Scheduler: executing task '{task.name}' ({task.task_type.value})")
        
        try:
            if task.task_type == TaskType.HEARTBEAT:
                if task.callback:
                    response = await task.callback(self._heartbeat_prompt)
                    if "HEARTBEAT_OK" in response.upper().replace("_", ""):
                        logger.debug("Heartbeat: OK (no action needed)")
                    else:
                        logger.info("Heartbeat: task completed")
                task.last_status = "ok"
                task.last_error = None
                self._consecutive_failures = 0
            
            elif task.task_type == TaskType.CRON:
                if self._cron_callback and task.payload:
                    # 构建 CronJob 对象
                    job = CronJob(
                        id=task.id.replace("cron_", ""),
                        name=task.name,
                        enabled=True,
                        schedule=task.schedule,
                        payload=task.payload,
                        state=CronJobState(next_run_at_ms=task.next_run_ms),
                        created_at_ms=0,
                        updated_at_ms=0,
                    )
                    await self._cron_callback(job)
                task.last_status = "ok"
                task.last_error = None
            
            logger.info(f"Scheduler: task '{task.name}' completed")
            
        except Exception as e:
            task.last_status = "error"
            task.last_error = str(e)
            logger.error(f"Scheduler: task '{task.name}' failed: {e}")
            self._consecutive_failures += 1
        
        # 计算下次运行时间
        task.next_run_ms = task.compute_next_run(_now_ms())
    
    async def _health_check(self, now_ms: int):
        """健康检查"""
        # 检查心跳是否超时
        if "heartbeat" in self._tasks:
            hb = self._tasks["heartbeat"]
            if hb.last_run_ms:
                elapsed_s = (now_ms - hb.last_run_ms) / 1000
                if elapsed_s > self._heartbeat_interval_s * 3:
                    logger.warning(f"Heartbeat timeout: {elapsed_s}s since last run")
        
        # 检查连续失败
        if self._consecutive_failures > 5:
            logger.error(f"Scheduler health: {self._consecutive_failures} consecutive failures")
    
    # ========== 状态 ==========
    
    def status(self) -> dict:
        """获取状态"""
        tasks_info = []
        for task in self._tasks.values():
            tasks_info.append({
                "id": task.id,
                "name": task.name,
                "type": task.task_type.value,
                "enabled": task.enabled,
                "next_run_ms": task.next_run_ms,
                "last_run_ms": task.last_run_ms,
                "last_status": task.last_status,
            })
        
        return {
            "running": self._running,
            "tasks": len(self._tasks),
            "task_details": tasks_info,
        }
    
    def list_tasks(self) -> list[dict]:
        """列出所有任务"""
        return [
            {
                "id": task.id,
                "name": task.name,
                "type": task.task_type.value,
                "enabled": task.enabled,
                "next_run_ms": task.next_run_ms,
            }
            for task in self._tasks.values()
        ]
