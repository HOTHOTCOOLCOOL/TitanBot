"""
Router Agent - 任务路由器

职责：
1. 接收用户请求
2. 判断任务类型
3. 选择合适的 Expert Agent
4. 返回路由结果
"""

import json
from typing import Any

from loguru import logger

from nanobot.agent.experts.base import ExpertAgent, ExpertRegistry, TaskType, get_expert_registry


class RouterAgent:
    """
    轻量级任务路由器
    
    使用简短的 prompt 让 LLM 判断任务类型，然后路由到对应的 Expert Agent。
    
    设计原则：
    - 优先使用关键词匹配（最快）
    - LLM 分类使用轻量级模型（快速、低成本）
    - 支持自定义路由模型
    """
    
    # 任务类型定义
    TASK_DEFINITIONS = {
        "email_analysis": {
            "keywords": ["邮件", "email", "邮箱", "outlook", "附件", "发件人", "收件人"],
            "description": "邮件分析、搜索邮件、读取附件"
        },
        "data_search": {
            "keywords": ["搜索", "查找", "找", "查", "search", "find", "google"],
            "description": "搜索信息、查找资料"
        },
        "task_execution": {
            "keywords": ["执行", "发送", "处理", "创建", "删除", "run", "send", "create", "delete"],
            "description": "执行操作、发送消息、处理文件"
        },
    }
    
    # 轻量级模型推荐列表（按速度排序）
    # 这些模型通常是非思考型的，适合简单分类任务
    LIGHTWEIGHT_MODELS = [
        # 本地模型（推荐）
        "flowsteer-8b@f16",
        # OpenRouter 轻量模型
        "google/gemma-3n-e4b-it",      # 快速、多语言
        "google/gemma-3-4b-it",         # 快速
        "meta-llama/llama-3.2-3b-instruct",  # 快速
        "qwen/qwen-2.5-3b-instruct",    # 极快
        "anthropic/claude-3-haiku",     # 快速
        # 国内模型
        "minimax/minimax-small",        # 极快
    ]
    
    def __init__(
        self, 
        llm_provider=None,
        expert_registry: ExpertRegistry | None = None,
        router_model: str | None = None,
    ):
        """
        初始化路由器
        
        Args:
            llm_provider: LLM 提供者
            expert_registry: 专家注册表
            router_model: 指定路由使用的模型（可选，默认自动选择轻量模型）
        """
        self.llm_provider = llm_provider
        self.expert_registry = expert_registry or get_expert_registry()
        self.router_model = router_model
    
    async def route(self, user_request: str) -> dict[str, Any]:
        """
        路由用户请求到合适的 Expert Agent
        
        Args:
            user_request: 用户请求
            
        Returns:
            {
                "task_type": "email_analysis",
                "expert": ExpertAgent,
                "reason": "用户提到搜索邮件",
                "confidence": 0.9
            }
        """
        # 1. 首先尝试关键词匹配（快速后备）
        task_type = self._keyword_match(user_request)
        if task_type:
            logger.info(f"Router: 关键词匹配 -> {task_type}")
            return {
                "task_type": task_type,
                "expert": self.expert_registry.get(task_type),
                "reason": f"关键词匹配: {user_request[:50]}",
                "confidence": 0.8,
                "method": "keyword"
            }
        
        # 2. 如果关键词匹配失败，使用 LLM 判断
        if self.llm_provider:
            task_type = await self._llm_classify(user_request)
            if task_type:
                logger.info(f"Router: LLM 分类 -> {task_type}")
                expert = self.expert_registry.get(task_type)
                return {
                    "task_type": task_type,
                    "expert": expert,
                    "reason": f"LLM 判断: {user_request[:50]}",
                    "confidence": 0.9,
                    "method": "llm"
                }
        
        # 3. 默认使用通用 Agent
        logger.info(f"Router: 默认 -> general")
        return {
            "task_type": "general",
            "expert": self.expert_registry.get("general"),
            "reason": "无法判断任务类型，使用通用处理",
            "confidence": 0.5,
            "method": "default"
        }
    
    def _keyword_match(self, user_request: str) -> str | None:
        """
        简单的关键词匹配
        
        Returns:
            匹配到的任务类型，或 None
        """
        request_lower = user_request.lower()
        
        # 检查每个任务类型的关键词
        for task_type, config in self.TASK_DEFINITIONS.items():
            for keyword in config["keywords"]:
                if keyword.lower() in request_lower:
                    return task_type
        
        return None
    
    def _get_lightweight_model(self) -> str | None:
        """
        获取轻量级模型用于路由分类
        
        优先使用用户指定的模型，否则从 LIGHTWEIGHT_MODELS 中选择
        """
        if self.router_model:
            return self.router_model
        
        # 尝试获取可用的轻量级模型
        if not self.llm_provider:
            return None
        
        try:
            # 获取可用的模型列表
            available_models = self.llm_provider.get_available_models()
            
            # 匹配轻量级模型
            for model in self.LIGHTWEIGHT_MODELS:
                if any(model in m or m in model for m in available_models):
                    logger.info(f"Router: 使用轻量级模型 {model}")
                    return model
            
            # 如果没有轻量模型，返回默认
            return None
        except Exception:
            return None
    
    async def _llm_classify(self, user_request: str) -> str | None:
        """
        使用轻量级 LLM 进行任务分类
        
        设计原则：
        - 使用非思考型模型（如 llama-3.2-3b, qwen-2.5-3b）
        - 极短的 prompt
        - 低温度（更确定性）
        - 小 max_tokens
        
        Returns:
            任务类型字符串，或 None
        """
        if not self.llm_provider:
            return None
        
        # 获取轻量级模型
        model = self._get_lightweight_model()
        
        prompt = f"""判断这个任务类型，只返回关键词。

类型：email_analysis, data_search, task_execution, simple_qa

请求: {user_request}

返回: """

        try:
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.llm_provider.get_default_model(),
                temperature=0.1,  # 低温度，更确定性的输出
                max_tokens=20,    # 极短，只需要返回一个词
            )
            
            content = (response.content or "").strip().lower()
            
            # 提取任务类型
            for task_type in self.TASK_DEFINITIONS.keys():
                if task_type in content:
                    return task_type
            
            # 检查是否有 simple_qa
            if any(q in content for q in ["simple_qa", "simple", "qa", "问答", "闲聊"]):
                return "simple_qa"
            
            return None
            
        except Exception as e:
            logger.warning(f"Router LLM 分类失败: {e}")
            return None
    
    def get_task_type_description(self, task_type: str) -> str:
        """获取任务类型的描述"""
        if task_type in self.TASK_DEFINITIONS:
            return self.TASK_DEFINITIONS[task_type]["description"]
        return "通用任务"


class SimpleRouter:
    """
    简化版路由器 - 不依赖 LLM，只用规则
    
    适用于轻量级场景或作为后备
    """
    
    TASK_KEYWORDS = {
        "email_analysis": ["邮件", "email", "邮箱", "outlook", "附件", "发件人", "收件人"],
        "data_search": ["搜索", "查找", "找", "查", "search", "find"],
        "task_execution": ["执行", "发送", "发送", "处理", "创建", "删除"],
    }
    
    def route(self, user_request: str) -> str:
        """返回任务类型字符串"""
        request_lower = user_request.lower()
        
        # 按优先级检查
        for task_type, keywords in self.TASK_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in request_lower:
                    return task_type
        
        return "general"
