"""
Task Expert - 任务执行专家
"""

from typing import Any

from nanobot.agent.experts.base import ExpertAgent


class TaskExpert(ExpertAgent):
    """
    任务执行专家 - 专门处理操作执行类任务
    
    专长：
    - 执行 shell 命令
    - 发送消息
    - 处理文件
    - 调度定时任务
    """
    
    name = "task_expert"
    description = "任务执行专家"
    tools = [
        "shell",
        "message",
        "spawn",
        "cron",
    ]
    knowledge_prefix = "task_"
    
    async def process(self, user_request: str, context: dict[str, Any]) -> dict[str, Any]:
        """处理任务执行相关请求"""
        return {
            "status": "success",
            "content": f"Task Expert 处理: {user_request[:100]}",
            "tools_used": [],
        }
    
    def get_system_prompt(self) -> str:
        """获取任务执行专家的系统提示"""
        return """你是任务执行专家。

你的专长：
- 执行命令：使用 shell 执行系统命令
- 发送消息：使用 message 发送消息到聊天渠道
- 后台任务：使用 spawn 启动后台子任务
- 定时任务：使用 cron 调度定时任务

工作流程：
1. 理解用户想要执行什么操作
2. 选择合适的工具执行
3. 返回执行结果

注意：
- 执行前确认操作的正确性
- 危险操作（如删除）要二次确认
- 长时间任务考虑使用 spawn 后台执行"""
