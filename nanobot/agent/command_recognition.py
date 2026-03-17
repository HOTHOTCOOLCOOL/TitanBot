"""User command recognition for knowledge workflow."""

# All recognized forms of "use knowledge base" commands
_USE_COMMANDS = {
    # Chinese
    "直接用", "用知识库", "用", "使用知识库", "使用", "直接使用",
    # English
    "use", "reuse", "yes",
}

# All recognized forms of "re-execute" commands
_REDO_COMMANDS = {
    # Chinese
    "重新执行", "重新", "重新处理", "重做",
    # English
    "redo", "re-execute", "rerun", "again",
}

# All recognized forms of "save confirmation" commands
_SAVE_COMMANDS = {
    # Chinese
    "是", "好", "是的", "好的", "保存", "存",
    # English
    "yes", "ok", "save", "y",
}

# All recognized forms of "upgrade to skill" commands
_UPGRADE_COMMANDS = {
    # Chinese
    "升级", "升级skill", "升",
    # English
    "upgrade", "upgrade skill",
}


def is_use_command(text: str) -> bool:
    """Check if user input means 'use knowledge base result'."""
    return text.strip().lower() in _USE_COMMANDS


def is_redo_command(text: str) -> bool:
    """Check if user input means 're-execute the task'."""
    return text.strip().lower() in _REDO_COMMANDS


def is_save_confirm(text: str) -> bool:
    """Check if user input means 'confirm save to knowledge base'."""
    return text.strip().lower() in _SAVE_COMMANDS


def is_upgrade_command(text: str) -> bool:
    """Check if user input means 'confirm skill upgrade'."""
    return text.strip().lower() in _UPGRADE_COMMANDS
