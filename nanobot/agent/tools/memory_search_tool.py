"""Memory Tool — unified CRUD for agent long-term memory.

Inspired by mem9's design: lets the agent store, search, update, and delete
persistent memory entries (facts, preferences, decisions, project context).
"""

import re
import time
from typing import Any

from loguru import logger

from nanobot.agent.tools import Tool


class MemorySearchTool(Tool):
    """Unified memory tool: store, search, update, and delete long-term memory.

    Supports semantic search (via vector store) and file-based CRUD
    on MEMORY.md and daily logs. Optionally filters by tags.
    """

    name = "memory"
    description = (
        "Manage long-term memory: store facts/preferences, search past events, "
        "update existing entries, or delete outdated information.\n\n"
        "Actions:\n"
        "- search: Find relevant memories by keyword/meaning (default action)\n"
        "- store: Save a new memory entry (fact, preference, decision, or event)\n"
        "- delete: Remove a specific entry from MEMORY.md by keyword\n\n"
        "Use 'store' when the user says things like 'remember this', 'don't forget', "
        "'save for later'. Use 'search' to recall past events or facts.\n\n"
        "What to remember: user preferences, profile facts, project context, "
        "important decisions, long-term instructions.\n"
        "What NOT to remember: temporary debugging info, large data, passwords/API keys."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform: 'search' (default), 'store', or 'delete'.",
                "enum": ["search", "store", "delete"],
                "default": "search",
            },
            "query": {
                "type": "string",
                "description": "Search query (for 'search') or content to store (for 'store') or keyword to delete (for 'delete').",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of search results to return (default 5, max 10). Only for 'search' action.",
                "default": 5,
            },
            "source": {
                "type": "string",
                "description": "Optional filter: 'history' for conversation summaries, 'daily_log' for daily activity logs. Only for 'search' action.",
                "enum": ["history", "daily_log"],
            },
            "memory_type": {
                "type": "string",
                "description": "For 'store': 'fact' saves to MEMORY.md (persistent), 'event' saves to daily log (temporal). Default: 'fact'.",
                "enum": ["fact", "event"],
                "default": "fact",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorizing the memory entry (e.g. ['preference', 'project']). For 'store' and 'search'.",
            },
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        self._vector_memory = None
        self._memory_store = None

    def set_vector_memory(self, vm: Any) -> None:
        """Inject the VectorMemory instance (called by AgentLoop)."""
        self._vector_memory = vm

    def set_memory_store(self, ms: Any) -> None:
        """Inject the MemoryStore instance (called by AgentLoop)."""
        self._memory_store = ms

    async def execute(self, **kwargs: Any) -> str:
        """Execute the memory action."""
        action = kwargs.get("action", "search")
        query = kwargs.get("query", "")

        if not query:
            return "Error: query parameter is required."

        if action == "store":
            return self._store(query, kwargs)
        elif action == "delete":
            return self._delete(query)
        else:
            return self._search(query, kwargs)

    def _search(self, query: str, kwargs: dict) -> str:
        """Search memory semantically."""
        top_k = min(int(kwargs.get("top_k", 5)), 10)
        source = kwargs.get("source")
        tags = kwargs.get("tags")

        if not self._vector_memory:
            return "Memory search is not available (vector store not initialised)."

        try:
            results = self._vector_memory.search(
                query=query,
                top_k=top_k,
                source_filter=source,
            )

            if not results:
                return f"No relevant memory found for: '{query}'"

            # Filter by tags if specified
            if tags:
                tag_set = set(t.lower() for t in tags)
                filtered = []
                for r in results:
                    entry_tags = r.get("metadata", {}).get("tags", [])
                    if isinstance(entry_tags, str):
                        entry_tags = [t.strip() for t in entry_tags.split(",")]
                    if any(t.lower() in tag_set for t in entry_tags):
                        filtered.append(r)
                if filtered:
                    results = filtered

            lines = [f"Found {len(results)} relevant memory entries:\n"]

            for i, r in enumerate(results, 1):
                src = r.get("source", "unknown")
                text = r.get("text", "").strip()
                score = r.get("score", 0)
                meta = r.get("metadata", {})
                date_str = meta.get("date", "")

                header = f"[{src}]"
                if date_str:
                    header = f"[{date_str}]"

                lines.append(f"--- Result {i} {header} (relevance: {score:.0%}) ---")
                lines.append(text)
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"MemoryTool search error: {e}")
            return f"Memory search failed: {str(e)}"

    def _store(self, content: str, kwargs: dict) -> str:
        """Store a new memory entry."""
        memory_type = kwargs.get("memory_type", "fact")
        tags = kwargs.get("tags", [])

        if not self._memory_store:
            return "Error: memory store not available."

        try:
            tag_comment = ""
            if tags:
                tag_comment = f"<!-- tags: {', '.join(tags)} -->\n"

            if memory_type == "event":
                # Save to daily log
                entry = f"{tag_comment}{content}"
                self._memory_store.append_daily_log(entry)

                # Also ingest into vector store for semantic search
                if self._vector_memory:
                    today_str = time.strftime("%Y-%m-%d")
                    self._vector_memory.ingest_text(
                        content,
                        source=f"daily_log:{today_str}",
                        metadata={"date": today_str, "tags": ",".join(tags) if tags else ""},
                    )

                return f"✅ Saved event to daily log: {content[:100]}..."
            else:
                # Save to MEMORY.md (append as a new entry)
                existing = self._memory_store.read_long_term()
                new_entry = f"\n\n{tag_comment}- {content}"
                self._memory_store.write_long_term(existing + new_entry)

                # Also ingest into vector store
                if self._vector_memory:
                    self._vector_memory.ingest_text(
                        content,
                        source="memory",
                        metadata={"tags": ",".join(tags) if tags else ""},
                    )

                return f"✅ Saved fact to long-term memory: {content[:100]}..."

        except Exception as e:
            logger.error(f"MemoryTool store error: {e}")
            return f"Failed to store memory: {str(e)}"

    def _delete(self, keyword: str) -> str:
        """Delete a memory entry from MEMORY.md by keyword match."""
        if not self._memory_store:
            return "Error: memory store not available."

        try:
            existing = self._memory_store.read_long_term()
            if not existing:
                return "Memory is empty, nothing to delete."

            # Split into lines/sections and filter out matching ones
            lines = existing.split("\n")
            original_count = len(lines)
            keyword_lower = keyword.lower()

            # Remove lines (and their tag comments) that contain the keyword
            filtered = []
            skip_next = False
            deleted_count = 0
            for i, line in enumerate(lines):
                if skip_next:
                    skip_next = False
                    continue
                if keyword_lower in line.lower():
                    # Also skip preceding tag comment if present
                    if filtered and filtered[-1].strip().startswith("<!-- tags:"):
                        filtered.pop()
                    deleted_count += 1
                    continue
                # Check if this is a tag comment for the next line
                if line.strip().startswith("<!-- tags:") and i + 1 < len(lines):
                    if keyword_lower in lines[i + 1].lower():
                        skip_next = True
                        deleted_count += 1
                        continue
                filtered.append(line)

            if deleted_count == 0:
                return f"No memory entries matching '{keyword}' found."

            self._memory_store.write_long_term("\n".join(filtered))
            return f"🗑️ Deleted {deleted_count} memory entry(ies) matching '{keyword}'."

        except Exception as e:
            logger.error(f"MemoryTool delete error: {e}")
            return f"Failed to delete memory: {str(e)}"
