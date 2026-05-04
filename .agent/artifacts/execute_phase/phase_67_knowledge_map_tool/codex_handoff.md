# Codex Handoff

Job ID: `phase_67_knowledge_map_tool`
Artifact Directory: `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/`

## Artifact Registry

- `implementation_plan.md`: `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/implementation_plan.md`
- `task.md`: `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/task.md`
- `codex_handoff.md`: `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/codex_handoff.md`
- `ADR-67`: `docs/adr/ADR-67-knowledge-map-tool.md`
- `TOOLS.md`: `TOOLS.md`
- Target Code: `nanobot/agent/tools/knowledge_map.py`, `nanobot/agent/tool_setup.py`
- Target Tests: `tests/unit/test_knowledge_map.py`

## Source Context

ADR-67 requires implementing a `KnowledgeMapTool` to provide a topology map of the Knowledge Graph based on degree centrality. It uses lazy mtime caching on `workspace/memory/graph.json` and enforces a 3,000 character limit on its output.

## Goal

Implement the KnowledgeMapTool, its unit tests, register the tool, and update documentation.

## Allowed Write Set

- `nanobot/agent/tools/knowledge_map.py`
- `nanobot/agent/tool_setup.py`
- `tests/unit/test_knowledge_map.py`
- `TOOLS.md`
- `progress_report.md`

## Forbidden Write Set

- Any other files in `nanobot/agent/`
- Any tests not related to `knowledge_map.py`

## Red Tests to Satisfy

(To be populated in Phase 2)

## Green Exit Criteria

- `pytest tests/unit/test_knowledge_map.py` is entirely green.
- All tasks in `task.md` are completed.

## Stop Conditions

- If any file in `Artifact Registry` cannot be read or understood, return `blocked`.
- Do not attempt to modify core loop or retrieval mechanisms.

## Codex Startup Checklist

1. Read `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/codex_handoff.md`.
2. Read all files listed in `Artifact Registry`.
3. Echo "已读取文件，理解目标" before coding.
4. If missing any files, immediately stop and return `blocked`.

## Return Contract

When finished, write the result strictly to `.agent/artifacts/execute_phase/phase_67_knowledge_map_tool/codex_result.md` (Do not just summarize in chat), and ask the user to notify AgentManager for acceptance.
