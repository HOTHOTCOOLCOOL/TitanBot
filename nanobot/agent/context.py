"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.vector_store import VectorMemory


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "KNOWLEDGE.md"]
    
    def __init__(self, workspace: Path, language: str = "zh"):
        self.workspace = workspace
        self.language = language
        self.memory = MemoryStore(workspace)
        self.vector_memory = VectorMemory(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity
        parts.append(self._get_identity())
        
        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
CRITICAL: If a task matches a Skill listed below, you MUST use the read_file tool to read its SKILL.md BEFORE attempting to write custom bash/python scripts.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """Get the core identity section."""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. 

You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks
- Access Outlook emails

## ⚠️ 重要：消息发送工具的区别

**message 工具**：
- 只用于发送到 飞书/微信/Telegram 等聊天工具
- 不能发送到外部邮箱！

**outlook.send_email 行动**：
- 用于发送到外部邮箱（如 DAVIDMSN@HOTMAIL.COM）
- 用户要求"发邮件"或"发送到邮箱"时，必须使用 outlook 工具的 send_email 行动！
- 绝对不要用 message 工具发送到邮箱！

## Current Time
{now} ({tz})

**日期理解提示**: 日报通常在次日发送。"昨天的销售数据" = 搜索今天的报告；"今天的report" = 昨天的业绩。请结合 KNOWLEDGE.md 中的业务规则判断应搜索哪天的邮件。

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Core Preferences (L1 Memory): {workspace_path}/memory/preferences.json
- Long-term memory (L2 Archive): {workspace_path}/memory/MEMORY.md (Use MemorySearchTool to retrieve details)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable)
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to simple questions or greetings, reply directly with text.
BUT when user asks you to DO something (search, analyze, send, execute), you MUST use tools!
- Want to know today's emails? Use outlook tool
- Want to analyze attachments? Use attachment_analyzer tool  
- Want to send email? Use outlook.send_email action
- Want to read files? Use read_file tool
- ⚠️ MISSING SKILLS? If the user asks for something outside your current skills (like creating a PPT, posting to social media), DO NOT simply say you can't or suggest they do it manually. Instead, use `exec` tool to run `npx clawhub search <keyword>` to find and install a skill!

**⚠️ CRITICAL INSTRUCTION FOR REASONING MODELS:**
When you decide to start a task (e.g., "I will start making the PPT, please wait"), **YOU MUST CALL THE TOOLS IN THE SAME TURN**. 
DO NOT simply reply with "稍等" (please wait) without any tool calls! If you only return text, the system will pause and wait for the user, and the task will NOT start. 
If you want to inform the user to wait, you can do so, but NEVER FORGET to include the actual tool calls (e.g., `exec`, `read_file`) in the exact same response!

NEVER say "I have sent the email," "Task completed," or "✅ 已发送" unless you have ACTUALLY used the corresponding tools (like outlook) in this exact turn. DO NOT hallucinate tool execution.

NEVER just describe what you would do - actually call the tools and DO it!

Always be helpful, accurate, and concise. When using tools, think step by step: what you know, what you need, and why you chose this tool.
When remembering something important, write to {workspace_path}/memory/MEMORY.md. Background processes will later distill it into preferences.json.
To recall past events, rely on the MemorySearchTool or grep {workspace_path}/memory/HISTORY.md.

## ⚠️ 语言要求 / Language
{self._get_language_instruction()}"""
    
    def _get_language_instruction(self) -> str:
        """Get the language instruction based on configured language."""
        if self.language == "zh":
            return (
                "请始终使用中文回复用户。用户使用中文提问时，必须用中文回答。"
                "包括分析结果、报告摘要、错误提示等所有输出内容都应使用中文。"
            )
        return "Respond in the same language as the user's message."

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.
            channel: Current channel (telegram, feishu, etc.).
            chat_id: Current chat/user ID.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names)
        
        # Inject VectorMemory RAG context
        try:
            rag_results = self.vector_memory.search(current_message, top_k=3)
            if rag_results:
                rag_context = self.vector_memory.format_results_for_context(rag_results)
                if rag_context:
                    system_prompt += f"\n\n{rag_context}"
        except Exception as e:
            pass  # Fail gracefully if vector search fails

        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list. Handles special image paths.
        
        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.
        
        Returns:
            Updated message list.
        """
        content: str | list[dict[str, Any]] = result
        user_multimodal_message = None

        # Intercept special screenshot payload: tool returns `__IMAGE__:/path/to/image.jpg`
        if isinstance(result, str) and result.startswith("__IMAGE__:"):
            path_part = result.split("__IMAGE__:", 1)[1]
            path = path_part.split(" | ANCHORS:", 1)[0].strip()
            anchor_text = ""
            if " | ANCHORS:" in path_part:
                anchor_text = path_part.split(" | ANCHORS:", 1)[1].strip()
                
            p = Path(path)
            if p.is_file():
                import mimetypes
                import base64
                mime, _ = mimetypes.guess_type(path)
                if mime and mime.startswith("image/"):
                    b64 = base64.b64encode(p.read_bytes()).decode()
                    content = f"Screenshot captured successfully. Path: {path}"
                    
                    user_content: list[dict[str, Any]] = [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    ]
                    if anchor_text:
                        user_content.append({"type": "text", "text": f"Evaluate the screenshot and continue the task. CRITICAL: When interacting with an element listed below, you MUST use the `ui_index` parameter instead of x and y coordinates! Do NOT hallucinate coordinates.\n\nANCHORS:\n{anchor_text}"})
                    else:
                        user_content.append({"type": "text", "text": "Evaluate the screenshot and continue the task."})
                        
                    user_multimodal_message = {
                        "role": "user",
                        "content": user_content
                    }

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": content
        })
        
        if user_multimodal_message:
            messages.append(user_multimodal_message)
            
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        
        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).
        
        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant"}

        # Some backends reject empty text blocks, but require content explicitly set to None or empty.
        # We set it to None if empty so Litellm/OpenAI serializes it as null.
        if content:
            msg["content"] = content
        else:
            msg["content"] = None

        if tool_calls:
            msg["tool_calls"] = tool_calls

        # Include reasoning content when provided (required by some thinking models)
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages
