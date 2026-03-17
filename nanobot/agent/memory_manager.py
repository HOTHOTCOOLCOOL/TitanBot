"""Memory management and consolidation."""

import asyncio
import json
import json_repair
import time
import re

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

    async def consolidate_memory(self, session: Session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md.

        Args:
            archive_all: If True, clear all messages and reset session (for /new command).
                       If False, only write to files without modifying session.
        """
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
            # Strip <think> tags before parsing JSON, as reasoning models will leak them
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
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
                    asyncio.create_task(distiller.distill_preferences())
                    
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")

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
