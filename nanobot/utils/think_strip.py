"""S6: Reliable <think> tag stripping utility.

Reasoning models (DeepSeek-R1, Kimi, etc.) wrap their internal reasoning in
<think>...</think> tags. When the response is parsed by JSON loaders or displayed
to the user, these tags must be removed.

The simple regex `re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)` fails
when `</think>` is missing (unmatched opening tag) — the regex keeps everything.

This module provides a robust `strip_think_tags()` that handles:
1. Matched `<think>...</think>` pairs
2. Unmatched `<think>` (strips from `<think>` to end of string)
3. Multiple occurrences
"""

import re

__all__ = ["strip_think_tags"]

# Matched pair: <think>...</think>
_MATCHED_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Unmatched opening tag: <think> to end of string (no closing tag found)
_UNMATCHED_RE = re.compile(r"<think>.*$", re.DOTALL)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags (and their content) from text.

    Handles both matched pairs and unmatched opening tags.

    Args:
        text: Raw LLM response text.

    Returns:
        Cleaned text with think tags removed and whitespace stripped.
    """
    if "<think>" not in text:
        return text

    # First pass: remove matched <think>...</think> pairs
    result = _MATCHED_RE.sub("", text)

    # Second pass: if an unmatched <think> remains, strip from it to end
    if "<think>" in result:
        result = _UNMATCHED_RE.sub("", result)

    return result.strip()
