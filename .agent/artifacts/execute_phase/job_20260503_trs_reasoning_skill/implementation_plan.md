# Implementation Plan

Job ID: `job_20260503_trs_reasoning_skill`

## Goal

Implement ReasoningSkill distillation storage in the Knowledge Graph and retrieval-time prompt injection with a strict 1000-character truncation budget for `reasoning_template` entities in `nanobot/agent/context.py`.

## Source Context

- Harness decision: `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/candidate.md`
- Supporting artifacts:
  - `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/problem_statement.md`
  - `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/baseline.md`
- Primary code paths:
  - `nanobot/agent/context.py`
  - `nanobot/agent/knowledge_graph.py`
  - `nanobot/agent/loop.py`
- Existing regression surfaces:
  - `tests/test_phase24_knowledge_graph.py`
  - `tests/test_context_knowledge.py`
  - `tests/test_phase28c_knowledge_graph.py`
  - `tests/adversarial/test_phase64_zone_a_adversarial.py`

## Blast Radius Analysis

- `nanobot/agent/context.py`
  - Owns Knowledge Graph prompt injection and is the required enforcement point for the 1000-character prompt budget.
  - Any formatting change can alter system-prompt shape for all Zone A flows.
- `nanobot/agent/knowledge_graph.py`
  - Holds the only durable entity store (`memory/graph.json`).
  - Current `rebuild_entity_index()` resets `entities[*].type` to `""`, which would silently erase `reasoning_template` metadata unless preserved.
  - Current `get_entity_context()` returns formatted text only, which hides entity type metadata from `context.py`; a type-aware helper or equivalent contract is required.
- `nanobot/agent/loop.py`
  - Pre-fetches KG context and passes `pre_fetched_kg` into `ContextBuilder.build_messages()`.
  - Even if left read-only, this path must remain behaviorally compatible with the new context-side truncation logic.
- `memory/graph.json`
  - Schema remains the single source of truth; no parallel storage layer is allowed.
  - Backward compatibility with existing entity summaries and older graph payloads must hold.
- Tests
  - Need focused regression coverage so non-`reasoning_template` entity retrieval and existing KG fallback behavior do not regress.

## Zone Declaration

- Zone: `ZONE A`
- Trigger: task directly changes `context.py`, with adjacent impact on Knowledge Graph prompt assembly.
- Required green baseline command:
  - `pytest tests/test_loop*.py tests/test_session*.py tests/test_middleware*.py tests/test_phase31*.py tests/adversarial/ -W ignore -v`

## Baseline Record

- Workflow baseline intent:
  - `pytest tests/test_loop*.py tests/test_session*.py tests/test_middleware*.py tests/test_phase31*.py tests/adversarial/ -W ignore -v`
- Windows execution form used:
  - `python -m pytest tests/test_loop_cleanup.py tests/test_loop_integration.py tests/test_session_manager.py tests/test_session_pending.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/ -W ignore -v`
- Result:
  - `193 passed in 49.72s`

## Implementation Strategy

1. Keep the Knowledge Graph as the single durable storage layer.
   - Represent a ReasoningSkill as a standard entity entry under `memory/graph.json`.
   - Use `entities[<name>]["type"] == "reasoning_template"` and store the distilled reasoning text in the existing entity summary field.

2. Preserve schema fidelity before prompt work.
   - Ensure entity reindex / rebuild logic does not erase pre-existing `type` metadata for manually curated entities.
   - Avoid touching `skills.py` or adding a second schema source.

3. Keep retrieval scoring unchanged while restoring type visibility to the injection path.
   - Reuse existing entity matching logic from `KnowledgeGraph.get_entity_context(...)`.
   - Add only the minimum type-aware helper or formatting contract needed so `context.py` can identify which retrieved entries are `reasoning_template`.

4. Enforce the prompt budget in `context.py`.
   - Apply a strict 1000-character truncation only to retrieved `reasoning_template` payloads before appending to `system_prompt`.
   - The same truncation rule must hold for both direct KG lookup and the pre-fetched KG path consumed by `build_messages()`.
   - Non-reasoning KG entities must keep existing formatting and retrieval behavior.

5. Lock the behavior with tests before implementation is accepted.
   - Add red tests for schema preservation, reasoning-template-only truncation, and consistent behavior between pre-fetched and non-prefetched KG injection.

## Contract / Data Structures / Function Signatures

- Durable entity shape in `memory/graph.json`:

```json
{
  "Reasoning: Parsing Legacy Binary Format": {
    "type": "reasoning_template",
    "summary": "<distilled reasoning template and pitfalls>",
    "triple_indices": [],
    "updated_at": "2026-05-03T00:00:00"
  }
}
```

- Required behavioral contract:
  - `KnowledgeGraph` remains the only persistence layer.
  - Entity retrieval ranking stays on the existing hybrid path.
  - `ContextBuilder.build_messages(...)` is the final enforcement point for prompt-budget truncation.

- Expected implementation shape:
  - Preserve `entities[*].type` in `KnowledgeGraph.rebuild_entity_index()`.
  - Introduce a type-aware retrieval/formatting helper if needed so `context.py` can distinguish `reasoning_template` entries without changing retrieval semantics.
  - Keep public prompt output compatible with the existing `## Entity Knowledge` block.

## Risk Notes

- Hidden metadata loss:
  - If `rebuild_entity_index()` still zeroes `type`, reasoning templates will disappear on the next KG maintenance pass.
- Prompt-shape regression:
  - Budget enforcement must not duplicate KG content or break the `pre_fetched_kg` optimization path.
- Over-truncation:
  - The 1000-character cap must apply only to `reasoning_template` entries, not to ordinary entity summaries.
- Backward compatibility:
  - Old graphs without `type` fields must continue loading and formatting cleanly.

## Validation Plan

- Stage-1 baseline:
  - Run `pytest tests/test_loop*.py tests/test_session*.py tests/test_middleware*.py tests/test_phase31*.py tests/adversarial/ -W ignore -v`
- Red tests to author in Phase 2:
  - `reasoning_template` metadata survives save/load/rebuild.
  - `ContextBuilder.build_messages()` truncates retrieved `reasoning_template` content to 1000 characters or less before prompt append.
  - Non-`reasoning_template` KG entities remain untruncated by the new rule.
  - Pre-fetched KG injection and direct KG lookup produce the same reasoning-template truncation behavior.
- Green acceptance target after implementation:
  - Focused tests for KG/context behavior.
  - Re-run the Zone A baseline command.
