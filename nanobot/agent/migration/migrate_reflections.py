"""Migration script: Unify Dual-Brain Knowledge Base (Phase 42B [P1]).

This script idempotently migrates old metacognitive reflections from 
workspace/memory/reflections.json into the main Experience Bank 
(TaskKnowledgeStore + VectorMemory).
"""

import json
import logging
from pathlib import Path
import sys

from loguru import logger
from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.agent.vector_store import VectorMemory
from nanobot.agent.hybrid_retriever import hybrid_retrieve

logging.basicConfig(level=logging.INFO)

def migrate_reflections_to_experience_bank(workspace: Path) -> None:
    """Migrate items from reflections.json to Experience Bank."""
    reflections_file = workspace / "memory" / "reflections.json"
    if not reflections_file.exists():
        logger.info(f"Source file not found: {reflections_file}. No migration needed.")
        return

    try:
        data = json.loads(reflections_file.read_text(encoding="utf-8"))
        reflections = data.get("reflections", [])
    except Exception as e:
        logger.error(f"Failed to load reflections.json: {e}")
        return

    if not reflections:
        logger.info("No reflections found in source file. Migration complete.")
        return
        
    knowledge_store = TaskKnowledgeStore(workspace)
    vector_memory = VectorMemory(workspace)
    
    migrated_count = 0
    skipped_count = 0

    experiences = knowledge_store.get_experiences()

    for idx, ref in enumerate(reflections):
        trigger = ref.get("trigger", "").strip()
        failure_reason = ref.get("failure_reason", "").strip()
        corrective_action = ref.get("corrective_action", "").strip()
        
        if not trigger or not corrective_action:
            logger.warning(f"Skipping malformed reflection at index {idx}.")
            skipped_count += 1
            continue

        tactical_prompt = f"USER DIRECTIVE (Migrated): Avoid Mistake: {failure_reason}. Correction: {corrective_action}"

        # Idempotency check: see if we already have it in the Experience Bank.
        # Check by Jaccard similarity or Exact match first.
        already_exists = False
        for exp in experiences:
            exp_trigger = exp.get("trigger", "").strip()
            if not exp_trigger: continue
            
            # Substring checking
            if trigger.lower() in exp_trigger.lower() or exp_trigger.lower() in trigger.lower():
                # We consider this already handled if the tactical prompt also looks similar
                already_exists = True
                break

        if already_exists:
            logger.info(f"Skip (already_exists): '{trigger}'")
            skipped_count += 1
            continue

        # Add to Experience Bank
        knowledge_store.add_experience(
            context_trigger=trigger,
            tactical_prompt=tactical_prompt,
            action_type="correction"
        )
        # Vectorize
        content = f"Trigger: {trigger}\nPrompt: {tactical_prompt}"
        vector_memory.ingest_text(
            content,
            source=f"knowledge_experience:{trigger}",
            metadata={"trigger": trigger},
            clear_old_source=True
        )
        
        logger.info(f"Migrated: '{trigger}'")
        migrated_count += 1
        # Add to local cache for next iteration checks
        experiences.append({
            "trigger": trigger,
            "prompt": tactical_prompt,
            "action_type": "correction"
        })

    logger.info(f"Migration completed. Migrated: {migrated_count}, Skipped: {skipped_count}.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        workspace_path = Path(sys.argv[1])
    else:
        # Default fallback
        workspace_path = Path(".").resolve()
    
    logger.info(f"Starting Reflection to Experience Bank Migration on workspace: {workspace_path}")
    migrate_reflections_to_experience_bank(workspace_path)
