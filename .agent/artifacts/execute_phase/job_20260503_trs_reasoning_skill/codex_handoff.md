# Codex Handoff

Job ID: `job_20260503_trs_reasoning_skill`

Artifact Directory:
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/`

Artifact Registry:
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/implementation_plan.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/task.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_handoff.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_result.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_feedback.md`
- `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/candidate.md`
- `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/problem_statement.md`
- `.agent/artifacts/harness_lite/lite_20260503_trs_reasoning_skill/baseline.md`
- `nanobot/agent/context.py`
- `nanobot/agent/knowledge_graph.py`
- `nanobot/agent/loop.py`
- `tests/test_phase24_knowledge_graph.py`
- `tests/test_context_knowledge.py`
- `tests/test_phase28c_knowledge_graph.py`
- `tests/adversarial/test_phase64_zone_a_adversarial.py`

Source Context:
- Harness candidate decided to keep the Knowledge Graph as the single storage layer.
- Retrieval matching should stay on the existing hybrid KG path.
- Prompt injection must enforce a strict 1000-character cap for retrieved `reasoning_template` payloads.
- Manual/HITL creation is the only supported distillation path for these templates.

Goal:
- Implement ReasoningSkill storage in the Knowledge Graph and context-time retrieval injection with strict 1000-character truncation for `reasoning_template` entities.

Baseline Status:
- Green baseline confirmed.
- Executed command:
  - `python -m pytest tests/test_loop_cleanup.py tests/test_loop_integration.py tests/test_session_manager.py tests/test_session_pending.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/ -W ignore -v`
- Result:
  - `193 passed in 49.72s`

Allowed Write Set:
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/implementation_plan.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/task.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_handoff.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_result.md`
- `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_feedback.md`
- `nanobot/agent/context.py`
- `nanobot/agent/knowledge_graph.py`
- `tests/test_phase24_knowledge_graph.py`
- `tests/test_context_knowledge.py`
- `tests/test_phase28c_knowledge_graph.py`
- `tests/adversarial/test_phase64_zone_a_adversarial.py`

Forbidden Write Set:
- `nanobot/agent/skills.py`
- `nanobot/agent/memory.py`
- `nanobot/session/manager.py`
- `nanobot/agent/middleware/`
- Any file outside the Allowed Write Set

Red Tests to Satisfy:
- Executed Command:
  `python -m pytest tests/test_phase24_knowledge_graph.py::TestReasoningTemplateSchema tests/test_context_knowledge.py::TestReasoningTemplatePromptBudget -v`
- Failure Summary:
  - `test_rebuild_preserves_reasoning_template_type`: FAILED. The `type` metadata is lost when `rebuild_entity_index()` resets it to `""`.
  - `test_reasoning_template_truncated`: FAILED. The 1500-char template is fully injected instead of being capped at 1000 characters in `ContextBuilder`.
- Minimum required coverage:
  - KG entity `type` preservation for `reasoning_template`
  - Strict 1000-character truncation for retrieved `reasoning_template` prompt injection
  - Same truncation behavior for pre-fetched KG content and direct KG retrieval
  - No regression for ordinary KG entity summaries

Green Exit Criteria:
- All red tests written in Phase 2 turn green.
- Zone A baseline command passes after implementation.
- `context.py` is the final enforcement point for the 1000-character reasoning-template prompt cap.
- KG remains the only durable schema source; `skills.py` stays untouched.

Stop Conditions:
- Any Artifact in the registry is missing or unreadable.
- Baseline is not green.
- The change requires writing outside the Allowed Write Set.
- Preserving `reasoning_template` metadata would require introducing a second storage layer or changing unrelated Zone A modules.

Codex Startup Checklist:
1. Read this file first.
2. Read `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/implementation_plan.md`.
3. Read `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/task.md`.
4. Read the harness candidate artifact and listed repo files before coding.
5. If any required artifact is missing, return `blocked` and do not invent a replacement plan.
6. Do not rewrite `implementation_plan.md` or `task.md`; execute against them.

Return Contract:
- After implementation, overwrite `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_result.md`.
- `Task Coverage` must respond to every task ID in `task.md`.
- List every changed file and every executed test command.
- If blocked or failed, record the exact blocker and stop.
