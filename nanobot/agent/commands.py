"""Slash command handlers."""

__all__ = ["CommandHandler"]

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.agent.task_tracker import TaskTracker
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.memory import MemoryStore
from nanobot.agent.i18n import msg as i18n_msg

# Module-level constants for memory intent detection (avoid per-call allocation)
_MEMORY_TRIGGERS = [
    # Chinese
    "记住", "别忘了", "不要忘记", "保存这个", "记下来",
    "以后记得", "帮我记", "请记住",
    # English
    "remember this", "don't forget", "save this", "keep in mind",
    "note this down", "make a note", "remember that",
]

class CommandHandler:
    def __init__(self, workspace: Path, task_tracker: TaskTracker) -> None:
        self.workspace = workspace
        self.task_tracker = task_tracker

    async def dispatch_command(self, cmd: str, msg: InboundMessage, session: 'Session', kw: KnowledgeWorkflow, agent: "AgentLoop") -> OutboundMessage | None:
        from nanobot.agent.i18n import msg as i18n_msg
        from nanobot.utils.metrics import metrics
        from nanobot.session.manager import Session
        import asyncio

        if cmd == "/new":
            messages_to_archive = session.messages.copy()
            session.clear()
            agent.sessions.save(session)
            agent.sessions.invalidate(session.key)

            async def _consolidate_and_cleanup():
                temp_session = Session(key=session.key)
                temp_session.messages = messages_to_archive
                await agent.memory_manager.save_session_summary(temp_session)
                await agent.memory_manager.consolidate_memory(temp_session, archive_all=True)

            asyncio.create_task(_consolidate_and_cleanup())
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=i18n_msg("new_session"),
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=i18n_msg("help_text"),
            )
        if cmd == "/tasks":
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=self.format_tasks_list(),
            )
        if cmd == "/reload":
            from nanobot.agent.tool_setup import _register_dynamic_tools
            _register_dynamic_tools(agent)
            if agent._dynamic_tool_names:
                tools_list = ", ".join(agent._dynamic_tool_names)
                content = f"🔄 Plugins reloaded. Active dynamic tools: {tools_list}"
            else:
                content = "🔄 Plugins reloaded. No dynamic tools found in plugins directory."
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=content,
            )
        if cmd.startswith("/kb"):
            return self.handle_kb_command(cmd, msg, kw)
        if cmd.startswith("/memory"):
            return self.handle_memory_command(cmd, msg)
        if cmd == "/stats":
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=f"```\n{metrics.report()}\n```"
            )
        return None

    def format_tasks_list(self) -> str:
        """Format recent tasks for the /tasks command."""
        tasks = self.task_tracker.list_tasks(limit=10)
        if not tasks:
            return i18n_msg("tasks_empty")

        status_icons = {
            "completed": "✅",
            "failed": "❌",
            "running": "⏳",
            "created": "📝",
            "planning": "📝",
            "pending_review": "🔍",
            "cancelled": "⛔",
        }
        lines = [i18n_msg("tasks_header")]
        for t in tasks:
            status = t.status.value if hasattr(t.status, 'value') else str(t.status)
            icon = status_icons.get(status, "❓")
            time_str = t.created_at.strftime("%m-%d %H:%M") if t.created_at else ""
            key_display = t.key[:30] + ("..." if len(t.key) > 30 else "")
            lines.append(f"{icon} `{key_display}` — {status} ({time_str})")
        return "\n".join(lines)

    def handle_kb_command(
        self,
        cmd: str,
        msg: InboundMessage,
        kw: KnowledgeWorkflow,
    ) -> OutboundMessage:
        """Handle /kb subcommands: list, cleanup, delete <key>, or show help."""
        parts = cmd.split(maxsplit=2)
        sub = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            content = kw.format_kb_list()
        elif sub == "cleanup":
            content = kw.cleanup_knowledge()
        elif sub == "delete" and len(parts) > 2:
            key_to_delete = parts[2].strip()
            content = kw.delete_knowledge(key_to_delete)
        else:
            content = i18n_msg("kb_help")

        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        )

    def handle_memory_command(
        self,
        cmd: str,
        msg: InboundMessage,
    ) -> OutboundMessage:
        """Handle /memory subcommands: export, import, or show help."""
        parts = cmd.split(maxsplit=2)
        sub = parts[1] if len(parts) > 1 else ""

        if sub == "export":
            content = self.export_memory()
        elif sub == "import" and len(parts) > 2:
            file_path = parts[2].strip()
            content = self.import_memory(file_path)
        else:
            content = i18n_msg("memory_help")

        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        )

    def export_memory(self) -> str:
        """Export all memory (MEMORY.md + daily logs + preferences) to a JSON file."""
        memory = MemoryStore(self.workspace)
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "long_term_memory": memory.read_long_term(),
            "preferences": memory.read_preferences(),
            "daily_logs": {},
        }

        # Collect all daily log files
        for f in sorted(memory.memory_dir.glob("????-??-??.md")):
            date_key = f.stem
            export_data["daily_logs"][date_key] = f.read_text(encoding="utf-8")

        # Write to workspace
        export_path = self.workspace / "memory_export.json"
        export_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return f"✅ 记忆已导出到 `{export_path}`\n包含: MEMORY.md, preferences.json, {len(export_data['daily_logs'])} 个日志文件。"

    def import_memory(self, file_path: str) -> str:
        """Import memory from a JSON export file."""
        p = Path(file_path)
        if not p.exists():
            return f"⚠️ 文件不存在: {file_path}"

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return f"⚠️ JSON 解析失败: {e}"

        memory = MemoryStore(self.workspace)
        imported = []

        if ltm := data.get("long_term_memory"):
            existing = memory.read_long_term()
            if existing:
                memory.write_long_term(existing + "\n\n--- Imported ---\n" + ltm)
            else:
                memory.write_long_term(ltm)
            imported.append("MEMORY.md")

        if prefs := data.get("preferences"):
            memory.write_preferences(prefs)
            imported.append("preferences.json")

        if daily := data.get("daily_logs"):
            for date_key, content in daily.items():
                daily_file = memory.memory_dir / f"{date_key}.md"
                if not daily_file.exists():
                    daily_file.write_text(content, encoding="utf-8")
                    imported.append(f"{date_key}.md")

        if imported:
            return f"✅ 已导入: {', '.join(imported)}"
        return "⚠️ 导入文件中没有可导入的内容。"

    def detect_memory_intent(self, user_input: str) -> str:
        """Detect if the user wants the agent to remember something.

        Returns a system prompt hint if memory intent is detected, else empty string.
        """
        input_lower = user_input.lower()

        if any(t in input_lower for t in _MEMORY_TRIGGERS):
            return (
                "## Memory Intent Detected\n"
                "The user wants you to remember something. After completing their request, "
                "use the `memory` tool with action='store' to save the relevant information. "
                "Choose memory_type='fact' for persistent preferences/facts, or 'event' for one-time events."
            )
        return ""
