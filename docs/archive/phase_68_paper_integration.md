# Phase 68: Paper Integration Slice

**Date:** 2026-05-04  
**Job ID:** `lite_20260503_paper_integration`  
**Status:** Accepted slice complete; broader Phase 68 orchestration remains open

## 1. Background

Phase 65 had already locked in the Artifact-first contract for `execute_phase`, but Phase 68 still had a paper-vs-runtime gap:

- the P0 observability rule existed in plan text, yet no runtime owner enforced it before tool dispatch;
- the Allowed Write Set contract existed in tests and handoff text, yet the real workspace root was not carried through `VerificationMiddleware` into `VerificationLayer`.

This slice closes those two contract holes without claiming that the rest of Phase 68 is finished.

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

### `nanobot/agent/middleware/verification_mw.py`

- The middleware now passes `self._agent.workspace` into `verification.check_rules(...)` so L1 rules can evaluate the real workspace boundary instead of relying on ambient assumptions.

### `nanobot/agent/verification.py`

- `check_rules()` and `_check_rule_sensitive_path()` now accept `workspace`.
- `write_file` and `edit_file` resolve their targets relative to that workspace and block escapes with:

```text
R07: Out of bounds write. Target path must be within the workspace directory.
```

- Resolution failures now fail closed with diagnostics instead of silently degrading behind broad exception handling.

## 3. Acceptance Evidence

Recorded on 2026-05-04:

- `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_phase68_paper_integration.py -W ignore -v` -> `12 passed`
- `D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_loop_integration.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py -W ignore -v` -> `130 passed`
- `D:\Python\nanobot\.venv311\Scripts\python.exe .agent/scripts/auto_reviewer.py --context "核对 task.md 落地情况，防范架构腐化" --files nanobot/agent/loop.py nanobot/agent/verification.py nanobot/agent/middleware/verification_mw.py tests/test_phase68_paper_integration.py tests/test_phase31_verification.py` -> pass

Observed proof signals:

- `Error: P0 observability contract violation`
- `P0 Plan Verified`
- `L1: Blocking X violation(s)`
- `R07: Out of bounds write`

## 4. Postmortem

### False-positive paths that showed up during this job

- A response could look compliant in logs or chat while the tool pipeline had already been reached.
- A workspace-boundary implementation could appear present in code review while broad exception handling quietly downgraded it into silent allow or silent uncertainty.

### Hard evidence that now matters

- The P0 gate runs before `add_assistant_message()`, so ADR-62 nullification cannot erase the evidence channel before enforcement.
- The real workspace root is passed from middleware into L1 verification instead of being reconstructed implicitly.
- Boundary-resolution failures are visible and fail closed.

### What remains open in broader Phase 68

- Codex auto-dispatcher
- `codex_result.md` completion detector
- plan-scoped approval token
- real runtime orchestration acceptance across multi-session / HITL / sandbox conditions

## 5. Files Touched in This Slice

- `nanobot/agent/loop.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/middleware/verification_mw.py`
- `tests/test_phase68_paper_integration.py`
- `.agent/artifacts/execute_phase/lite_20260503_paper_integration/`
