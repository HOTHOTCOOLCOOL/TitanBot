"""
Task Knowledge Store - 用于存储和管理任务知识库

存储结构:
{
    "tasks": [
        {
            "key": "任务关键词",
            "description": "任务描述",
            "steps": ["step1", "step2"],
            "params": {"folder": "inbox/reporting"},
            "last_run": "2026-02-21",
            "result_summary": "分析结果摘要",
            "confirmed": true,
            "use_count": 5,
            "success_count": 4,
            "fail_count": 1,
            "last_steps_detail": [{"tool": "...", "args": {}, "result": "..."}],
            "created_at": "2026-02-21"
        }
    ]
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class TaskKnowledgeStore:
    """任务知识库存储"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tasks_file = workspace / "memory" / "tasks.json"
        self._tasks: list[dict[str, Any]] = []
        self._load()
    
    def _load(self) -> None:
        """从磁盘加载任务知识库"""
        if self.tasks_file.exists():
            try:
                data = json.loads(self.tasks_file.read_text(encoding="utf-8"))
                self._tasks = data.get("tasks", [])
            except Exception:
                self._tasks = []
        else:
            self._tasks = []
    
    def _save(self) -> None:
        """保存任务知识库到磁盘"""
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": self._tasks, "updated_at": datetime.now().isoformat()}
        self.tasks_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    def add_task(
        self,
        key: str,
        description: str,
        steps: list[str],
        params: dict[str, Any],
        result_summary: str,
        steps_detail: list[dict[str, Any]] | None = None,
    ) -> None:
        """添加新任务到知识库"""
        task = {
            "key": key,
            "description": description,
            "steps": steps,
            "params": params,
            "last_run": datetime.now().strftime("%Y-%m-%d"),
            "result_summary": result_summary,
            "confirmed": True,
            "use_count": 1,
            "success_count": 1,
            "fail_count": 0,
            "last_steps_detail": steps_detail or [],
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
        self._tasks.append(task)
        self._save()
    
    def update_task(self, key: str, result_summary: str) -> bool:
        """更新现有任务的执行结果"""
        for task in self._tasks:
            if task.get("key") == key:
                task["last_run"] = datetime.now().strftime("%Y-%m-%d")
                task["result_summary"] = result_summary
                task["use_count"] = task.get("use_count", 0) + 1
                self._save()
                return True
        return False
    
    def find_task(self, key: str) -> dict[str, Any] | None:
        """查找任务"""
        for task in self._tasks:
            if task.get("key") == key:
                return task
        return None
    
    def search_tasks(self, keyword: str) -> list[dict[str, Any]]:
        """搜索任务（简单的关键词匹配）"""
        results = []
        keyword_lower = keyword.lower()
        for task in self._tasks:
            if (keyword_lower in task.get("key", "").lower() or 
                keyword_lower in task.get("description", "").lower()):
                results.append(task)
        return results
    
    def get_all_tasks(self) -> list[dict[str, Any]]:
        """获取所有任务"""
        return self._tasks
    
    def delete_task(self, key: str) -> bool:
        """删除任务"""
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.get("key") != key]
        if len(self._tasks) < before:
            self._save()
            return True
        return False
    
    def cleanup_old_tasks(self, max_tasks: int = 50) -> int:
        """清理旧任务（保留最近 N 条）"""
        if len(self._tasks) <= max_tasks:
            return 0
        
        # 按使用次数排序，保留使用次数多的
        self._tasks.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        removed = len(self._tasks) - max_tasks
        self._tasks = self._tasks[:max_tasks]
        self._save()
        return removed

    def record_success(self, key: str) -> bool:
        """Record a successful task execution."""
        for task in self._tasks:
            if task.get("key") == key:
                task["success_count"] = task.get("success_count", 0) + 1
                self._save()
                return True
        return False

    def record_failure(self, key: str) -> bool:
        """Record a failed task execution."""
        for task in self._tasks:
            if task.get("key") == key:
                task["fail_count"] = task.get("fail_count", 0) + 1
                self._save()
                return True
        return False

    def get_success_rate(self, key: str) -> float:
        """Get the success rate (0.0-1.0) for a task. Returns -1 if not found."""
        task = self.find_task(key)
        if not task:
            return -1.0
        total = task.get("success_count", 0) + task.get("fail_count", 0)
        if total == 0:
            return 1.0
        return task.get("success_count", 0) / total

    def update_steps_detail(self, key: str, steps_detail: list[dict[str, Any]]) -> bool:
        """Update the last detailed steps for a task."""
        for task in self._tasks:
            if task.get("key") == key:
                task["last_steps_detail"] = steps_detail
                self._save()
                return True
        return False
