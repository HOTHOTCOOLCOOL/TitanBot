# Baseline Fact Sheet

## Claim / Evidence / Status

| Claim | Evidence | Status |
| :--- | :--- | :--- |
| Nanobot currently uses `KnowledgeMapTool` to navigate the Knowledge Graph (KG). | `d:\Python\nanobot\docs\archive\EVOLUTION_epoch1_20.md` and Phase 67 `knowledge_map.py` | VERIFIED |
| Nanobot tools lack a standardized capability card with precise inputs, outputs, and invocation goals. | `TOOLS.md` mostly relies on natural language descriptions without strict schema breakdown. | VERIFIED |
| The paper 2604.24026v3 proves that a "Scheduling Layer" metadata schema improves tool discovery MRR significantly. | `paper_analysis_report.md` | VERIFIED |

## Source of Truth Files

- `nanobot/agent/tools/knowledge_map.py` (Current implementation of tool discovery navigation)
- `TOOLS.md` (Current tool registry and descriptions)
- `.agent/artifacts/paper_analysis_report.md` (Paper review context)

## Runtime Artifacts / Hidden Runtime States

- **Knowledge Graph Nodes**: Metadata attached to tool/skill entities in the KG.
- **Context Injection**: When `KnowledgeMapTool` returns nodes, it currently returns node names, relationships, and limited text. The new metadata will consume context token budget.
- **Prompt Budget**: Any injected Scheduling Layer metadata must respect the strict context budget (e.g., similar to the 1000-character budget for `reasoning_template` in Phase 65/Job 20260503).

## Observable Proof Signals

- `KnowledgeMapTool` returning a specific schema (e.g., `{"goal": "...", "input": "...", "output": "..."}`) when querying a tool entity.
- A script (LLM Normalizer) successfully taking a raw markdown file and outputting the JSON Scheduling Layer schema.

## Unknowns

- Whether injecting full Scheduling Layer metadata for multiple tools during `KnowledgeMapTool` navigation will blow up the context window.
- The exact format of the LLM prompt required for the lightweight Normalizer.

## Questions the Critic Must Attack

1. Will adding Scheduling Layer metadata to KG nodes bloat the `KnowledgeMapTool` output beyond safe token limits?
2. If the LLM Normalizer script hallucinates the schema, does it compromise Nanobot's security, or just cause a slightly worse retrieval? (False Positive Success Path check).
3. If the capability card isn't properly wired into the `context.py` prompt budgeting, will it bypass the Phase 57 Waterfall Budget?
