"""
Task Knowledge Tool - 用于记录和管理任务知识
"""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.task_knowledge import TaskKnowledgeStore


class TaskMemoryTool(Tool):
    """工具：管理任务知识库"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.store = TaskKnowledgeStore(workspace)
    
    @property
    def name(self) -> str:
        return "task_memory"
    
    @property
    def description(self) -> str:
        return """Task Knowledge Manager - 管理任务知识库

⚠️ 重要规则（必须遵守）：
1. **不要自动从知识库返回结果** - 知识库只是缓存，不代表最新数据
2. **必须先用工具获取最新数据** - 无论知识库有没有，收到任务后先用 outlook 工具获取当前数据
3. **只在用户明确确认后才保存** - 用户说"好的"、"收到"、"是的"才调用 save
4. **禁止在工具执行前使用知识库结果**

Actions:
- save: 用户确认后才保存 (参数: key, description, steps, params, result_summary)
- search: 仅用于查看，不要直接返回给用户
- get: 获取详情参考
- list: 列出所有（仅供查看）
- delete: 删除

正确的流程：
1. 用户要求分析邮件 → 调用 outlook 工具获取最新数据
2. 分析并发送邮件 
3. 用户确认"收到"后 → 再调用 save 保存到知识库"""
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "search", "get", "list", "delete"],
                    "description": "操作类型"
                },
                "key": {"type": "string", "description": "任务关键词"},
                "description": {"type": "string", "description": "任务描述"},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "执行步骤"},
                "params": {"type": "object", "description": "任务参数"},
                "result_summary": {"type": "string", "description": "结果摘要"},
                "keyword": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["action"]
        }
    
    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list")
        
        try:
            if action == "save":
                key = kwargs.get("key", "")
                description = kwargs.get("description", "")
                steps = kwargs.get("steps", [])
                params = kwargs.get("params", {})
                result_summary = kwargs.get("result_summary", "")
                
                if not key:
                    return "Error: key is required"
                
                # 检查是否已存在
                existing = self.store.find_task(key)
                if existing:
                    self.store.update_task(key, result_summary)
                    return f"Updated task: {key}"
                else:
                    self.store.add_task(key, description, steps, params, result_summary)
                    return f"Saved task: {key}"
            
            elif action == "search":
                keyword = kwargs.get("keyword", "")
                if not keyword:
                    return "Error: keyword is required"
                
                results = self.store.search_tasks(keyword)
                if not results:
                    return f"No tasks found for: {keyword}"
                
                output = [f"Found {len(results)} task(s):\n"]
                for t in results:
                    output.append(f"- {t['key']}: {t.get('description', '')[:50]}...")
                return "\n".join(output)
            
            elif action == "get":
                key = kwargs.get("key", "")
                if not key:
                    return "Error: key is required"
                
                task = self.store.find_task(key)
                if not task:
                    return f"Task not found: {key}"
                
                return f"""Task: {task['key']}
Description: {task.get('description', '')}
Steps: {', '.join(task.get('steps', []))}
Last run: {task.get('last_run', '')}
Use count: {task.get('use_count', 0)}
Result: {task.get('result_summary', '')[:200]}"""
            
            elif action == "list":
                tasks = self.store.get_all_tasks()
                if not tasks:
                    return "No tasks in knowledge base."
                
                output = [f"Tasks in knowledge base ({len(tasks)}):\n"]
                for t in tasks:
                    output.append(f"- {t['key']}: {t.get('description', '')[:50]}... (x{t.get('use_count', 0)})")
                return "\n".join(output)
            
            elif action == "delete":
                key = kwargs.get("key", "")
                if not key:
                    return "Error: key is required"
                
                if self.store.delete_task(key):
                    return f"Deleted task: {key}"
                return f"Task not found: {key}"
            
            else:
                return f"Unknown action: {action}"
        
        except Exception as e:
            return f"Error: {str(e)}"
