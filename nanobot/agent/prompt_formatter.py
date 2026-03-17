"""Prompt formatting for knowledge workflow."""

from nanobot.agent.i18n import msg


def format_match_prompt(match: dict, lang: str | None = None) -> str:
    """Format the knowledge-match prompt for the user."""
    key = match.get("key", "unknown")
    return msg("knowledge_match_prompt", lang=lang, key=key)


def format_save_prompt(lang: str | None = None) -> str:
    """Format the save-to-knowledge-base prompt."""
    return msg("save_prompt", lang=lang)


def format_save_confirmed(lang: str | None = None) -> str:
    """Format the save-confirmed message."""
    return msg("save_confirmed", lang=lang)


def format_skill_upgrade_prompt(match: dict, lang: str | None = None) -> str:
    """Format the skill upgrade suggestion prompt."""
    return msg("skill_upgrade_prompt", lang=lang,
               key=match.get("key", ""),
               count=str(match.get("success_count", 0)))


def get_match_stats(match: dict) -> dict:
    """Get formatted stats for a knowledge match (for display in prompts)."""
    success = match.get("success_count", 0)
    fail = match.get("fail_count", 0)
    total = success + fail
    rate = (success / total * 100) if total > 0 else 100
    return {
        "success_count": success,
        "fail_count": fail,
        "total": total,
        "rate": rate,
        "use_count": match.get("use_count", 0),
    }


def get_knowledge_result(match: dict, lang: str | None = None) -> str:
    """Format and return the stored result of a matched knowledge entry.

    If the match has a result_summary, returns that.
    Otherwise returns step names.
    """
    result_summary = match.get("result_summary", "")
    if result_summary:
        return msg("knowledge_result_header", lang=lang, result=result_summary)

    # Fallback: list the steps
    steps = match.get("steps", [])
    if steps:
        step_names = []
        for s in steps:
            if isinstance(s, dict):
                step_names.append(s.get("tool", str(s)))
            else:
                step_names.append(str(s))
        steps_text = "\n".join(f"  {i+1}. {name}" for i, name in enumerate(step_names))
        return msg("knowledge_result_header", lang=lang, result=steps_text)

    return msg("knowledge_no_params", lang=lang)


def format_few_shot_prompt(match: dict) -> str:
    """Generate a few-shot reference prompt from a high-success knowledge entry.

    This is injected into the system message when a user chooses "redo" on a
    matched task, giving the local LLM a reference path to follow.

    Returns:
        A formatted prompt string, or empty string if no useful detail available.
    """
    key = match.get("key", "")
    steps_detail = match.get("last_steps_detail", [])
    steps = match.get("steps", [])
    result_summary = match.get("result_summary", "")
    success_count = match.get("success_count", 0)
    use_count = match.get("use_count", 0)

    if not steps_detail and not steps:
        return ""

    lines = [
        f"## Reference: Previously successful execution of '{key}'",
        f"(Success: {success_count}/{use_count} executions)",
        "",
    ]

    if steps_detail:
        lines.append("### Steps taken:")
        for i, step in enumerate(steps_detail, 1):
            tool = step.get("tool", "unknown")
            args = step.get("args", {})
            result = step.get("result", "")
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if isinstance(args, dict) else str(args)
            lines.append(f"{i}. `{tool}({args_str})`")
            if result:
                lines.append(f"   → {result[:200]}")
    elif steps:
        lines.append("### Tools used:")
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                lines.append(f"{i}. `{step.get('tool', str(step))}`")
            else:
                lines.append(f"{i}. `{step}`")

    if result_summary:
        lines.extend(["", f"### Final result: {result_summary}"])

    lines.extend([
        "",
        "Use this as a reference. Adapt parameters to the current request.",
    ])
    return "\n".join(lines)
