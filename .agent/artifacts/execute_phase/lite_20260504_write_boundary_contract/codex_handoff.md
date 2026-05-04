# Codex Handoff

## Job ID
`lite_20260504_write_boundary_contract`

## Artifact Directory
`.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/`

## Artifact Registry
- **Harness Candidate**: `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/candidate.md`
- **Harness Review Packet**: `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/review_packet.md`
- **Harness Evidence Gate**: `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/evidence_gate.md`
- **Implementation Plan**: `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/implementation_plan.md`
- **Task List**: `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/task.md`
- **Handoff Contract**: `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_handoff.md`
- **Result Template**: `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_result.md`
- **Feedback Slot**: `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_feedback.md`
- **Locked Red Tests**:
  - `tests/test_phase68_paper_integration.py`
  - `tests/test_loop_integration.py`
- **Implementation Files**:
  - `nanobot/agent/middleware/verification_mw.py`
  - `nanobot/agent/verification.py`
  - `nanobot/agent/loop.py`
  - `nanobot/agent/state_handler.py`
  - `nanobot/agent/trace_archive.py`
- **Contract Docs**:
  - `docs/tests/manual_guides/phase_68_manual_test_guide.md`
  - `docs/archive/phase_68_paper_integration.md`
- **Read-Only Runtime Boundary Sources**:
  - `nanobot/agent/tool_setup.py`
  - `nanobot/agent/worker/bridge.py`

## Source Context
- `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/candidate.md`
- `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/evidence_gate.md`

## Goal
Implement the approved candidate so that:

1. the generic `write_file` / `edit_file` boundary is `workspace/sandbox` (Zone C) in both L1 and runtime execution; and
2. success/task/trace/knowledge bookkeeping consumes a shared executed-only tool-call source instead of the pre-dispatch proposal list.

## Allowed Write Set
You may ONLY modify:
- `nanobot/agent/middleware/verification_mw.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/loop.py`
- `nanobot/agent/state_handler.py`
- `nanobot/agent/trace_archive.py`
- `docs/tests/manual_guides/phase_68_manual_test_guide.md`
- `docs/archive/phase_68_paper_integration.md`
- `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_result.md`

## Forbidden Write Set
Do NOT modify:
- `nanobot/agent/tool_setup.py`
- `nanobot/agent/worker/bridge.py`
- `nanobot/agent/tools/filesystem.py`
- `nanobot/session/manager.py`
- `nanobot/agent/task_knowledge.py`
- `tests/test_phase68_paper_integration.py`
- `tests/test_loop_integration.py`
- any harness artifact under `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/`
- any execute-phase artifact here other than `codex_result.md`

Especially forbidden:
- any change that widens generic file-write permissions from Zone C to workspace root
- any “fix” that makes the old workspace-root docs pass by expanding runtime capability

## Red Tests to Satisfy
These tests are locked by AgentManager in Phase 2 and are read-only for Codex:

- `tests/test_phase68_paper_integration.py::test_allowed_write_set_blocks_workspace_root_outside_sandbox`
- `tests/test_phase68_paper_integration.py::test_allowed_write_set_allows_sandbox_write`
- `tests/test_loop_integration.py::TestExecutedOnlyBookkeeping::test_blocked_write_proposal_is_not_recorded_as_success`

## Red Test Command
Run this exact command first:

`D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py::test_allowed_write_set_blocks_workspace_root_outside_sandbox tests/test_phase68_paper_integration.py::test_allowed_write_set_allows_sandbox_write tests/test_loop_integration.py::TestExecutedOnlyBookkeeping::test_blocked_write_proposal_is_not_recorded_as_success -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_red`

Recorded Phase 2 result on 2026-05-04:

- `test_allowed_write_set_blocks_workspace_root_outside_sandbox` -> fail
- `test_allowed_write_set_allows_sandbox_write` -> pass
- `test_blocked_write_proposal_is_not_recorded_as_success` -> fail

## Failure Summary
- `test_allowed_write_set_blocks_workspace_root_outside_sandbox`
  Current behavior does **not** abort at L1 for `write_file("phase68_manual_ok.txt")` at workspace root. `ctx.action_reason` stays empty, proving that workspace-root generic writes outside `sandbox/` still slip past the verification boundary.
- `test_blocked_write_proposal_is_not_recorded_as_success`
  Current behavior still stores the blocked `../outside_workspace.txt` proposal in `session.pending_save["steps"]` before the later legal sandbox write succeeds. This proves the bookkeeping source is still the pre-dispatch proposal list instead of an executed-only list.
- `test_allowed_write_set_allows_sandbox_write`
  This already passes and must keep passing. It is the regression guard against over-tightening the boundary fix.

## Expected Repair Boundary
- Keep `tool_setup.py` and `worker/bridge.py` unchanged as the source of truth that generic writes belong to Zone C.
- Repair the mismatch by changing L1 boundary propagation and R07 evaluation, not by widening write permissions.
- Change `LoopResult.tool_calls_with_args` and `tools_used` semantics so they represent executed-only calls.
- Let downstream sinks inherit the corrected source semantics instead of patching every sink independently unless a sink truly bypasses the shared source.
- Update the manual guide and archive so they stop promising workspace-root generic writes.

## Green Exit Criteria
All of the following must pass:

1. Locked red tests:
   `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py::test_allowed_write_set_blocks_workspace_root_outside_sandbox tests/test_phase68_paper_integration.py::test_allowed_write_set_allows_sandbox_write tests/test_loop_integration.py::TestExecutedOnlyBookkeeping::test_blocked_write_proposal_is_not_recorded_as_success -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_red`
2. Phase 68 regression file:
   `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_phase68`
3. ZONE A green baseline:
   `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_loop_integration.py tests/test_loop_cleanup.py tests/test_session_pending.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/test_truncation_safety.py tests/adversarial/test_ssrs_false_positive.py tests/adversarial/test_rpa_bounds.py tests/adversarial/test_phase64_zone_a_adversarial.py tests/adversarial/test_phase59_l0_injection.py tests/adversarial/test_path_traversal.py -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_zone_a`

## Behavior Smoke Checks
These are mechanism checks, not answer-shape checks:

1. **Workspace-root generic write is blocked pre-dispatch**
   - Probe: `write_file("phase68_manual_ok.txt")`
   - Expected: L1 aborts before executor; rewrite hint/tool result mentions `sandbox`
2. **Sandbox generic write still works**
   - Probe: `write_file("sandbox/phase68_manual_ok.txt")`
   - Expected: real file appears under `workspace/sandbox/`
3. **Mixed blocked-then-legal flow records only executed calls**
   - Probe: one request first proposes `../outside_workspace.txt`, then retries with `sandbox/phase68_manual_ok.txt`
   - Expected: blocked path absent from `pending_save["steps"]`, `session.last_tool_calls`, trace output, and knowledge `last_steps_detail`

## Runtime Parity Checks
- `nanobot/agent/tool_setup.py`
  Main agent generic write allowlist remains `workspace/sandbox`
- `nanobot/agent/worker/bridge.py`
  Worker generic write allowlist remains Zone C-aligned
- `nanobot/agent/middleware/verification_mw.py`
  Must pass the same Zone C root into L1 that runtime write tools already use
- `nanobot/agent/verification.py`
  Must evaluate R07 relative to Zone C and stop saying “within the workspace directory” for generic writes
- `nanobot/agent/loop.py`
  Must treat `LoopResult.tool_calls_with_args` as executed-only
- `nanobot/agent/state_handler.py`
  Must not reintroduce proposal semantics through the redo/re-execute path
- `nanobot/agent/trace_archive.py`
  Must not archive blocked proposals as if they executed

## Proof Signals to Inspect
- `ctx.action_reason == "l1_violation"` for workspace-root generic writes outside `sandbox/`
- rewrite-hint or tool-result text for blocked generic writes contains `sandbox`
- `WriteFileTool` success for `sandbox/phase68_manual_ok.txt`
- `session.pending_save["steps"]` contains only the executed sandbox write
- `session.last_tool_calls` contains only the executed sandbox write
- `workspace/memory/traces/trace_*.json` contains only the executed sandbox write
- `workspace/memory/tasks.json` `last_steps_detail` contains only the executed sandbox write
- docs use `sandbox/phase68_manual_ok.txt` as the legal example

## Stop Conditions
If any of these happen, stop and output `BLOCKED`:
- any required artifact in the registry is missing or unreadable
- the locked red tests have been modified
- the requested implementation requires widening generic write access beyond Zone C
- the implementation would require rewriting `implementation_plan.md` or `task.md`

## Codex Startup Checklist
Before coding, read these in order:

1. `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/candidate.md`
2. `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/evidence_gate.md`
3. `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/implementation_plan.md`
4. `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/task.md`
5. `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_handoff.md`
6. `tests/test_phase68_paper_integration.py`
7. `tests/test_loop_integration.py`

Before editing, echo understanding of:
- why Zone C is the accepted generic write boundary
- why `ctx.action_reason == "l1_violation"` is only a symptom and not the source-of-truth bookkeeping contract
- which sinks must inherit the executed-only list

## Return Contract
Write completion status to:

`.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_result.md`

Do not only summarize in chat.

You must explicitly fill:
- `Artifacts Read`
- `Task Coverage`
- `Deviation from Plan`
- `Changed Files`
- `Executed Tests`
- `Behavior Smoke Checks Executed`
- `Observed Proof Signals`
- `Runtime Parity Findings`
- `Suggested Validation Steps`
- `Suggested Review Focus`
- `Untested Runtime States`
- `Open Risks`
