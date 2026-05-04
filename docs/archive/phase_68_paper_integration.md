# Phase 68: Paper Integration Slice

**Date:** 2026-05-04  
**Job IDs:** `lite_20260503_paper_integration`, `lite_20260504_write_boundary_contract`  
**Status:** Accepted slice follow-up complete; broader Phase 68 orchestration remains open
**Phase Tracking:** This archive records two sibling `execute_phase` jobs under the same Phase 68. They may run in parallel, but each job keeps its own artifact directory and acceptance receipt.

## 1. Background

Phase 65 had already locked in the Artifact-first contract for `execute_phase`, but Phase 68 still had three paper-vs-runtime gaps:

- the P0 observability rule existed in plan text, yet no runtime owner enforced it before tool dispatch;
- the Allowed Write Set contract existed in tests and handoff text, yet the real generic write boundary (`workspace/sandbox`) was not carried through `VerificationMiddleware` into `VerificationLayer`;
- success / task / trace / knowledge bookkeeping still consumed the pre-dispatch proposal list, so blocked tool calls could appear in persisted step history as if they had executed.

These two sibling jobs close those holes without claiming that the rest of Phase 68 orchestration is finished.

## 2. What Shipped

### `nanobot/agent/loop.py`

- Added a pre-dispatch P0 gate for tool-call turns.
- A turn is accepted when it contains either:
  - a numbered or bulleted plan inside `<think>...</think>`, or
  - valid numbered or bulleted `reasoning_content`.
- Invalid tool-call turns now inject:

```text
Error: P0 observability contract violation...
```

and retry before entering middleware or dispatching any tool.

- Valid tool-call turns emit the proof signal:

```text
P0 Plan Verified
```

- `LoopResult.tool_calls_with_args` and `tools_used` now derive only from calls that actually reached execution (`zip(ctx.tool_calls, ctx.results)` after `pipeline.run_turn(ctx)`), so blocked proposals no longer pollute save prompts, trace dumps, or task knowledge.

### `nanobot/agent/middleware/verification_mw.py`

- The middleware now passes `self._agent.workspace / "sandbox"` into `verification.check_rules(...)` so L1 rules evaluate the same generic write boundary that runtime file tools enforce.
- The L3 anti-pattern audit also consumes executed calls only, rather than the raw proposal list.

### `nanobot/agent/verification.py`

- `check_rules()` and `_check_rule_sensitive_path()` now accept an explicit generic write boundary directory.
- `write_file` and `edit_file` compare their resolved targets against `workspace/sandbox` and block escapes with:

```text
R07: Out of bounds write. Target path must stay inside the workspace sandbox directory.
```

- Resolution failures now fail closed with diagnostics instead of silently degrading behind broad exception handling.

### Contract Docs

- The manual guide legal example now uses `sandbox/phase68_manual_ok.txt`.
- The archive and progress docs no longer imply that workspace-root generic writes are legal or that proposed tool calls count as successful executed steps.

## 3. Acceptance Evidence

Recorded on 2026-05-04 during final acceptance:

- `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py::test_allowed_write_set_blocks_workspace_root_outside_sandbox tests/test_phase68_paper_integration.py::test_allowed_write_set_allows_sandbox_write tests/test_loop_integration.py::TestExecutedOnlyBookkeeping::test_blocked_write_proposal_is_not_recorded_as_success -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_red` -> `3 passed`
- `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_phase68` -> `14 passed`
- `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_loop_integration.py tests/test_loop_cleanup.py tests/test_session_pending.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/test_truncation_safety.py tests/adversarial/test_ssrs_false_positive.py tests/adversarial/test_rpa_bounds.py tests/adversarial/test_phase64_zone_a_adversarial.py tests/adversarial/test_phase59_l0_injection.py tests/adversarial/test_path_traversal.py -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_zone_a` -> `196 passed`
- `D:\Python\nanobot\.venv311\Scripts\python.exe .agent/scripts/auto_reviewer.py --context "核对 task.md 落地情况，防范架构腐化" --files nanobot/agent/loop.py nanobot/agent/verification.py nanobot/agent/middleware/verification_mw.py docs/tests/manual_guides/phase_68_manual_test_guide.md docs/archive/phase_68_paper_integration.md tests/test_phase68_paper_integration.py tests/test_loop_integration.py` -> pass（local fallback runtime）

Observed proof signals:

- `Error: P0 observability contract violation`
- `P0 Plan Verified`
- `ctx.action_reason == "l1_violation"` for workspace-root writes outside `sandbox/`
- `R07: Out of bounds write. Target path must stay inside the workspace sandbox directory.`
- a real file appears at `workspace/sandbox/phase68_manual_ok.txt`
- the blocked `../outside_workspace.txt` proposal is absent from `pending_save["steps"]`, `session.last_tool_calls`, trace output, and `memory/tasks.json` `last_steps_detail`

## 4. Postmortem

### False-positive paths that showed up during this job

- A response could look compliant in logs or chat while the tool pipeline had already been reached.
- A sandbox-boundary implementation could appear present in code review while broad exception handling quietly downgraded it into silent allow or silent uncertainty.
- A raw `response.tool_calls` list could make save / task / trace / knowledge records look successful even when ToolExecutor never ran.

### Hard evidence that now matters

- The P0 gate runs before `add_assistant_message()`, so ADR-62 nullification cannot erase the evidence channel before enforcement.
- The real `workspace/sandbox` boundary is passed from middleware into L1 verification instead of being reconstructed implicitly.
- Executed-step bookkeeping is derived from post-executor results, not from the model proposal list.
- Trace and task-memory artifacts omit blocked proposals instead of merely hiding them in the user-visible reply.

### What remains open in broader Phase 68

- Codex auto-dispatcher
- `codex_result.md` completion detector
- plan-scoped approval token
- worker-side mixed blocked-then-legal runtime proof under live execution
- real runtime orchestration acceptance across multi-session / HITL / sandbox conditions

## 5. Files Touched in This Slice

- `nanobot/agent/loop.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/middleware/verification_mw.py`
- `docs/tests/manual_guides/phase_68_manual_test_guide.md`
- `docs/archive/phase_68_paper_integration.md`
- `tests/test_phase68_paper_integration.py`
- `tests/test_loop_integration.py`
- `.agent/artifacts/execute_phase/lite_20260503_paper_integration/`
- `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/`
