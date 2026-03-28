"""Internationalization support for user-facing messages.

Centralizes all strings shown to users, supporting zh (Chinese) and en (English).
Language is determined by config.agents.defaults.language (default: 'en').
"""


# All user-facing message templates
# Keys are message identifiers, values are dicts mapping language codes to templates.
# Templates may contain {placeholders} for str.format() substitution.
MESSAGES: dict[str, dict[str, str]] = {
    # --- Knowledge Workflow ---
    "knowledge_match_prompt": {
        "zh": (
            "💡 发现相似任务「{key}」已成功执行过。\n"
            "回复 **直接用** 使用知识库结果，或回复 **重新执行** 让 AI 重新处理。"
        ),
        "en": (
            "💡 Found a similar completed task '{key}'.\n"
            "Reply **use** to reuse the saved result, or **redo** to re-execute."
        ),
    },
    "knowledge_result_header": {
        "zh": "📋 从知识库获取的结果：\n\n{result}",
        "en": "📋 Result from knowledge base:\n\n{result}",
    },
    "knowledge_no_params": {
        "zh": (
            "⚠️ 知识库只保存了步骤名称，没有保存参数，无法直接执行。\n"
            "建议回复 **重新执行**，让 AI 根据当前情况重新处理。"
        ),
        "en": (
            "⚠️ The knowledge base only saved step names without parameters.\n"
            "Please reply **redo** to let the AI re-execute with current context."
        ),
    },
    "knowledge_execution_header": {
        "zh": "从知识库执行任务：\n\n{results}",
        "en": "Executing from knowledge base:\n\n{results}",
    },

    # --- Save Prompt ---
    "save_prompt": {
        "zh": (
            "\n\n💡 要把这个任务保存到知识库吗？"
            "（下次遇到相同任务可以直接复用）\n"
            "回复 **是** 保存，其他输入忽略。"
        ),
        "en": (
            "\n\n💡 Save this task to knowledge base? "
            "(Similar tasks can be reused next time)\n"
            "Reply **yes** to save, anything else to skip."
        ),
    },
    "save_confirmed": {
        "zh": "✅ 已保存到知识库！下次遇到相同任务时可以选择直接复用。",
        "en": "✅ Saved to knowledge base! Similar tasks can be reused next time.",
    },

    # --- Memory Consolidation ---
    "memory_consolidating": {
        "zh": "好的，正在帮你整合记忆...",
        "en": "OK, consolidating memory...",
    },

    # --- Session Commands ---
    "new_session": {
        "zh": "新会话已开始。记忆整合进行中。",
        "en": "New session started. Memory consolidation in progress.",
    },
    "help_text": {
        "zh": "🐈 nanobot 命令：\n/new — 开始新对话\n/tasks — 查看最近任务\n/kb — 知识库管理\n/memory — 记忆管理（导入/导出）\n/reload — 重载插件\n/help — 显示帮助",
        "en": "🐈 nanobot commands:\n/new — Start a new conversation\n/tasks — Show recent tasks\n/kb — Knowledge base management\n/memory — Memory management (import/export)\n/reload — Reload plugins\n/help — Show available commands",
    },
    "re_execute_no_previous": {
        "zh": "好的，将重新执行任务。请稍候...",
        "en": "OK, will re-execute the task. Please wait...",
    },

    # --- Errors ---
    "processing_error": {
        "zh": "抱歉，处理时遇到了错误：{error}",
        "en": "Sorry, I encountered an error: {error}",
    },
    "no_response": {
        "zh": "处理完成，但没有生成回复。",
        "en": "I've completed processing but have no response to give.",
    },
    "background_task_done": {
        "zh": "后台任务已完成。",
        "en": "Background task completed.",
    },

    # --- Tasks Command ---
    "tasks_header": {
        "zh": "📋 最近任务：",
        "en": "📋 Recent tasks:",
    },
    "tasks_empty": {
        "zh": "暂无任务记录。",
        "en": "No tasks recorded yet.",
    },

    # --- Skill Upgrade ---
    "skill_upgrade_prompt": {
        "zh": (
            "\n\n⭐ 这个任务已经成功执行了 {count} 次，"
            "要升级为常用 skill 吗？（升级后每次自动加载）\n"
            "回复 **升级** 确认，其他输入跳过。"
        ),
        "en": (
            "\n\n⭐ This task has been executed successfully {count} times. "
            "Upgrade to a permanent skill? (Auto-loaded in future sessions)\n"
            "Reply **upgrade** to confirm, anything else to skip."
        ),
    },
    "skill_upgrade_confirmed": {
        "zh": "✅ 已升级为常用 skill！以后每次启动都会自动加载。",
        "en": "✅ Upgraded to permanent skill! It will be auto-loaded in future sessions.",
    },

    # --- Knowledge Match with Stats ---
    "knowledge_match_with_stats": {
        "zh": (
            "💡 发现相似任务「{key}」（相似度 {score} | 成功率 {rate}%, 已执行 {count} 次）\n"
            "回复 **直接用** 使用知识库结果，或回复 **重新执行** 让 AI 重新处理。"
        ),
        "en": (
            "💡 Found similar task '{key}' (similarity: {score} | success rate: {rate}%, executed {count} times)\n"
            "Reply **use** to reuse the saved result, or **redo** to re-execute."
        ),
    },
    "knowledge_auto_adapt": {
        "zh": "🔄 发现相似任务「{key}」（相似度 {score}），正在参考其经验自动执行...",
        "en": "🔄 Found similar task '{key}' (similarity: {score}), auto-executing with adapted reference...",
    },

    # --- Knowledge Base Management (/kb) ---
    "kb_list_header": {
        "zh": "📚 知识库条目列表：\n",
        "en": "📚 Knowledge base entries:\n",
    },
    "kb_list_empty": {
        "zh": "📚 知识库为空，还没有保存过任务。",
        "en": "📚 Knowledge base is empty. No tasks saved yet.",
    },
    "kb_cleanup_result": {
        "zh": "🧹 知识库清理完成：合并了 {merged} 组重复条目，删除了 {deleted} 条。",
        "en": "🧹 Knowledge base cleanup done: merged {merged} duplicate groups, removed {deleted} entries.",
    },
    "kb_delete_success": {
        "zh": "🗑️ 已删除知识库条目「{key}」。",
        "en": "🗑️ Deleted knowledge base entry '{key}'.",
    },
    "kb_delete_not_found": {
        "zh": "⚠️ 未找到知识库条目「{key}」。",
        "en": "⚠️ Knowledge base entry '{key}' not found.",
    },
    "kb_help": {
        "zh": (
            "📚 知识库管理命令：\n"
            "  `/kb list` — 列出所有知识条目\n"
            "  `/kb cleanup` — 自动去重合并相似条目\n"
            "  `/kb delete <key>` — 删除指定条目\n"
            "  `/kb` — 显示此帮助"
        ),
        "en": (
            "📚 Knowledge base commands:\n"
            "  `/kb list` — List all knowledge entries\n"
            "  `/kb cleanup` — Auto-merge duplicate entries\n"
            "  `/kb delete <key>` — Delete a specific entry\n"
            "  `/kb` — Show this help"
        ),
    },

    # --- Memory Management (/memory) ---
    "memory_help": {
        "zh": (
            "🧠 记忆管理命令：\n"
            "  `/memory export` — 导出所有记忆为 JSON 文件\n"
            "  `/memory import <path>` — 从 JSON 文件导入记忆\n"
            "  `/memory` — 显示此帮助"
        ),
        "en": (
            "🧠 Memory management commands:\n"
            "  `/memory export` — Export all memory to a JSON file\n"
            "  `/memory import <path>` — Import memory from a JSON file\n"
            "  `/memory` — Show this help"
        ),
    },

    # --- Agent Loop Nudges ---
    "agent_continue_prompt": {
        "zh": "继续执行！如果需要提取附件、分析内容、发邮件，立即调用工具。不要只返回文字，立即行动！",
        "en": "Continue executing! If you need to extract attachments, analyze content, or send emails, call the tools immediately. Don't just return text — take action now!",
    },
    "agent_wait_nudge": {
        "zh": "你前一句只回复了确认的文字。这会导致动作中断！请你**立即调用实际工具**（如 exec, read_file 等）往下推进任务进程！！！",
        "en": "Your previous reply was only an acknowledgement. This will stall the task! You MUST **immediately call actual tools** (e.g., exec, read_file) to push the task forward!!!",
    },
    "agent_fake_completion_nudge": {
        "zh": "你声称已经完成了任务或发送了邮件，但实际上系统检测到你并没有调用任何工具！这是你的幻觉。请立刻调用正确的工具执行实际操作！",
        "en": "You claimed to have completed the task or sent an email, but the system detected NO tool calls! This is a hallucination. Call the correct tools NOW to execute the actual operation!",
    },

    # --- E4: Command Messages (previously hardcoded) ---
    "reload_success": {
        "zh": "🔄 插件已重载。当前动态工具: {tools}",
        "en": "🔄 Plugins reloaded. Active dynamic tools: {tools}",
    },
    "reload_no_tools": {
        "zh": "🔄 插件已重载。未发现动态工具。",
        "en": "🔄 Plugins reloaded. No dynamic tools found in plugins directory.",
    },
    "deep_consolidate_started": {
        "zh": "⏳ 深度记忆整合已启动，可能需要较长时间。",
        "en": "⏳ System Deep Memory Consolidation started. This may take a while.",
    },
    "export_success": {
        "zh": "✅ 记忆已导出到 `{path}`\n包含: MEMORY.md, preferences.json, {count} 个日志文件。",
        "en": "✅ Memory exported to `{path}`\nIncludes: MEMORY.md, preferences.json, {count} daily log files.",
    },
    "file_not_found": {
        "zh": "⚠️ 文件不存在: {path}",
        "en": "⚠️ File not found: {path}",
    },
    "json_parse_error": {
        "zh": "⚠️ JSON 解析失败: {error}",
        "en": "⚠️ JSON parse error: {error}",
    },
    "import_success": {
        "zh": "✅ 已导入: {items}",
        "en": "✅ Imported: {items}",
    },
    "import_empty": {
        "zh": "⚠️ 导入文件中没有可导入的内容。",
        "en": "⚠️ No importable content found in the file.",
    },
}


# Default language
_current_language: str = "en"


def set_language(lang: str) -> None:
    """Set the current language for user-facing messages."""
    global _current_language
    _current_language = lang if lang in ("zh", "en") else "en"


def get_language() -> str:
    """Get the current language."""
    return _current_language


def msg(msg_key: str, lang: str | None = None, **kwargs: str) -> str:
    """Get a localized message by key.

    Args:
        msg_key: Message identifier (must exist in MESSAGES dict).
        lang: Optional language override. Uses current language if None.
        **kwargs: Format arguments for the message template.

    Returns:
        Formatted message string. Falls back to English if key or language missing.
    """
    lang = lang or _current_language
    templates = MESSAGES.get(msg_key, {})
    template = templates.get(lang) or templates.get("en", f"[missing: {msg_key}]")
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError):
        return template
