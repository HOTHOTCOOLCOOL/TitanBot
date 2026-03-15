"""Memory Search Tool — lets the agent search historical memory semantically."""

from typing import Any

from loguru import logger

from nanobot.agent.tools import Tool


class MemorySearchTool(Tool):
    """Search long-term memory and historical activity logs using semantic similarity.

    This tool allows the agent to proactively search its historical memory
    (conversation summaries, daily activity logs) when the user asks about
    past events, previous tasks, or historical context.
    """

    name = "memory_search"
    description = (
        "Search long-term memory and historical activity logs using semantic similarity. "
        "Use this when the user asks about past events, previous tasks, or anything that "
        "happened more than 2 days ago. Returns the most relevant historical entries."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query describing what to look for in memory.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10).",
                "default": 5,
            },
            "source": {
                "type": "string",
                "description": "Optional filter: 'history' for conversation summaries, 'daily_log' for daily activity logs, or omit for all sources.",
                "enum": ["history", "daily_log"],
            },
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        self._vector_memory = None

    def set_vector_memory(self, vm: Any) -> None:
        """Inject the VectorMemory instance (called by AgentLoop)."""
        self._vector_memory = vm

    async def execute(self, **kwargs: Any) -> str:
        """Execute the memory search."""
        query = kwargs.get("query", "")
        top_k = min(int(kwargs.get("top_k", 5)), 10)
        source = kwargs.get("source")

        if not query:
            return "Error: query parameter is required."

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
            logger.error(f"MemorySearchTool error: {e}")
            return f"Memory search failed: {str(e)}"
