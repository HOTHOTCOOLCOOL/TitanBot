"""
任务状态追踪器 - Task Tracker

负责追踪每个任务的完整生命周期：
- created → planning → running → pending_review → completed/failed/cancelled
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(Enum):
    """任务状态枚举"""
    CREATED = "created"           # 刚创建
    PLANNING = "planning"        # 规划中（分析知识库）
    RUNNING = "running"          # 执行中
    PENDING_REVIEW = "pending_review"  # 等待用户确认
    COMPLETED = "completed"      # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 取消


class Step:
    """任务步骤"""
    def __init__(
        self,
        step_id: int,
        name: str,
        description: str = "",
        tool_name: str = "",
        params: dict = None,
    ):
        self.step_id = step_id
        self.name = name
        self.description = description
        self.tool_name = tool_name
        self.params = params or {}
        self.status = "pending"  # pending, running, completed, failed
        self.result = ""
        self.start_time = None
        self.end_time = None
    
    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "tool_name": self.tool_name,
            "params": self.params,
            "status": self.status,
            "result": self.result,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Step":
        step = cls(
            step_id=data["step_id"],
            name=data["name"],
            description=data.get("description", ""),
            tool_name=data.get("tool_name", ""),
            params=data.get("params", {}),
        )
        step.status = data.get("status", "pending")
        step.result = data.get("result", "")
        return step


class TrackedTask:
    """被追踪的任务"""
    
    def __init__(
        self,
        task_id: str,
        key: str,
        user_request: str,
    ):
        self.task_id = task_id
        self.key = key  # 任务类型标识
        self.user_request = user_request
        self.status = TaskStatus.CREATED
        
        # 规划阶段
        self.analyzed_from = ""  # 基于哪个历史任务
        self.steps: list[Step] = []
        self.params = {}
        
        # 执行阶段
        self.current_step = 0
        self.step_results: list[dict] = []
        
        # 完成阶段
        self.result_summary = ""
        self.knowledge_to_save = {}
        
        # 时间戳
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.start_time = None
        self.end_time = None
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "key": self.key,
            "user_request": self.user_request,
            "status": self.status.value,
            "analyzed_from": self.analyzed_from,
            "steps": [s.to_dict() for s in self.steps],
            "params": self.params,
            "current_step": self.current_step,
            "step_results": self.step_results,
            "result_summary": self.result_summary,
            "knowledge_to_save": self.knowledge_to_save,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TrackedTask":
        task = cls(
            task_id=data["task_id"],
            key=data["key"],
            user_request=data["user_request"],
        )
        task.status = TaskStatus(data.get("status", "created"))
        task.analyzed_from = data.get("analyzed_from", "")
        task.steps = [Step.from_dict(s) for s in data.get("steps", [])]
        task.params = data.get("params", {})
        task.current_step = data.get("current_step", 0)
        task.step_results = data.get("step_results", [])
        task.result_summary = data.get("result_summary", "")
        task.knowledge_to_save = data.get("knowledge_to_save", {})
        
        if data.get("created_at"):
            task.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            task.updated_at = datetime.fromisoformat(data["updated_at"])
        
        return task


class TaskTracker:
    """
    任务追踪器 - 管理所有任务的生命周期
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tasks_file = workspace / "memory" / "tasks_tracking.json"
        self._tasks: dict[str, TrackedTask] = {}
        self._active_task_id: str | None = None
        self._load()
    
    def _load(self) -> None:
        """从磁盘加载任务追踪数据"""
        if self.tasks_file.exists():
            try:
                data = json.loads(self.tasks_file.read_text(encoding="utf-8"))
                self._tasks = {
                    k: TrackedTask.from_dict(v) 
                    for k, v in data.get("tasks", {}).items()
                }
                self._active_task_id = data.get("active_task_id")
            except Exception:
                self._tasks = {}
        else:
            self._tasks = {}
    
    def _save(self) -> None:
        """保存任务追踪数据到磁盘"""
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
            "active_task_id": self._active_task_id,
            "updated_at": datetime.now().isoformat()
        }
        self.tasks_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), 
            encoding="utf-8"
        )
    
    def create_task(
        self,
        key: str,
        user_request: str,
        analyzed_from: str = "",
    ) -> str:
        """创建新任务"""
        import uuid
        task_id = f"{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
        
        task = TrackedTask(
            task_id=task_id,
            key=key,
            user_request=user_request,
        )
        task.analyzed_from = analyzed_from
        
        self._tasks[task_id] = task
        self._active_task_id = task_id
        self._save()
        
        return task_id
    
    def get_active_task(self) -> TrackedTask | None:
        """获取当前活跃任务"""
        if self._active_task_id and self._active_task_id in self._tasks:
            return self._tasks[self._active_task_id]
        return None
    
    def get_task(self, task_id: str) -> TrackedTask | None:
        """获取指定任务"""
        return self._tasks.get(task_id)
    
    def update_status(self, task_id: str, status: TaskStatus) -> bool:
        """更新任务状态"""
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        task.status = status
        task.updated_at = datetime.now()
        
        if status == TaskStatus.RUNNING and not task.start_time:
            task.start_time = datetime.now()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.end_time = datetime.now()
        
        self._save()
        return True
    
    def add_steps(self, task_id: str, steps: list[Step]) -> bool:
        """添加任务步骤"""
        if task_id not in self._tasks:
            return False
        
        self._tasks[task_id].steps = steps
        self._tasks[task_id].status = TaskStatus.PLANNING
        self._save()
        return True
    
    def update_step(
        self,
        task_id: str,
        step_index: int,
        status: str = None,
        result: str = None,
    ) -> bool:
        """更新步骤状态"""
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        if 0 <= step_index < len(task.steps):
            if status:
                task.steps[step_index].status = status
            if result:
                task.steps[step_index].result = result
            task.current_step = step_index
            task.updated_at = datetime.now()
            self._save()
            return True
        return False
    
    def complete_task(
        self,
        task_id: str,
        result_summary: str = "",
        knowledge_to_save: dict = None,
    ) -> bool:
        """完成任务"""
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.result_summary = result_summary
        task.knowledge_to_save = knowledge_to_save or {}
        task.end_time = datetime.now()
        task.updated_at = datetime.now()
        
        self._active_task_id = None
        self._save()
        return True
    
    def fail_task(self, task_id: str, error: str = "") -> bool:
        """标记任务失败"""
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        task.status = TaskStatus.FAILED
        task.result_summary = f"Failed: {error}"
        task.end_time = datetime.now()
        task.updated_at = datetime.now()
        
        self._active_task_id = None
        self._save()
        return True
    
    def list_tasks(
        self,
        status: TaskStatus = None,
        limit: int = 10,
    ) -> list[TrackedTask]:
        """列出任务"""
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        # 按更新时间排序
        tasks.sort(key=lambda t: t.updated_at, reverse=True)
        
        return tasks[:limit]
    
    def get_task_history(self, key: str = None, limit: int = 5) -> list[TrackedTask]:
        """获取任务历史"""
        tasks = list(self._tasks.values())
        
        # 过滤已完成的任务
        tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        
        if key:
            tasks = [t for t in tasks if t.key == key]
        
        # 按时间排序
        tasks.sort(key=lambda t: t.end_time or t.created_at, reverse=True)
        
        return tasks[:limit]
    
    def clear_old_tasks(self, days: int = 30) -> int:
        """清理旧任务"""
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        old_ids = []
        
        for task_id, task in self._tasks.items():
            if task.updated_at.timestamp() < cutoff:
                old_ids.append(task_id)
        
        for task_id in old_ids:
            del self._tasks[task_id]
        
        if old_ids:
            self._save()
        
        return len(old_ids)
    
    # ========== Step 3: 增量更新功能 ==========
    
    def save_intermediate_result(
        self,
        task_id: str,
        step_name: str,
        result: str,
        partial_data: dict = None,
    ) -> bool:
        """
        保存中间结果（增量更新）
        
        用于长任务执行过程中保存进度，即使中断也能恢复。
        
        Args:
            task_id: 任务ID
            step_name: 步骤名称
            result: 步骤结果
            partial_data: 可选的部分数据（如已处理的邮件列表）
            
        Returns:
            是否保存成功
        """
        if task_id not in self._tasks:
            return False
        
        task = self._tasks[task_id]
        
        # 记录中间结果
        intermediate = {
            "step": step_name,
            "result": result,
            "partial_data": partial_data or {},
            "timestamp": datetime.now().isoformat(),
        }
        
        task.step_results.append(intermediate)
        task.updated_at = datetime.now()
        
        # 增量保存到单独文件（避免频繁写入主文件）
        self._save_incremental(task_id, intermediate)
        
        return True
    
    def _save_incremental(self, task_id: str, intermediate: dict) -> None:
        """增量保存到单独文件"""
        inc_file = self.tasks_file.parent / f"task_{task_id}_incremental.jsonl"
        try:
            with open(inc_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(intermediate, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 增量保存失败不影响主流程
    
    def get_intermediate_results(self, task_id: str) -> list[dict]:
        """获取任务的中间结果"""
        inc_file = self.tasks_file.parent / f"task_{task_id}_incremental.jsonl"
        results = []
        
        if inc_file.exists():
            try:
                for line in inc_file.read_text(encoding="utf-8").strip().split("\n"):
                    if line:
                        results.append(json.loads(line))
            except Exception:
                pass
        
        # 也返回内存中的结果
        task = self._tasks.get(task_id)
        if task:
            results.extend(task.step_results)
        
        return results
    
    def get_progress(self, task_id: str) -> dict:
        """
        获取任务进度
        
        Returns:
            {
                "total_steps": 5,
                "completed_steps": 2,
                "progress_percent": 40,
                "current_step": "analyze_attachments"
            }
        """
        task = self._tasks.get(task_id)
        if not task:
            return {}
        
        total = len(task.steps)
        completed = sum(1 for s in task.steps if s.status == "completed")
        
        current = ""
        if task.current_step < len(task.steps):
            current = task.steps[task.current_step].name
        
        return {
            "total_steps": total,
            "completed_steps": completed,
            "progress_percent": int(completed / total * 100) if total > 0 else 0,
            "current_step": current,
        }
