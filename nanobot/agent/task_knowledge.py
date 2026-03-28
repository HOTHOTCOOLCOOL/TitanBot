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


def tokenize_key(text: str) -> list[str]:
    """Tokenize text for similarity matching.

    Shared between TaskKnowledgeStore and KnowledgeWorkflow.
    For Chinese text: uses jieba word segmentation (falls back to char-level).
    For English text: splits by whitespace, filters short words.
    """
    text = text.lower().strip()
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cjk_count > len(text) * 0.3:
        try:
            import jieba
            words = jieba.lcut(text)
            return [w.strip() for w in words if len(w.strip()) >= 2]
        except ImportError:
            return [c for c in text if '\u4e00' <= c <= '\u9fff']
    else:
        return [w for w in text.split() if len(w) > 1]


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
                self._experiences = data.get("experiences", [])
            except Exception:
                self._tasks = []
                self._experiences = []
        else:
            self._tasks = []
            self._experiences = []
    
    def _save(self) -> None:
        """保存任务知识库到磁盘"""
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": self._tasks, "experiences": getattr(self, "_experiences", []), "updated_at": datetime.now().isoformat()}
        self.tasks_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    def add_task(
        self,
        key: str,
        description: str,
        steps: list[str],
        params: dict[str, Any],
        result_summary: str,
        steps_detail: list[dict[str, Any]] | None = None,
        triggers: list[str] | None = None,
        tags: list[str] | None = None,
        anti_patterns: list[str] | None = None,
        confidence: float = 1.0,
        derived_from: str | None = None,  # P29-6: Provenance tracking
    ) -> None:
        """添加新任务到知识库"""
        task = {
            "key": key,
            "description": description,
            "triggers": triggers or [],
            "tags": tags or [],
            "anti_patterns": anti_patterns or [],
            "confidence": confidence,
            "derived_from": derived_from,
            "steps": steps,
            "params": params,
            "last_run": datetime.now().strftime("%Y-%m-%d"),
            "result_summary": result_summary,
            "confirmed": True,
            "use_count": 1,
            "success_count": 1,
            "fail_count": 0,
            "last_steps_detail": steps_detail or [],
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "version": 1,
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

    def run_knowledge_judge(self, min_confidence: float = 0.3, max_fail_rate: float = 0.7) -> int:
        """Evaluate all tasks and discard those that are consistently failing or have low confidence.
        
        Args:
            min_confidence: Threshold below which a task is discarded.
            max_fail_rate: Threshold above which a task is discarded.
            
        Returns:
            Number of tasks discarded.
        """
        before = len(self._tasks)
        retained = []
        for task in self._tasks:
            conf = task.get("confidence", 1.0)
            success = task.get("success_count", 0)
            fail = task.get("fail_count", 0)
            total = success + fail
            fail_rate = fail / total if total > 0 else 0.0

            if conf < min_confidence or fail_rate > max_fail_rate:
                # Discarding task
                continue
            retained.append(task)
            
        self._tasks = retained
        removed = before - len(self._tasks)
        if removed > 0:
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

    def find_similar_task(self, key: str, threshold: float = 0.5) -> dict[str, Any] | None:
        """Find the most similar existing task using Jaccard word similarity.

        Args:
            key: The task key to compare against.
            threshold: Minimum Jaccard score to consider a match (0.0-1.0).

        Returns:
            The most similar task dict, or None if no match above threshold.
        """
        key_words = set(tokenize_key(key))
        if not key_words:
            return None

        best: dict[str, Any] | None = None
        best_score = 0.0
        for task in self._tasks:
            task_key = task.get("key", "")
            task_words = set(tokenize_key(task_key))
            if not task_words:
                continue
            intersection = key_words & task_words
            union = key_words | task_words
            score = len(intersection) / len(union) if union else 0
            if score > best_score:
                best_score = score
                best = task

        if best and best_score >= threshold:
            return best
        return None

    def merge_task(
        self,
        existing_key: str,
        new_steps: list | None = None,
        new_result_summary: str | None = None,
        new_steps_detail: list[dict[str, Any]] | None = None,
        new_triggers: list[str] | None = None,
        new_tags: list[str] | None = None,
        new_anti_patterns: list[str] | None = None,
        new_confidence: float | None = None,
        derived_from: str | None = None,  # P29-6: Provenance tracking
    ) -> bool:
        """Merge new execution data into an existing task entry.

        Increments version, updates steps/result/detail while preserving
        accumulated success/fail counts.

        Returns:
            True if merged successfully, False if key not found.
        """
        for task in self._tasks:
            if task.get("key") == existing_key:
                task["version"] = task.get("version", 1) + 1
                task["last_run"] = datetime.now().strftime("%Y-%m-%d")
                task["use_count"] = task.get("use_count", 0) + 1
                if new_steps is not None:
                    task["steps"] = new_steps
                if new_result_summary is not None:
                    task["result_summary"] = new_result_summary
                if new_steps_detail is not None:
                    task["last_steps_detail"] = new_steps_detail
                
                # Merge lists, keeping unique items
                if new_triggers:
                    task["triggers"] = list(set(task.get("triggers", []) + new_triggers))
                if new_tags:
                    task["tags"] = list(set(task.get("tags", []) + new_tags))
                if new_anti_patterns:
                    task["anti_patterns"] = list(set(task.get("anti_patterns", []) + new_anti_patterns))
                if new_confidence is not None:
                    task["confidence"] = new_confidence
                if derived_from:
                    task["derived_from"] = derived_from

                self._save()
                return True
        return False

    def count(self) -> int:
        """Return the total number of task entries."""
        return len(self._tasks)

    # --- Phase 12: Experience Bank (Action-level prompts) ---
    
    def add_experience(self, context_trigger: str, tactical_prompt: str, action_type: str = "general") -> None:
        """Add a new experience (action-level tactical prompt) to the bank."""
        if not hasattr(self, "_experiences"):
            self._experiences = []
            
        exp = {
            "trigger": context_trigger,
            "prompt": tactical_prompt,
            "action_type": action_type,
            "success_count": 1,
            "fail_count": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "version": 1
        }
        self._experiences.append(exp)
        self._save()

    def get_experiences(self) -> list[dict[str, Any]]:
        """Return all experiences in the bank."""
        return getattr(self, "_experiences", [])
