# Codex Handoff

## Job ID
`lite_20260503_paper_integration`

## Artifact Directory
`.agent/artifacts/execute_phase/lite_20260503_paper_integration/`

## Artifact Registry
- **Candidate Design**: `.agent/artifacts/harness_lite/lite_20260503_paper_integration/candidate.md`
- **Implementation Plan**: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/implementation_plan.md`
- **Task List**: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/task.md`
- **Handoff Contract**: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_handoff.md`
- **Result Template**: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_result.md`
- **Feedback Slot**: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_feedback.md`
- **Implementation Files**:
  - `nanobot/agent/loop.py`
  - `nanobot/agent/verification.py`
  - `nanobot/agent/middleware/verification_mw.py`
- **Read-Only Red Tests**:
  - `tests/test_phase68_paper_integration.py`

## Source Context
`.agent/artifacts/harness_lite/lite_20260503_paper_integration/candidate.md`

## Goal
Implement the P0 observability contract (mandatory `<think>` tag OR `reasoning_content`) in `loop.py` and Allowed Write Set runtime interception in `verification.py` for `write_file` / `edit_file`.

## Allowed Write Set
You may ONLY modify:
- `nanobot/agent/loop.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/middleware/verification_mw.py`
- `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_result.md`

## Forbidden Write Set
Do NOT modify any other files.
Especially forbidden:
- `tests/test_phase68_paper_integration.py`
- `tests/test_loop_integration.py`
- `nanobot/agent/context.py`
- any artifact file other than `codex_result.md`

## Red Tests to Satisfy
These tests are already written and locked by AgentManager in Phase 2. Treat them as read-only acceptance gates.
- `tests/test_phase68_paper_integration.py::test_p0_observability_block`
- `tests/test_phase68_paper_integration.py::test_p0_observability_reasoning_only_pass`
- `tests/test_phase68_paper_integration.py::test_allowed_write_set_block`

## Red Test Command
Use this exact command first in the current environment:

`.\.venv\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py -k "p0_observability or allowed_write_set_block" -W ignore -v -p no:tmpdir`

## Failure Summary
- `test_p0_observability_block`
  Current behavior still reaches the middleware pipeline and returns `pipeline should not run`.
  Expected behavior is to inject `Error: P0 observability contract violation...` and retry before any tool dispatch.
- `test_p0_observability_reasoning_only_pass`
  Current behavior reaches the pipeline, but never emits `logger.info("P0 Plan Verified")`.
  Expected behavior is to accept a numbered/bulleted `reasoning_content` plan and log the proof signal.
- `test_allowed_write_set_block`
  Current `VerificationMiddleware` + `VerificationLayer` path does not abort `write_file("../outside_workspace.txt")`.
  Expected behavior is `ctx.action_reason == "l1_violation"` and an injected rewrite hint containing `R07: Out of bounds write`.

## Expected Repair Boundary
- Satisfy the failures only by editing `loop.py`, `verification.py`, and `verification_mw.py`.
- Do not weaken, delete, or rewrite the new red tests.
- T05/T06/T07 in `task.md` are already complete Phase-2 setup tasks and must remain read-only during Codex implementation.
- Keep the repair narrowly scoped to:
  - pre-dispatch P0 validation for tool calls
  - reasoning-only acceptance via `reasoning_content`
  - workspace-relative write interception for `write_file` / `edit_file`

## Green Exit Criteria
- `.\.venv\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py -W ignore -v`
- `.\.venv\Scripts\python.exe -m pytest tests/test_loop_integration.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py -W ignore -v`

## Behavior Smoke Checks
1. Run a local agent session and ask the agent to execute a tool without a valid `<think>` block and without valid `reasoning_content`. It must receive an injected error `Error: P0 observability contract violation...` before dispatch.
2. Run a local agent session where the model provides valid bulleted `reasoning_content` but no `<think>` tag. Tool dispatch should proceed and `P0 Plan Verified` should appear in logs.
3. Ask the agent to write `../outside_workspace.txt` relative to its workspace. It must fail through the Verification Middleware, not by a broader sensitive-path rule.

## Runtime Parity Checks
- `nanobot/agent/loop.py`
  The P0 gate MUST execute before `ContextBuilder.add_assistant_message()` so ADR-62 nullification cannot erase the evidence.
- `nanobot/agent/middleware/verification_mw.py`
  `self._agent.workspace` MUST be passed into `verification.check_rules(...)`.
- `nanobot/agent/verification.py`
  The write target MUST be resolved against the provided workspace and checked with `Path.resolve()` plus `is_relative_to(...)` for `write_file` / `edit_file`.

## Proof Signals to Inspect
- injected retry text containing `Error: P0 observability contract violation`
- `logger.info("P0 Plan Verified")`
- `L1: Blocking X violation(s)`
- rewrite hint containing `R07: Out of bounds write`

## Stop Conditions
If any requested artifact is missing, unreadable, or contradictory, stop and output `BLOCKED`.

## Codex Startup Checklist
1. Read `.agent/artifacts/harness_lite/lite_20260503_paper_integration/candidate.md`
2. Read `.agent/artifacts/execute_phase/lite_20260503_paper_integration/implementation_plan.md`
3. Read `.agent/artifacts/execute_phase/lite_20260503_paper_integration/task.md`
4. Read `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_handoff.md`
5. Read `tests/test_phase68_paper_integration.py` as a read-only red-test contract.
6. Echo your understanding of:
   - the pre-dispatch P0 gate
   - the reasoning-only acceptance path
   - the workspace write boundary

## Return Contract
Write your completion status to `.agent/artifacts/execute_phase/lite_20260503_paper_integration/codex_result.md`.
Do not only summarize in chat.
You must explicitly fill:
- `Artifacts Read`
- `Task Coverage`
- `Changed Files`
- `Executed Tests`
- `Behavior Smoke Checks Executed`
- `Observed Proof Signals`
- `Runtime Parity Findings`
- `Untested Runtime States`
