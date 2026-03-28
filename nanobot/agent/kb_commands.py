"""Knowledge Base Management Commands for knowledge workflow."""

from typing import Any
from loguru import logger
from nanobot.agent.i18n import msg
from nanobot.agent.task_knowledge import TaskKnowledgeStore, tokenize_key


def format_kb_list(knowledge_store: TaskKnowledgeStore | None, lang: str | None = None) -> str:
    """Format a human-readable list of all knowledge base entries."""
    if not knowledge_store:
        return msg("kb_list_empty", lang=lang)

    tasks = knowledge_store.get_all_tasks()
    if not tasks:
        return msg("kb_list_empty", lang=lang)

    lines = [msg("kb_list_header", lang=lang)]
    for i, t in enumerate(tasks, 1):
        key = t.get("key", "?")
        version = t.get("version", 1)
        sc = t.get("success_count", 0)
        fc = t.get("fail_count", 0)
        total = sc + fc
        rate = int(sc / total * 100) if total > 0 else 100
        use_count = t.get("use_count", 0)
        lines.append(
            f"{i}. **{key}** — v{version} | "
            f"成功率 {rate}% | 使用 {use_count} 次"
        )
    return "\n".join(lines)


def delete_knowledge(knowledge_store: TaskKnowledgeStore | None, key: str, lang: str | None = None, vector_memory: Any = None) -> str:
    """Delete a knowledge base entry by key. Returns user-facing message."""
    if not knowledge_store:
        return msg("kb_delete_not_found", lang=lang, key=key)
    if knowledge_store.delete_task(key):
        if vector_memory:
            vector_memory.delete_by_source(f"knowledge:{key}")
        logger.info(f"KnowledgeWorkflow: deleted knowledge entry '{key}'")
        return msg("kb_delete_success", lang=lang, key=key)
    return msg("kb_delete_not_found", lang=lang, key=key)


from typing import Any

def cleanup_knowledge(knowledge_store: TaskKnowledgeStore | None, lang: str | None = None, vector_memory: Any = None) -> str:
    """Find and merge duplicate/similar knowledge base entries.

    Returns a user-facing message with cleanup stats.
    """
    if not knowledge_store:
        return msg("kb_cleanup_result", lang=lang, merged="0", deleted="0")

    tasks = knowledge_store.get_all_tasks()
    merged_count = 0
    deleted_keys: set[str] = set()

    # Compare each pair; skip already-deleted entries
    for i, t1 in enumerate(tasks):
        k1 = t1.get("key", "")
        if k1 in deleted_keys:
            continue
        for t2 in tasks[i + 1:]:
            k2 = t2.get("key", "")
            if k2 in deleted_keys:
                continue
            # Use tokenize similarity
            w1 = set(tokenize_key(k1))
            w2 = set(tokenize_key(k2))
            if not w1 or not w2:
                continue
            score = len(w1 & w2) / len(w1 | w2)
            if score >= 0.5:
                # Merge t2 into t1 (keep the one with more successes)
                keep, discard = (t1, t2) if t1.get("success_count", 0) >= t2.get("success_count", 0) else (t2, t1)
                knowledge_store.merge_task(
                    keep.get("key", ""),
                    new_steps=discard.get("steps"),
                    new_result_summary=discard.get("result_summary"),
                )
                knowledge_store.delete_task(discard.get("key", ""))
                deleted_keys.add(discard.get("key", ""))
                merged_count += 1
                logger.info(
                    f"KnowledgeWorkflow cleanup: merged '{discard.get('key')}' "
                    f"into '{keep.get('key')}'"
                )

    if merged_count > 0 and vector_memory:
        vector_memory.ingest_knowledge_tasks()

    return msg(
        "kb_cleanup_result", lang=lang,
        merged=str(merged_count), deleted=str(len(deleted_keys)),
    )
