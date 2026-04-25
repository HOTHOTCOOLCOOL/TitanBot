# Phase 67: KnowledgeMapTool — KG Topology Navigation Tool

## Overview
This document serves as the technical archive for the implementation of ADR-67 (`KnowledgeMapTool`), completed during Phase 67. The purpose of this tool is to provide the agent with a bird's-eye view of the Knowledge Graph, acting as a zero-overhead fallback when `memory` search fails.

## Key Technical Decisions
1. **Tool vs Skill**: Implemented as a Tool to avoid context pollution. It only consumes tokens when actively invoked by the LLM.
2. **Degree Centrality**: Used an O(N) degree centrality scan rather than complex K-Means clustering, preventing the introduction of heavy ML dependencies like `sklearn`.
3. **Lazy Caching**: Implemented `mtime`-based lazy caching on `workspace/memory/graph.json` to guarantee O(1) response times during repetitive calls.
4. **Search-First Doctrine**: Designed specifically as a fallback (`P1`) to the primary memory vector search (`P0`).

## Bug Fix: The Truncation False-Positive (Harness Artifact)
During the Stage 3 Acceptance of the `execute_phase` workflow, a critical flaw was detected in the original Harness-generated code:
- **The Bug**: The tool enforced `_MAP_OUTPUT_CAP = 3000`. However, the truncation logic was implemented as `result = result[:_MAP_OUTPUT_CAP] + "\n...[map truncated]"`. This caused the final output to be `3018` characters, violating the strict ToolRegistry size contracts.
- **The False-Positive Test**: The corresponding test `test_output_cap_enforced` generated 200 nodes to trigger the cap. However, because the tool logic only selects the top 15 hubs, the resulting string never actually reached 3000 characters. The test asserted `len(result) <= 3000`, which trivially passed (since the length was ~1500), hiding the truncation logic bug entirely.
- **The Fix**: The truncation logic was reworked to reserve space for the suffix (`_TRUNCATION_SUFFIX`). The test was also overhauled to use an immensely long node name (`A * 3500`) to physically force the string length over the boundary, verifying both the presence of the truncation marker and the hard cap adherence.

## Artifact Handoff
This phase successfully demonstrated the new `execute_phase` Artifact-First workflow:
- The `AgentManager` prepared the `implementation_plan.md`, `task.md`, and `codex_handoff.md`.
- `codex_feedback.md` was effectively utilized to bridge the gap and point out the specific false-positive test logic to Codex.
- Codex resolved the issue and generated `codex_result.md`.

## Lessons Learned
- **Defensive Testing**: When testing length boundaries, do not rely on generating many items if the underlying logic caps the item count. Instead, generate extremely long items to physically breach the threshold. (Added to `ARCHITECTURE.md`).
