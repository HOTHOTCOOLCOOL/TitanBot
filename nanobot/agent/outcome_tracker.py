"""Outcome tracking and implicit feedback for knowledge workflow."""

from loguru import logger
from nanobot.agent.task_knowledge import TaskKnowledgeStore

# Negative feedback patterns — if user's next message matches,
# the previous task is recorded as a failure.
_NEGATIVE_FEEDBACK = {
    # Chinese
    "不对", "错了", "重来", "重做", "不行", "有问题", "再试",
    # English
    "wrong", "incorrect", "redo", "try again", "not right", "fix it",
}


def is_negative_feedback(text: str) -> bool:
    """Check if user message implies the previous task failed."""
    t = text.strip().lower()
    return any(neg in t for neg in _NEGATIVE_FEEDBACK)


def record_outcome(knowledge_store: TaskKnowledgeStore | None, key: str, success: bool) -> None:
    """Record task outcome (success or failure) in knowledge base."""
    if not knowledge_store:
        return
    if success:
        knowledge_store.record_success(key)
        logger.info(f"KnowledgeWorkflow: recorded success for '{key}'")
    else:
        knowledge_store.record_failure(key)
        logger.info(f"KnowledgeWorkflow: recorded failure for '{key}'")


def silent_update_steps(knowledge_store: TaskKnowledgeStore | None, key: str, tool_calls: list[dict]) -> bool:
    """Silently update steps_detail for a task after successful execution.

    Called during implicit feedback (success path) to keep the knowledge
    base's step details current without prompting the user.

    Args:
        knowledge_store: The TaskKnowledgeStore instance.
        key: Task key.
        tool_calls: The tool calls from the latest execution.

    Returns:
        True if updated, False if key not found or no store.
    """
    if not knowledge_store or not tool_calls:
        return False
    result = knowledge_store.update_steps_detail(key, tool_calls)
    if result:
        logger.debug(f"KnowledgeWorkflow: silent steps update for '{key}'")
    return result
