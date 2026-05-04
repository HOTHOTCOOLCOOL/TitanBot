# Job 20260503: ReasoningSkill KG Schema and Prompt Budget

## Summary

This job landed the minimal ReasoningSkill implementation chosen by the harness decision: keep the Knowledge Graph as the only durable storage layer, preserve `reasoning_template` entity metadata during reindex, and enforce a strict 1000-character prompt budget for retrieved reasoning templates inside `ContextBuilder`.

## What Landed

- `nanobot/agent/knowledge_graph.py`
  - `rebuild_entity_index()` now preserves existing entity `type` metadata instead of resetting it to `""`.
  - Standalone manually curated `reasoning_template` entities remain durable even when they are not backed by triples.
  - Added `get_entity_context_entries()` so retrieval can expose structured entity metadata without changing match scoring.
- `nanobot/agent/context.py`
  - Added a type-aware KG formatting path inside `ContextBuilder`.
  - Retrieved entities of type `reasoning_template` are truncated to a hard 1000-character cap before prompt append.
  - Ordinary KG summaries keep the previous untruncated behavior.
  - Direct KG lookup and the `pre_fetched_kg` optimization path now share the same structured formatting logic when a KG instance is available.
- Tests
  - Added schema-preservation coverage for manual and triple-backed `reasoning_template` entities.
  - Added prompt-budget coverage for direct KG injection, pre-fetched KG injection, and non-reasoning pass-through.

## Runtime Contract

- Durable storage remains `memory/graph.json`; no parallel `skills.py` schema was introduced.
- Reasoning templates are represented as KG entities with:
  - `type: "reasoning_template"`
  - `summary: <distilled reasoning template>`
- The 1000-character cap applies only to prompt injection, not to on-disk storage.
- Retrieval ranking semantics remain unchanged; only formatting and metadata preservation were extended.

## Why This Shape Was Chosen

The harness candidate explicitly rejected:

- autonomous background distillation loops,
- a second source of truth in `skills.py`,
- and IFCC-style hand-waving for pre-call budgeting.

The resulting implementation therefore follows a narrower rule:

1. store reasoning templates exactly where other durable knowledge already lives,
2. keep retrieval on the existing KG path,
3. enforce the budget at the final prompt assembly boundary.

## Files Affected

- `nanobot/agent/knowledge_graph.py`
- `nanobot/agent/context.py`
- `tests/test_phase24_knowledge_graph.py`
- `tests/test_context_knowledge.py`

## Automated Verification

Validated with:

```text
python -m pytest tests/test_phase24_knowledge_graph.py::TestReasoningTemplateSchema tests/test_context_knowledge.py::TestReasoningTemplatePromptBudget -v
python -m pytest tests/test_phase24_knowledge_graph.py tests/test_context_knowledge.py tests/test_phase28c_knowledge_graph.py tests/adversarial/test_phase64_zone_a_adversarial.py -v
python -m pytest tests/test_loop_cleanup.py tests/test_loop_integration.py tests/test_session_manager.py tests/test_session_pending.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/ -W ignore -v
```

Result: pass

## Manual Validation Still Recommended

- Create or edit a real `reasoning_template` entry in `memory/graph.json` and confirm a relevant query injects only the first 1000 characters into the built prompt.
- Confirm a normal KG entity summary of similar length still injects in full.
- Confirm a rebuild/restart cycle does not erase manually curated `reasoning_template` metadata.

## Residual Risks

- If a future caller passes only raw `pre_fetched_kg` text and does not also provide a `KnowledgeGraph` instance, type-aware truncation cannot be reconstructed from the flattened string alone.
- Template usefulness remains dependent on manual curation quality; this job intentionally does not automate distillation.
