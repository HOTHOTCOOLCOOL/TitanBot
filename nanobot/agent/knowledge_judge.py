"""Knowledge Judge & Persistence for Knowledge Workflow.

Handles LLM-based knowledge quality evaluation (ADD/MERGE/DISCARD),
save/merge/create operations, and retrieval-time adaptation.
"""

import json
from typing import Any

from loguru import logger

from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.agent.prompt_formatter import format_few_shot_prompt
from nanobot.utils.metrics import metrics


async def evaluate_and_structure_knowledge(
    key: str,
    request: str,
    steps: list[dict],
    result: str,
    provider: Any = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Evaluate new knowledge using LLM and structure it into formal fields.

    Returns a dict:
        decision: "ADD", "MERGE", or "DISCARD"
        triggers: list of strings
        tags: list of strings
        anti_patterns: list of strings
        confidence: float (0.0 - 1.0)
    """
    default_result: dict[str, Any] = {
        "decision": "ADD",
        "triggers": [key],
        "tags": [],
        "anti_patterns": [],
        "confidence": 0.8,
    }

    if not provider:
        return default_result

    task_str = f"Task Key: {key}\nOriginal Request: {request}\nSteps: {steps}\nResult: {result}"

    prompt = f"""
You are the Knowledge Management Judge for a personal AI assistant.
Your job is to evaluate a newly completed workflow and structure it for the Knowledge Base.

Workflow Data:
{task_str}

Tasks:
1. DECISION: Decide if this knowledge should be ADDed as new, MERGEd with existing, or DISCARDed entirely (if trivial, completely erroneous, or empty).
2. TRIGGERS: Extract 2-3 short, distinct trigger phrases the user might say next time to request this.
3. TAGS: 1-3 broad categorization tags (e.g., 'email', 'system', 'research').
4. ANTI-PATTERNS: 1-2 warnings or mistakes to avoid when running this workflow in the future (based on the steps or result). If none, empty array.
5. CONFIDENCE: Give a confidence score (0.0 to 1.0) on how reliable and generalizable this workflow is.

Return your evaluation EXACTLY as a JSON object, with no markdown formatting around it:
{{
    "decision": "ADD|MERGE|DISCARD",
    "triggers": ["trigger1", "trigger2"],
    "tags": ["tag1", "tag2"],
    "anti_patterns": ["anti_pattern1"],
    "confidence": 0.9
}}
"""
    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            max_tokens=300,
        )
        content = response.content or ""
        from nanobot.utils.think_strip import strip_think_tags
        content = strip_think_tags(content)
        content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        return {**default_result, **parsed}
    except Exception as e:
        logger.warning(f"Knowledge Judge failed, using defaults: {e}")
        metrics.increment("knowledge_judge_fallback_count")
        return default_result


async def save_to_knowledge(
    key: str,
    steps: list[dict],
    user_request: str,
    knowledge_store: TaskKnowledgeStore | None,
    provider: Any = None,
    model: str | None = None,
    result_summary: str = "",
) -> bool:
    """Save or update a task in the knowledge base.

    Strategy (P0 — auto-merge):
    1. Exact key match → merge into existing entry (version++)
    2. Similar key found → merge into similar entry (avoid duplicates)
    3. No match → create new entry

    Args:
        key: Task key (extracted by extract_key).
        steps: List of tool call dicts [{tool, args}, ...].
        user_request: Original user request text.
        knowledge_store: The TaskKnowledgeStore instance.
        provider: LLM provider (optional).
        model: LLM model name (optional).
        result_summary: Summary of the task result.

    Returns:
        True if saved successfully.
    """
    if not knowledge_store:
        logger.warning("knowledge_judge: no knowledge store available")
        return False

    try:
        judge_result = await evaluate_and_structure_knowledge(
            key, user_request, steps, result_summary,
            provider=provider, model=model,
        )
        decision = judge_result.get("decision", "ADD")

        if decision == "DISCARD":
            logger.info(f"knowledge_judge: discarded new knowledge for '{key}'")
            return True

        triggers = judge_result.get("triggers", [])
        tags = judge_result.get("tags", [])
        anti_patterns = judge_result.get("anti_patterns", [])
        confidence = judge_result.get("confidence", 1.0)

        # 1. Exact key match → merge
        existing = knowledge_store.find_task(key)
        if existing or decision == "MERGE":
            target_key = existing.get("key") if existing else key
            if not existing and decision == "MERGE":
                similar = knowledge_store.find_similar_task(key)
                if similar:
                    target_key = similar.get("key", key)

            knowledge_store.merge_task(
                existing_key=target_key,
                new_steps=steps,
                new_result_summary=result_summary or "Task completed",
                new_steps_detail=steps,
                new_triggers=triggers,
                new_tags=tags,
                new_anti_patterns=anti_patterns,
                new_confidence=confidence,
            )
            logger.info(f"knowledge_judge: merged for key='{target_key}'")
            return True

        # 2. Similar key match → merge
        similar = knowledge_store.find_similar_task(key)
        if similar:
            similar_key = similar.get("key", "")
            knowledge_store.merge_task(
                existing_key=similar_key,
                new_steps=steps,
                new_result_summary=result_summary or "Task completed",
                new_steps_detail=steps,
                new_triggers=triggers,
                new_tags=tags,
                new_anti_patterns=anti_patterns,
                new_confidence=confidence,
            )
            logger.info(f"knowledge_judge: merged (similar) '{key}' → '{similar_key}'")
            return True

        # 3. No match → create new
        knowledge_store.add_task(
            key=key,
            description=user_request[:100],
            steps=steps,
            params={},
            result_summary=result_summary or "Task completed",
            triggers=triggers,
            tags=tags,
            anti_patterns=anti_patterns,
            confidence=confidence,
        )
        logger.info(f"knowledge_judge: saved new knowledge for key='{key}'")
        return True
    except Exception as e:
        logger.error(f"knowledge_judge: save failed: {e}")
        metrics.increment("knowledge_save_error_count")
        return False


async def adapt_knowledge(
    match: dict,
    current_request: str,
    provider: Any = None,
    model: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Adapt a retrieved knowledge entry into a tailored few-shot prompt for the current context.

    Uses a lightweight LLM call to rewrite the generic steps from the knowledge
    base into a specific, actionable reference for the current request.

    Args:
        match: The matched knowledge entry dict.
        current_request: The current user request text.
        provider: LLM provider instance (optional).
        model: LLM model name (optional).
        history: Recent conversation history.

    Returns:
        Adapted prompt string, or generic few-shot prompt as fallback.
    """
    if not provider:
        return format_few_shot_prompt(match)

    key = match.get("key", "")
    steps_detail = match.get("last_steps_detail", [])
    steps = match.get("steps", [])

    if not steps_detail and not steps:
        return ""

    generic_prompt = format_few_shot_prompt(match)

    prompt_parts = [
        f"You are given a previously successful workflow for the task: '{key}'.\n",
        "Adapt this generic workflow to fit the NEW current user request.\n",
        "Rules:\n",
        "- Extract specific parameters (paths, names, URLs, etc.) from the new request or history.\n",
        "- Replace the old parameters in the generic workflow with the new ones.\n",
        "- Keep the output concise, focusing purely on the modified steps.\n",
        "- Output a markdown formatted reference list of steps.\n\n",
    ]

    if history:
        prompt_parts.append("Recent conversation history (for additional context):\n")
        for m in history[-5:]:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                prompt_parts.append(f"[{role}]: {content[:500]}\n")
            elif isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                text_content = " ".join(text_parts)
                prompt_parts.append(f"[{role}]: {text_content[:500]}\n")

    prompt_parts.append(f"\nUser request: {current_request}\n")
    prompt_parts.append(f"\nGeneric workflow to adapt:\n{generic_prompt}\n\nAdapted workflow:")
    prompt = "".join(prompt_parts)

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            max_tokens=300,
        )
        content = response.content or ""
        from nanobot.utils.think_strip import strip_think_tags
        content = strip_think_tags(content)
        adapted = content.strip()
        if adapted:
            logger.info(f"knowledge_judge: successfully adapted knowledge for '{key}'")
            return f"## Contextual Reference: Adapted from '{key}'\n\n{adapted}"
    except Exception as e:
        logger.warning(f"knowledge_judge: adaptation failed: {e}")

    return generic_prompt
