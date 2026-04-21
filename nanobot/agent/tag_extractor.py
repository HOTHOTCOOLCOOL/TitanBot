"""Phase 49: IFCC Tag Extraction Engine."""

import re


def extract_mem_content(text: str) -> tuple[str, str | None]:
    """
    Extracts content inside <mem> tags for In-Flight Context Condensation.
    
    Args:
        text: The raw LLM response string.
        
    Returns:
        tuple[str, str | None]: The cleaned text (sans tags) and the extracted summary 
                                (truncated to 500 chars, parts joined by " | "), or None.
    """
    if not isinstance(text, str):
        return text, None

    matches = list(re.finditer(r"<mem>(.*?)</mem>", text, re.DOTALL | re.IGNORECASE))

    if not matches:
        # Fallback for unclosed tag: if <mem> without </mem> exists, treat text after <mem> as the summary
        if "<mem>" in text.lower():
            idx = text.lower().find("<mem>")
            summary = text[idx+5:].strip()
            clean_text = text[:idx].strip()
            if summary:
                return clean_text, summary[:500]
        return text, None

    summaries = []
    for match in matches:
        summaries.append(match.group(1).strip())

    # Remove all instances of <mem>...</mem>
    clean_text = re.sub(r"<mem>.*?</mem>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    summary_str = " | ".join(summaries)
    if len(summary_str) > 500:
        summary_str = summary_str[:500]

    return clean_text, summary_str
