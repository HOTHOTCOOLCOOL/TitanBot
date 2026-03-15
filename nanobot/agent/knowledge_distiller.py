"""
Step 4: 知识蒸馏器 - Knowledge Distiller

任务完成后自动从任务结果中提取知识，保存到知识库。
"""

import json
from typing import Any
from loguru import logger

from nanobot.agent.task_knowledge import TaskKnowledgeStore


class KnowledgeDistiller:
    """
    知识蒸馏器
    
    任务完成后自动提取知识：
    - 任务类型（key）
    - 执行步骤（steps）
    - 参数模式（params schema）
    - 结果摘要（result_summary）
    
    设计原则：
    - 独立于主流程，可选调用
    - 如果失败，不影响任务完成
    - 用户可以关闭自动保存
    """
    
    def __init__(self, workspace, enabled: bool = True):
        self.workspace = workspace
        self.enabled = enabled
        self.knowledge_store = TaskKnowledgeStore(workspace)
    
    async def distill(
        self,
        task_id: str,
        user_request: str,
        tool_calls: list[dict] = None,
        final_result: str = "",
        llm_provider = None,
    ) -> dict | None:
        """
        从任务执行结果中提取知识并保存
        
        Args:
            task_id: 任务ID
            user_request: 用户原始请求
            tool_calls: 执行的工具调用列表
            final_result: 最终结果
            llm_provider: LLM 提供者（可选，用于智能提取）
            
        Returns:
            保存的知识条目，或 None
        """
        if not self.enabled:
            logger.debug("KnowledgeDistiller: disabled, skipping")
            return None
        
        logger.info(f"KnowledgeDistiller: 提取任务 {task_id} 的知识")
        
        # 1. 从 tool_calls 提取步骤
        steps = self._extract_steps(tool_calls or [])
        
        # 2. 从请求和结果中提取 key
        key = self._extract_key(user_request, tool_calls or [])
        
        # 3. 生成描述
        description = user_request[:100]
        
        # 4. 生成摘要
        result_summary = final_result[:500] if final_result else "任务完成"
        
        # 5. 如果有 LLM，可以做更智能的提取
        if llm_provider:
            try:
                extracted = await self._llm_extract(
                    user_request, tool_calls or [], final_result, llm_provider
                )
                if extracted:
                    key = extracted.get("key", key)
                    description = extracted.get("description", description)
                    steps = extracted.get("steps", steps)
            except Exception as e:
                logger.warning(f"KnowledgeDistiller LLM 提取失败: {e}")
        
        # 6. 保存到知识库
        try:
            # 检查是否已存在
            existing = self.knowledge_store.find_task(key)
            if existing:
                self.knowledge_store.update_task(key, result_summary)
                logger.info(f"KnowledgeDistiller: 更新已有知识 {key}")
            else:
                self.knowledge_store.add_task(
                    key=key,
                    description=description,
                    steps=steps,
                    params={},
                    result_summary=result_summary,
                )
                logger.info(f"KnowledgeDistiller: 保存新知识 {key}")
            
            return {
                "key": key,
                "description": description,
                "steps": steps,
                "result_summary": result_summary,
            }
        except Exception as e:
            logger.error(f"KnowledgeDistiller: 保存失败 {e}")
            return None
    
    def _extract_steps(self, tool_calls: list[dict]) -> list[str]:
        """从工具调用中提取步骤"""
        steps = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                func = tc.get("function", {})
                name = func.get("name", "")
                if name:
                    steps.append(name)
            elif hasattr(tc, "name"):
                steps.append(tc.name)
        return steps
    
    def _extract_key(self, user_request: str, tool_calls: list[dict]) -> str:
        """从请求和工具中提取任务 key"""
        user_lower = user_request.lower()
        
        # 基于关键词生成 key
        if any(w in user_lower for w in ["邮件", "email", "outlook"]):
            base = "email"
        elif any(w in user_lower for w in ["搜索", "search", "查找"]):
            base = "search"
        elif any(w in user_lower for w in ["发送", "send", "消息"]):
            base = "message"
        else:
            base = "task"
        
        # 添加时间戳避免重复
        from datetime import datetime
        timestamp = datetime.now().strftime("%m%d")
        
        return f"{base}_{timestamp}"
    
    async def _llm_extract(
        self,
        user_request: str,
        tool_calls: list[dict],
        final_result: str,
        llm_provider,
    ) -> dict | None:
        """使用 LLM 智能提取知识"""
        prompt = f"""从任务执行结果中提取知识条目，返回 JSON：

{{
    "key": "任务标识符（英文简短）",
    "description": "任务描述",
    "steps": ["step1", "step2"],
    "params": {{"param1": "类型"}}
}}

用户请求: {user_request}
执行的工具: {json.dumps([tc.get('function', {}).get('name', '') for tc in tool_calls])}
结果: {final_result[:200]}

只返回 JSON："""

        try:
            response = await llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=llm_provider.get_default_model(),
                temperature=0.3,
                max_tokens=200,
            )
            text = (response.content or "").strip()
            
            # 提取 JSON
            if "{" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_str = text[start:end]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"LLM 提取失败: {e}")
        
        return None


# 便捷函数
async def auto_distill(
    workspace,
    task_id: str,
    user_request: str,
    tool_calls: list = None,
    final_result: str = "",
    llm_provider = None,
    enabled: bool = True,
) -> dict | None:
    """
    自动知识蒸馏的便捷函数
    
    可以在任务完成后调用此函数来自动保存知识
    """
    distiller = KnowledgeDistiller(workspace, enabled=enabled)
    return await distiller.distill(
        task_id=task_id,
        user_request=user_request,
        tool_calls=tool_calls,
        final_result=final_result,
        llm_provider=llm_provider,
    )
