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
        "zh": "🐈 nanobot 命令：\n/new — 开始新对话\n/tasks — 查看最近任务\n/help — 显示帮助",
        "en": "🐈 nanobot commands:\n/new — Start a new conversation\n/tasks — Show recent tasks\n/help — Show available commands",
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
            "💡 发现相似任务「{key}」（成功率 {rate}%, 已执行 {count} 次）\n"
            "回复 **直接用** 使用知识库结果，或回复 **重新执行** 让 AI 重新处理。"
        ),
        "en": (
            "💡 Found similar task '{key}' (success rate: {rate}%, executed {count} times)\n"
            "Reply **use** to reuse the saved result, or **redo** to re-execute."
        ),
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
