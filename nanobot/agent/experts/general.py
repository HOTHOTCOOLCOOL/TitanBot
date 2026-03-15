"""
General Expert - 通用专家（默认）
"""

from typing import Any

from nanobot.agent.experts.base import ExpertAgent


class GeneralExpert(ExpertAgent):
    """
    通用专家 - 默认的 Expert Agent
    
    当 Router 无法确定任务类型时使用。
    可以处理各种类型的请求。
    """
    
    name = "general"
    description = "通用助手"
    tools = []  # 使用所有可用工具
    knowledge_prefix = ""
    
    async def process(self, user_request: str, context: dict[str, Any]) -> dict[str, Any]:
        """处理通用请求"""
        return {
            "status": "success",
            "content": f"General Expert 处理: {user_request[:100]}",
            "tools_used": [],
        }
    
    def get_system_prompt(self) -> str:
        """获取通用专家的系统提示"""
        return """你是一个通用的 AI 助手。

你可以帮助用户完成各种任务，包括：
- 回答问题
- 分析信息
- 执行各种操作
- 使用各种工具

当你需要使用工具时，直接调用。
尽可能提供准确、有用的帮助。"""
