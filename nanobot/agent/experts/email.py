"""
Email Expert - 邮件处理专家
"""

from typing import Any

from nanobot.agent.experts.base import ExpertAgent


class EmailExpert(ExpertAgent):
    """
    邮件专家 - 专门处理邮件相关任务
    
    专长：
    - 搜索邮件
    - 读取邮件内容
    - 分析附件
    - 发送邮件
    """
    
    name = "email_expert"
    description = "邮件处理专家"
    tools = [
        "outlook.search_emails",
        "outlook.read_email",
        "outlook.get_attachments",
        "outlook.send_email",
        "attachment_analyzer",
    ]
    knowledge_prefix = "email_"
    
    async def process(self, user_request: str, context: dict[str, Any]) -> dict[str, Any]:
        """
        处理邮件相关任务
        
        流程：
        1. 解析用户请求（搜索/读取/分析/发送）
        2. 执行相应操作
        3. 返回结果
        """
        # 这里的具体实现会在集成到 loop 时完善
        return {
            "status": "success",
            "content": f"Email Expert 处理: {user_request[:100]}",
            "tools_used": [],
        }
    
    def get_system_prompt(self) -> str:
        """获取邮件专家的系统提示"""
        return """你是邮件处理专家。

你的专长：
- 搜索邮件：使用 outlook.search_emails 搜索符合条件的邮件
- 读取邮件：使用 outlook.read_email 获取邮件详情
- 提取附件：使用 outlook.get_attachments 获取附件
- 分析附件：使用 attachment_analyzer 分析附件内容
- 发送邮件：使用 outlook.send_email 发送邮件

工作流程：
1. 先搜索邮件，找到相关邮件
2. 读取邮件详情，获取内容
3. 如有附件，提取并分析
4. 如需发送，使用 outlook.send_email

注意：
- 搜索邮件时尽量精确，提供足够的搜索条件
- 读取邮件后再分析附件
- 发送给外部邮箱时使用 outlook.send_email"""


class EmailPreAnalyzer:
    """
    邮件预分析器 - 分析用户请求，确定搜索策略
    """
    
    def analyze(self, user_request: str) -> dict[str, Any]:
        """
        分析用户请求，返回搜索参数
        
        Returns:
            {
                "action": "search|read|analyze|send",
                "params": {...},
                "suggestion": "..."
            }
        """
        user_lower = user_request.lower()
        
        # 判断操作类型
        if any(k in user_lower for k in ["搜索", "找", "查找", "search", "find"]):
            action = "search"
        elif any(k in user_lower for k in ["发送", "发", "send"]):
            action = "send"
        elif any(k in user_lower for k in ["分析", "analyze"]):
            action = "analyze"
        else:
            action = "search"  # 默认搜索
        
        # 提取搜索参数
        params = {}
        
        # 发件人
        for keyword in ["发件人", "from", "sender"]:
            if keyword in user_lower:
                idx = user_lower.find(keyword)
                # 简单提取：取关键词后面的内容
                params["sender"] = user_request[idx:].split()[1] if len(user_request[idx:].split()) > 1 else ""
        
        # 关键词
        if "关于" in user_request:
            idx = user_request.find("关于")
            params["keyword"] = user_request[idx+2:].split()[0]
        
        # 日期范围
        if "上周" in user_request:
            params["date_range"] = "last_week"
        elif "上周" in user_request:
            params["date_range"] = "last_week"
        elif "今天" in user_request:
            params["date_range"] = "today"
        elif "昨天" in user_request:
            params["date_range"] = "yesterday"
        
        # 文件夹
        if "收件箱" in user_request or "inbox" in user_lower:
            params["folder"] = "inbox"
        elif "已发送" in user_request or "sent" in user_lower:
            params["folder"] = "sent"
        
        return {
            "action": action,
            "params": params,
            "suggestion": f"建议使用 {action} 操作，参数: {params}"
        }
