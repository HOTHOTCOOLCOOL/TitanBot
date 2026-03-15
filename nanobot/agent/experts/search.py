"""
Search Expert - 搜索专家
"""

from typing import Any

from nanobot.agent.experts.base import ExpertAgent


class SearchExpert(ExpertAgent):
    """
    搜索专家 - 专门处理搜索相关任务
    
    专长：
    - 网页搜索
    - 内容抓取
    - 文件搜索
    """
    
    name = "search_expert"
    description = "搜索专家"
    tools = [
        "web.search",
        "web.fetch",
        "filesystem.search",
    ]
    knowledge_prefix = "search_"
    
    async def process(self, user_request: str, context: dict[str, Any]) -> dict[str, Any]:
        """处理搜索相关任务"""
        return {
            "status": "success",
            "content": f"Search Expert 处理: {user_request[:100]}",
            "tools_used": [],
        }
    
    def get_system_prompt(self) -> str:
        """获取搜索专家的系统提示"""
        return """你是搜索专家。

你的专长：
- 网页搜索：使用 web.search 搜索互联网信息
- 内容抓取：使用 web.fetch 获取网页内容
- 文件搜索：在本地文件系统搜索文件

工作流程：
1. 明确搜索目标
2. 使用合适的搜索工具
3. 整理搜索结果
4. 提供清晰的总结

注意：
- 搜索前先理解用户真正想要什么
- 多个关键词可以提高搜索精度
- 重要信息要验证来源"""
