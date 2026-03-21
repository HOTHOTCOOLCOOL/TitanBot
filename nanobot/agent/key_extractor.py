"""Key Extraction for Knowledge Workflow.

Extracts a concise task key from user requests via lightweight LLM call,
with a truncation-based fallback when no LLM provider is available.
"""

from typing import Any

from loguru import logger


async def extract_key(
    user_request: str,
    provider: Any = None,
    model: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Extract a task key from user request using a lightweight LLM call.

    The key should be:
    - Chinese: ≤50 characters
    - English: ≤200 characters
    - A concise description of the task's core intent

    Args:
        user_request: The raw user message.
        provider: LLM provider instance (optional).
        model: LLM model name (optional).
        history: Recent conversation history for coreference resolution.

    Returns:
        Extracted key string, or a truncated version of the request as fallback.
    """
    if not provider:
        return fallback_key(user_request)

    prompt_parts = [
        "Extract a concise task description from the user request below. ",
        "Rules:\n",
        "- If the request is in Chinese, output ≤50 Chinese characters\n",
        "- If the request is in English, output ≤200 English characters\n",
        "- Output ONLY the key text, nothing else\n",
        "- Focus on the core action and target\n",
        "- Do NOT output any reasoning, chain-of-thought, or explanation\n",
        "- Do NOT start with 'We need', 'The user', 'Let me', 'This is', 'Based on'\n",
        "- Just output the concise task description directly\n",
    ]

    if history:
        prompt_parts.append("\nRecent conversation history (for context and coreference resolution):\n")
        for m in history[-5:]:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                prompt_parts.append(f"[{role}]: {content[:500]}\n")
            elif isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                text_content = " ".join(text_parts)
                prompt_parts.append(f"[{role}]: {text_content[:500]}\n")

    prompt_parts.append(f"\nUser request: {user_request}\n\nKey:")
    prompt = "".join(prompt_parts)

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            max_tokens=100,
        )
        content = response.content or ""
        from nanobot.utils.think_strip import strip_think_tags
        content = strip_think_tags(content)

        # Reasoning models may output chain-of-thought as plain text (no <think> tags).
        # Take only the last non-empty line — that's typically the actual answer.
        lines = [ln.strip() for ln in content.strip().splitlines() if ln.strip()]
        key = lines[-1] if lines else ""
        key = key.strip('"').strip("'").strip()

        # Detect reasoning/chain-of-thought leakage (no <think> tags but still reasoning)
        if key and _is_reasoning_text(key):
            logger.warning(f"key_extractor: detected reasoning leakage, using fallback: '{key[:60]}...'")
            return fallback_key(user_request)

        # Enforce length limits to prevent verbose keys
        if key:
            key = _enforce_key_limit(key)
            logger.info(f"key_extractor: extracted key = '{key}'")
            return key
    except Exception as e:
        logger.warning(f"key_extractor: key extraction failed: {e}")

    return fallback_key(user_request)


# Phrases that indicate chain-of-thought reasoning leaked as plain text
_REASONING_PREFIXES = (
    "the user", "the last", "we need", "let me", "i need",
    "looking at", "based on", "the request", "the message",
    "this is", "it seems", "it appears", "so the",
    "okay", "alright", "first",
    # Prompt echo detection
    "extract a concise", "output only",
)


def _is_reasoning_text(key: str) -> bool:
    """Detect if the key looks like chain-of-thought reasoning rather than a real key."""
    key_lower = key.lower().strip()

    # Check for common reasoning prefixes
    for prefix in _REASONING_PREFIXES:
        if key_lower.startswith(prefix):
            return True

    # If key contains the original prompt instructions, it's reasoning
    if "task description" in key_lower or "user request" in key_lower:
        return True

    # If key is unreasonably long AND has multiple sentences, likely reasoning
    if len(key) > 80 and key.count('.') >= 2:
        return True

    return False


def _enforce_key_limit(key: str) -> str:
    """Enforce character limits on extracted keys."""
    cjk_count = sum(1 for c in key if '\u4e00' <= c <= '\u9fff')
    limit = 50 if cjk_count > len(key) * 0.3 else 100
    if len(key) > limit:
        key = key[:limit].strip()
    return key


def fallback_key(user_request: str) -> str:
    """Fallback key extraction without LLM — simple truncation."""
    cjk_count = sum(1 for c in user_request if '\u4e00' <= c <= '\u9fff')
    limit = 50 if cjk_count > len(user_request) * 0.3 else 100
    return user_request[:limit].strip()


