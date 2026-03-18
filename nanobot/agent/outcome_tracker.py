"""Outcome tracking and implicit feedback for knowledge workflow."""

import re
from loguru import logger
from nanobot.agent.task_knowledge import TaskKnowledgeStore

# Negative feedback patterns — if user's next message matches,
# the previous task is recorded as a failure.
_NEGATIVE_FEEDBACK_ZH = [
    "不对", "错了", "重来", "重做", "不行", "有问题", "再试",
]

# English patterns are compiled as word-boundary regexes to avoid substring false positives.
# E.g. "nothing wrong" should NOT trigger on "wrong".
_NEGATIVE_FEEDBACK_EN = [
    re.compile(r"\b" + kw + r"\b", re.IGNORECASE)
    for kw in ["wrong", "incorrect", "redo", "try again", "not right", "fix it"]
]

# Specific negated-positive phrases that look like feedback but are actually positive.
# "not right" IS negative, so we cannot generically block "not" prefix.
_NEGATED_POSITIVE_PHRASES = [
    "nothing wrong", "no problem", "no issue", "isn't wrong",
    "没有问题", "不是问题", "没什么问题",
]


def is_negative_feedback(text: str) -> bool:
    """Check if user message implies the previous task failed.

    Uses word-boundary matching for English and short-message heuristic
    for Chinese to reduce false positives (L1 fix).
    """
    t = text.strip()
    t_lower = t.lower()

    # Negation check: skip if the message is a negated-positive phrase
    if any(phrase in t_lower for phrase in _NEGATED_POSITIVE_PHRASES):
        return False

    # Chinese: only match in short messages (≤30 chars = typical single-line feedback)
    if len(t) <= 30:
        if any(neg in t for neg in _NEGATIVE_FEEDBACK_ZH):
            return True

    # English: word-boundary regex matching
    for pattern in _NEGATIVE_FEEDBACK_EN:
        if pattern.search(t_lower):
            return True

    return False


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
