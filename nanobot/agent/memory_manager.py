"""Memory management and consolidation."""

import asyncio
import json
import json_repair
import time

from pathlib import Path
from loguru import logger
from nanobot.agent.memory import MemoryStore
from nanobot.agent.personalization import MemoryDistiller
from nanobot.providers.base import LLMProvider
from nanobot.agent.vector_store import VectorMemory
from nanobot.session.manager import Session

class MemoryManager:
    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        memory_window: int,
        vector_memory: VectorMemory | None = None
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.memory_window = memory_window
        self.vector_memory = vector_memory
        # L4/C1: Prevents concurrent consolidation tasks from corrupting session state / MEMORY.md
        self._consolidation_lock = asyncio.Lock()

    async def consolidate_memory(self, session: Session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md.

        Args:
            archive_all: If True, clear all messages and reset session (for /new command).
                       If False, only write to files without modifying session.
        """
        async with self._consolidation_lock:  # L4/C1: serialize consolidation
            await self._consolidate_memory_inner(session, archive_all)

    async def _consolidate_memory_inner(self, session: Session, archive_all: bool = False) -> None:
        """Inner consolidation implementation (called under lock)."""
        memory = MemoryStore(self.workspace)

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(f"Memory consolidation (archive_all): {len(session.messages)} total messages archived")
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                logger.debug(f"Session {session.key}: No consolidation needed (messages={len(session.messages)}, keep={keep_count})")
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                logger.debug(f"Session {session.key}: No new messages to consolidate (last_consolidated={session.last_consolidated}, total={len(session.messages)})")
                return

            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return
            logger.info(f"Memory consolidation started: {len(session.messages)} total, {len(old_messages)} new to consolidate, {keep_count} keep")

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")
        conversation = "\n".join(lines)

        # B5: Skip LLM call if conversation is empty (all messages had no content)
        if not conversation.strip():
            logger.debug("Memory consolidation: no content in messages, skipping LLM call")
            return

        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly three keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. ONLY add durable FACTS: user preferences, personal info, project context, technical decisions, tools/services used. Do NOT add one-time events or task results. If nothing new is a durable fact, return the existing content unchanged.

3. "daily_log": A brief summary of notable one-time events from the conversation (tasks completed, errors encountered, emails analyzed, etc.). One line per event. Return empty string if nothing notable.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            text = (response.content or "").strip()
            # S6: Strip <think> tags reliably before parsing JSON
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if not text:
                logger.warning("Memory consolidation: LLM returned empty response, skipping")
                return
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            if not isinstance(result, dict):
                logger.warning(f"Memory consolidation: unexpected response type, skipping. Response: {text[:200]}")
                return

            if entry := result.get("history_entry"):
                memory.append_history(entry)
                # Auto-ingest new history entry into vector store
                if self.vector_memory:
                    self.vector_memory.ingest_text(entry, source="history")

                # Append to evicted context buffer for Virtual Paging (keep last ~2000 chars)
                try:
                    current_evicted = session.evicted_context or ""
                    now_str = time.strftime("%Y-%m-%d %H:%M")
                    new_evicted = f"[{now_str}] {entry}\n"
                    combined = (current_evicted + new_evicted).strip()
                    if len(combined) > 2000:
                        combined = combined[-2000:]
                        if "\n" in combined:
                            combined = combined.split("\n", 1)[1]
                    session.evicted_context = combined
                except Exception as e:
                    logger.warning(f"Failed to update evicted context: {e}")

            if update := result.get("memory_update"):
                if isinstance(update, dict):
                    update = __import__("json").dumps(update, ensure_ascii=False, indent=2)
                elif not isinstance(update, str):
                    update = str(update)
                if update != current_memory:
                    memory.write_long_term(update)

            if daily := result.get("daily_log"):
                if daily.strip():
                    memory.append_daily_log(daily.strip())
                    # Auto-ingest new daily log entry into vector store
                    today_str = time.strftime("%Y-%m-%d")
                    if self.vector_memory:
                        self.vector_memory.ingest_text(
                            daily.strip(),
                            source=f"daily_log:{today_str}",
                            metadata={"date": today_str}
                        )

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            logger.info(f"Memory consolidation done: {len(session.messages)} messages, last_consolidated={session.last_consolidated}")
            
            # Fire an asynchronous distillation to extract L1 core preferences
            # Only distill if the L2 memory actually changed 
            if memory_changed := result.get("memory_update"):
                if memory_changed != current_memory:
                    distiller = MemoryDistiller(memory, self.provider, self.model)
                    from nanobot.agent.commands import _safe_create_task
                    _safe_create_task(distiller.distill_preferences(), name="distill_preferences")
                    
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")

    async def deep_consolidate(self) -> None:
        """Deep consolidation of HISTORY.md and MEMORY.md: dedup, generalize, and demote stale entries."""
        async with self._consolidation_lock:  # C1: share lock with regular consolidation
            await self._deep_consolidate_inner()

    async def _deep_consolidate_inner(self) -> None:
        """Inner deep consolidation implementation (called under lock)."""
        logger.info("Starting deep memory consolidation...")
        # read existing memory and history
        memory = MemoryStore(self.workspace)
        current_memory = memory.read_long_term()
        
        history_file = self.workspace / "memory" / "HISTORY.md"
        if not history_file.exists():
            current_history = ""
        else:
            current_history = history_file.read_text(encoding="utf-8")

        # To avoid blowing up context, only take the last ~50000 chars of history
        if len(current_history) > 50000:
            current_history = "..." + current_history[-50000:]

        prompt = f"""You are a Memory Optimization Assistant. Perform a slow-path deep consolidation of the following memory systems:

1. Reorganize and deduplicate information.
2. Form higher-level abstractions from repeated patterns.
3. Demote or remove stale or obsolete entries.

## Current Long-term Memory (MEMORY.md)
{current_memory or '(empty)'}

## Recent History (HISTORY.md)
{current_history or '(empty)'}

Return ONLY a valid JSON object with a single key "memory_update" containing the optimized and rewritten long-term memory content (which will completely REPLACE the old MEMORY.md). Format the content using clear markdown headers. Maintain all critical facts and preferences, but make it concise and well-structured."""
        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.2, # Low temp for consistency
            )
            text = (response.content or "").strip()
            # S6: Strip <think> tags reliably
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            
            if isinstance(result, dict) and "memory_update" in result:
                new_memory = result["memory_update"]
                if isinstance(new_memory, dict):
                    new_memory = __import__("json").dumps(new_memory, ensure_ascii=False, indent=2)
                elif not isinstance(new_memory, str):
                    new_memory = str(new_memory)
                
                if new_memory and new_memory != current_memory:
                    memory.write_long_term(new_memory)
                    logger.info("Deep memory consolidation completed successfully.")
                    
                    # Fire asynchronous distillation to keep L1 preferences in sync
                    distiller = MemoryDistiller(memory, self.provider, self.model)
                    from nanobot.agent.commands import _safe_create_task
                    _safe_create_task(distiller.distill_preferences(), name="deep_distill_preferences")
                    
                    # P1: Extract Knowledge Graph Entity-Relation Triples
                    try:
                        from nanobot.agent.knowledge_graph import KnowledgeGraph
                        kg = KnowledgeGraph(self.workspace)
                        _safe_create_task(kg.extract_triples(self.provider, self.model, str(new_memory)), name="kg_extraction")
                    except Exception as e:
                        logger.error(f"Failed to start Knowledge Graph extraction: {e}")
        except Exception as e:
            logger.error(f"Deep memory consolidation failed: {e}")

    async def save_session_summary(self, session: Session) -> None:
        """Session-end hook: save a brief summary of the session to daily log.

        Called before memory consolidation when /new is invoked.
        Inspired by mem9's before_reset lifecycle hook.
        """
        if not session.messages or len(session.messages) < 4:
            return  # Too short to summarize

        memory = MemoryStore(self.workspace)
        try:
            # Build a lightweight summary from the session messages
            topics = []
            for m in session.messages:
                content = m.get("content", "")
                if not content or m.get("role") != "user":
                    continue
                preview = content[:80].strip()
                if preview:
                    topics.append(preview)

            if not topics:
                return

            now_str = time.strftime("%Y-%m-%d %H:%M")
            summary = f"[{now_str}] 会话结束 — 话题: {'; '.join(topics[:5])}"
            memory.append_daily_log(summary)
            logger.info(f"Session summary saved to daily log: {summary[:80]}")

            # Also ingest into vector store for future semantic search
            if self.vector_memory:
                today_str = time.strftime("%Y-%m-%d")
                self.vector_memory.ingest_text(
                    summary,
                    source=f"daily_log:{today_str}",
                    metadata={"date": today_str},
                )
        except Exception as e:
            logger.error(f"Session summary save failed: {e}")
