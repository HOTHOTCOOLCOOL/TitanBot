"""
Expert Agent 基类 - 所有专家 Agent 的父类
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class TaskType(Enum):
    """任务类型枚举"""
    EMAIL_ANALYSIS = "email_analysis"
    DATA_SEARCH = "data_search"
    TASK_EXECUTION = "task_execution"
    SIMPLE_QA = "simple_qa"
    GENERAL = "general"


class ExpertAgent(ABC):
    """
    专家 Agent 基类
    
    每个 Expert Agent 有：
    - name: 专家名称
    - description: 专家描述
    - tools: 专用工具列表
    - knowledge_prefix: 知识库前缀
    """
    
    name: str = "expert"
    description: str = "General expert agent"
    tools: list[str] = []
    knowledge_prefix: str = ""
    
    def __init__(self, llm_provider=None, tools_registry=None):
        self.llm_provider = llm_provider
        self.tools_registry = tools_registry
    
    @abstractmethod
    async def process(self, user_request: str, context: dict[str, Any]) -> dict[str, Any]:
        """
        处理用户请求
        
        Args:
            user_request: 用户请求
            context: 上下文信息
            
        Returns:
            处理结果 {"status": "success/failure", "content": "...", "tools_used": [...]}
        """
        pass
    
    def get_system_prompt(self) -> str:
        """获取该专家的系统提示"""
        return f"""你是一个{self.description}。

你的专长领域：
{chr(10).join(f"- {tool}" for tool in self.tools)}

当你需要使用工具时，直接调用。不要询问用户确认。
完成任务后，给出清晰的总结。"""
    
    def get_tools_definitions(self) -> list[dict]:
        """获取该专家可用的工具定义"""
        if not self.tools_registry:
            return []
        
        definitions = []
        for tool_name in self.tools:
            tool = self.tools_registry.get(tool_name)
            if tool:
                definitions.append(tool.get_definition())
        return definitions


class ExpertRegistry:
    """
    专家注册表 - 管理所有可用的 Expert Agents
    """
    
    def __init__(self):
        self._experts: dict[str, ExpertAgent] = {}
    
    def register(self, task_type: TaskType, expert: ExpertAgent) -> None:
        """注册一个专家"""
        self._experts[task_type.value] = expert
    
    def get(self, task_type: TaskType | str) -> ExpertAgent | None:
        """获取对应任务类型的专家"""
        if isinstance(task_type, TaskType):
            task_type = task_type.value
        return self._experts.get(task_type)
    
    def list_experts(self) -> list[dict[str, str]]:
        """列出所有已注册的专家"""
        return [
            {"type": key, "name": exp.name, "description": exp.description}
            for key, exp in self._experts.items()
        ]
    
    def get_all_task_types(self) -> list[str]:
        """获取所有任务类型"""
        return list(self._experts.keys())


# 全局注册表实例
_default_registry: ExpertRegistry | None = None


def get_expert_registry() -> ExpertRegistry:
    """获取全局专家注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ExpertRegistry()
    return _default_registry


def register_expert(task_type: TaskType, expert: ExpertAgent) -> None:
    """快捷函数：注册专家到全局注册表"""
    get_expert_registry().register(task_type, expert)
