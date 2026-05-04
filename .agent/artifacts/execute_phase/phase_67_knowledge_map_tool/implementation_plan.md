# Goal

Implement KnowledgeMapTool — KG Topology Navigation Tool based on ADR-67.
This tool will help the LLM navigate the knowledge graph by identifying hub nodes (Degree Centrality) and their top associations, providing a topology map when the LLM lacks domain context.

## Blast Radius Analysis

The changes primarily introduce a new tool and its unit tests. The blast radius is limited to the tool registration mechanism (`nanobot/agent/tool_setup.py`) and the tool system's documentation (`TOOLS.md`). Existing tools and core execution loops will not be affected.

## Zone Declaration

**ZONE B** (波及 `tools/`, `tool_setup.py`)
对应靶向命令：
`pytest tests/unit/test_knowledge_map.py tests/unit/test_tool_setup.py -W ignore -v`

## Implementation Strategy

1. **Create `nanobot/agent/tools/knowledge_map.py`**:
   - Implement `KnowledgeMapTool` class inheriting from `BaseTool`.
   - Use Lazy mtime caching on `workspace/memory/graph.json`.
   - Calculate Degree Centrality on the fly (O(N) scanning) when cache is invalid.
   - Enforce string output strictly ≤ 3,000 characters.
   - Handle empty or missing `graph.json` gracefully, returning a standard `"Error: ..."` prefix.
2. **Update `nanobot/agent/tool_setup.py`**:
   - Import `KnowledgeMapTool`.
   - Register it at the end of `_register_default_tools()`.
3. **Update `TOOLS.md`**:
   - Document `knowledge_map` tool as the 20th audit entry, adhering to Phase 22B rules.
4. **Create `tests/unit/test_knowledge_map.py`**:
   - Test empty/missing graph handling (`A2`).
   - Test output length cap (`A3`).
   - Test mtime cache hit (`A4`).
5. **Update `progress_report.md`**:
   - Mark ADR-67 as completed.

## Contract / Data Structures / Function Signatures

- `class KnowledgeMapTool(BaseTool)`:
  - `name = "knowledge_map"`
  - `description = "..."`
  - `def _execute(self, **kwargs) -> str`
- Caching logic: Maintain module-level or instance-level `_last_mtime` and `_cached_result`.

## Risk Notes

- Tool execution should not raise unhandled exceptions; return string starting with "Error: ".
- Large `graph.json` might cause latency or memory spikes. Degree centrality computation should be memory-efficient.

## Validation Plan

1. Run automated unit tests for `test_knowledge_map.py` (Covering empty graph, length limit, cache).
2. Ensure full project regression tests pass.
