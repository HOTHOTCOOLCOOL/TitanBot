# Codex Handoff

**Job ID**: `phase_68_ssl_observability`
**Artifact Directory**: `.agent/artifacts/execute_phase/phase_68_ssl_observability/`

## Artifact Registry
- `implementation_plan.md`: `.agent/artifacts/execute_phase/phase_68_ssl_observability/implementation_plan.md`
- `task.md`: `.agent/artifacts/execute_phase/phase_68_ssl_observability/task.md`
- `codex_handoff.md`: `.agent/artifacts/execute_phase/phase_68_ssl_observability/codex_handoff.md`
- `tests/test_ssl_normalizer.py`: `tests/test_ssl_normalizer.py`
- `nanobot/agent/skills.py`: `nanobot/agent/skills.py`
- `nanobot/agent/context.py`: `nanobot/agent/context.py`
- `nanobot/agent/knowledge_graph.py`: `nanobot/agent/knowledge_graph.py`
- `Candidate Reference`: `.agent/artifacts/harness_lite/lite_20260504_ssl_representation/candidate.md`

## Goal
Implement the SSL 3-layer JSON graph representation for skills purely as an Observability and Context Optimization layer, including composite file hashing and `ContextBuilder` prompt compression.

## Allowed Write Set
- `nanobot/agent/ssl_normalizer.py`
- `nanobot/agent/skills.py`
- `nanobot/agent/context.py`
- `nanobot/agent/knowledge_graph.py`
- `tests/test_ssl_normalizer.py`
- `tests/test_context_knowledge.py`

## Forbidden Write Set
- `nanobot/agent/verification.py` (AST sandbox must NOT be touched)
- `nanobot/agent/loop.py`

## Red Tests to Satisfy
- `tests/test_ssl_normalizer.py` (To be created by AgentManager)

## Green Exit Criteria
- `pytest tests/test_ssl_normalizer.py tests/test_context_knowledge.py tests/test_phase22a_skills.py tests/test_phase24_knowledge_graph.py tests/test_phase68_paper_integration.py -W ignore -v` passes.
- Code conforms to L1 sandbox constraints.

## Behavior Smoke Checks
- Run a live skill load and observe the console logs for `[SkillsLoader] Computed new composite hash...` and `[SkillsLoader] Injected SSL Scheduling for skill...`.

## Runtime Parity Checks
- Verify `skill_ssl` entity with full properties (including `hash` and `graph`) exists within the `entities` mapping of `memory/graph.json`.

## Proof Signals to Inspect
- Log trace: `[SkillsLoader] Injected SSL Scheduling...`

## Stop Conditions
- If the AST Sandbox is bypassed or modified in any way.
- If KG schema conflicts with existing `reasoning_template`.
- If `nanobot/agent/knowledge_graph.py` lacks the logic to preserve `skill_ssl` (and its full payload) across `rebuild_entity_index` operations.

## Codex Startup Checklist
1. Read ALL files listed in the Artifact Registry sequentially. If any critical item is missing or unreadable, output `blocked`.
2. Echo back explicitly in your response before coding: (a) Which files you have successfully read; (b) Your understanding of the goals and the Allowed/Forbidden write boundaries; (c) Which specific Runtime Parity Checks and Proof Signals you are required to inspect.

## Return Contract
- Write results to `.agent/artifacts/execute_phase/phase_68_ssl_observability/codex_result.md` using the standard template.
- You MUST explicitly document `Observed Proof Signals`, `Runtime Parity Findings`, and `Untested Runtime States` in your result.
