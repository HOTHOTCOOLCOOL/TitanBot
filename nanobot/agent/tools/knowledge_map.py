"""Knowledge Map Tool — KG topology-based domain navigator (ADR-67).

At serve time, provides the agent with a bird's-eye view of the Knowledge Graph
so it can route searches to the right domain. Uses KG degree centrality to
identify Domain Hubs without requiring any external ML libraries.

Design decisions (see docs/adr/ADR-67-knowledge-map-tool.md):
- Tool (not Skill): injected only when the agent calls it, zero system-prompt overhead
- KG degree centrality (not K-Means): no sklearn dependency, O(N) scan
- Lazy mtime cache: recomputes only when graph.json changes
- Search-First always P0: this tool is a fallback, never a replacement for memory search
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.agent.capability import CapabilityTag

# Hard cap on map output — stays well within the 50K ToolRegistry global limit
_MAP_OUTPUT_CAP = 3_000
# Number of top Domain Hub entities to surface
_TOP_N_HUBS = 15
# Number of sub-topic nodes to show per hub
_SUB_TOPICS_PER_HUB = 5

_ERR_UNAVAILABLE = "Error: Knowledge graph is currently empty or unavailable."
_TRUNCATION_SUFFIX = "\n...[map truncated]"


def _truncate_map_output(result: str) -> str:
    """Enforce the ADR-67 cap while reserving room for the truncation marker."""
    if len(result) <= _MAP_OUTPUT_CAP:
        return result

    visible_chars = _MAP_OUTPUT_CAP - len(_TRUNCATION_SUFFIX)
    if visible_chars <= 0:
        return _TRUNCATION_SUFFIX[:_MAP_OUTPUT_CAP]

    return result[:visible_chars] + _TRUNCATION_SUFFIX


class KnowledgeMapTool(Tool):
    """View a structured map of all knowledge domains in the Knowledge Graph.

    Uses KG graph topology (degree centrality) to identify major subject areas
    without requiring vector search or external ML libraries.

    When to use:
    - ``memory`` search returned no results and you need to discover what topics exist
    - A question spans multiple subject areas and you are unsure which keywords to use

    When NOT to use:
    - As a replacement for ``memory`` search on specific, concrete questions.
    - Search-First is always the primary path; this map is a fallback and orientation tool.
    """

    name = "knowledge_map"

    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.DATA_READ

    description = (
        "View a structured map of all knowledge domains in the Knowledge Graph. "
        "Use this tool when: (1) memory search returned no results and you need to "
        "discover what topics exist, or (2) a question spans multiple subject areas "
        "and you are unsure which keywords to search for.\n\n"
        "Do NOT use this as a replacement for memory search on specific questions. "
        "Search-first is always the primary path; this map is a fallback and orientation tool."
    )

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._graph_path = workspace / "memory" / "graph.json"
        self._cache: str | None = None
        self._cache_mtime: float = 0.0

    @property
    def execution_timeout(self) -> int | None:
        return 10  # Fast O(N) scan — 10s is generous

    async def execute(self, **kwargs: Any) -> str:
        """Generate and return the knowledge domain map."""
        if not self._graph_path.exists():
            return _ERR_UNAVAILABLE

        try:
            mtime = self._graph_path.stat().st_mtime
        except OSError as e:
            logger.debug(f"KnowledgeMapTool: cannot stat graph.json: {e}")
            return _ERR_UNAVAILABLE

        # Lazy cache: only recompute when graph.json has changed
        if self._cache is not None and mtime <= self._cache_mtime:
            return self._cache

        try:
            data = json.loads(self._graph_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"KnowledgeMapTool: failed to read graph.json: {e}")
            return _ERR_UNAVAILABLE

        triples = data.get("triples", [])
        if not triples:
            return _ERR_UNAVAILABLE

        # Compute degree centrality: count times each entity appears as source or target
        degree: dict[str, int] = {}
        adjacency: dict[str, list[str]] = {}

        for t in triples:
            src = (t.get("source") or "").strip()
            tgt = (t.get("target") or "").strip()
            if src:
                degree[src] = degree.get(src, 0) + 1
                if src not in adjacency:
                    adjacency[src] = []
            if tgt:
                degree[tgt] = degree.get(tgt, 0) + 1
                if src and tgt not in adjacency.get(src, []):
                    adjacency.setdefault(src, []).append(tgt)

        # Select Top-N hubs by degree
        hubs = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:_TOP_N_HUBS]

        lines = [
            "[Knowledge Domain Map]",
            "",
            "Major knowledge domains Nanobot has learned. "
            "Use this to choose better search keywords.",
            "",
        ]

        for i, (entity, deg) in enumerate(hubs, 1):
            sub_nodes = adjacency.get(entity, [])[:_SUB_TOPICS_PER_HUB]
            sub_str = ", ".join(sub_nodes) if sub_nodes else "—"
            lines.append(f"{i}. 📌 {entity} ({deg} connections) → Related: {sub_str}")

        result = _truncate_map_output("\n".join(lines))

        # Update lazy cache
        self._cache = result
        self._cache_mtime = mtime
        return result
