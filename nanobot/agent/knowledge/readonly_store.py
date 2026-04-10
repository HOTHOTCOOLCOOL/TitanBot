"""
Read-Only adapter for TaskKnowledgeStore to prevent concurrent write corruption
from Worker subprocesses.
"""
import copy
from typing import Any
from loguru import logger

class ReadOnlyKnowledgeStore:
    """
    A read-only adapter that wraps an existing TaskKnowledgeStore.
    It delegates all read operations to the underlying store but intercepts
    and mocks all write operations, preventing Worker sub-processes from 
    corrupting the shared JSON files.
    """
    def __init__(self, backend_store):
        self._backend = backend_store
        
        # We need to provide the same properties that KnowledgeWorkflow expects
        if hasattr(self._backend, "workspace"):
            self.workspace = self._backend.workspace
            
    def _save(self) -> None:
        """Intercepted: Do nothing"""
        pass
        
    def add_task(self, *args, **kwargs) -> None:
        logger.debug("ReadOnlyKnowledgeStore: add_task intercepted in Worker process")
        pass
        
    def update_task(self, *args, **kwargs) -> bool:
        logger.debug("ReadOnlyKnowledgeStore: update_task intercepted in Worker process")
        return True
        
    def find_task(self, key: str) -> dict[str, Any] | None:
        return self._backend.find_task(key)
        
    def search_tasks(self, keyword: str) -> list[dict[str, Any]]:
        return self._backend.search_tasks(keyword)
        
    def get_all_tasks(self) -> list[dict[str, Any]]:
        # Return deep copy to prevent in-memory mutation
        return copy.deepcopy(self._backend.get_all_tasks())
        
    def delete_task(self, key: str) -> bool:
        logger.debug("ReadOnlyKnowledgeStore: delete_task intercepted in Worker process")
        return False
        
    def cleanup_old_tasks(self, max_tasks: int = 50) -> int:
        return 0
        
    def run_knowledge_judge(self, *args, **kwargs) -> int:
        return 0
        
    def record_success(self, key: str) -> bool:
        logger.debug("ReadOnlyKnowledgeStore: record_success intercepted in Worker process")
        return True
        
    def record_failure(self, key: str) -> bool:
        logger.debug("ReadOnlyKnowledgeStore: record_failure intercepted in Worker process")
        return True
        
    def get_success_rate(self, key: str) -> float:
        return self._backend.get_success_rate(key)
        
    def update_steps_detail(self, *args, **kwargs) -> bool:
        return True
        
    def find_similar_task(self, key: str, threshold: float = 0.5) -> dict[str, Any] | None:
        return self._backend.find_similar_task(key, threshold)
        
    def merge_task(self, *args, **kwargs) -> bool:
        logger.debug("ReadOnlyKnowledgeStore: merge_task intercepted in Worker process")
        return True
        
    def count(self) -> int:
        return self._backend.count()
        
    # Phase 12: Experience Bank
    def add_experience(self, context_trigger: str, tactical_prompt: str, action_type: str = "general") -> None:
        logger.debug("ReadOnlyKnowledgeStore: add_experience intercepted in Worker process")
        pass
        
    def get_experiences(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._backend.get_experiences())
