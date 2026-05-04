# Implementation Plan

## Job ID
`lite_20260504_write_boundary_contract`

## Goal
Implement the accepted `harness_lite` candidate for the Phase 68 write-boundary contract:

1. unify the `write_file` / `edit_file` generic write boundary to `workspace/sandbox` (Zone C) across L1 and runtime execution; and
2. change success/task/trace/knowledge bookkeeping to consume a shared executed-only tool-call source instead of the pre-dispatch proposal list.

## Source Context
- `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/candidate.md`
- `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/review_packet.md`
- `.agent/artifacts/harness_lite/lite_20260504_write_boundary_contract/evidence_gate.md`
- `nanobot/agent/tool_setup.py`
- `nanobot/agent/worker/bridge.py`
- `nanobot/agent/middleware/verification_mw.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/loop.py`
- `nanobot/agent/state_handler.py`
- `nanobot/agent/trace_archive.py`
- `docs/tests/manual_guides/phase_68_manual_test_guide.md`
- `docs/archive/phase_68_paper_integration.md`
- `tests/test_phase68_paper_integration.py`
- `tests/test_loop_integration.py`

## Blast Radius Analysis
- `nanobot/agent/loop.py`
  High blast radius. This is the authoritative source for `LoopResult.tool_calls_with_args`, save prompts, task tracking, trace dump inputs, and implicit-feedback inputs. A semantic mistake here will either keep the current false-positive pollution or silently drop legitimate executed steps.
- `nanobot/agent/middleware/verification_mw.py`
  High blast radius. This is the L1 pre-dispatch owner for generic file-write interception. Wrong boundary propagation keeps the current paper/runtime split alive.
- `nanobot/agent/verification.py`
  High blast radius. This file owns R07 path resolution and user-visible rewrite hints. A bad change could either over-block legitimate sandbox writes or re-open workspace-root drift.
- `nanobot/agent/state_handler.py`
  Medium blast radius. The redo/re-execute path writes `result.tool_calls_with_args` back into `session.last_tool_calls`; if that path keeps old semantics, post-fix pollution can re-enter through an alternate route.
- `nanobot/agent/trace_archive.py`
  Medium blast radius. Trace files are developer-facing evidence artifacts; if they continue to archive proposed-but-never-executed tool calls, the proof channel stays unreliable.
- `docs/tests/manual_guides/phase_68_manual_test_guide.md`
  Medium blast radius. This is the human acceptance contract. Leaving the legal-write example at workspace root would preserve an explicit false contract even after code is fixed.
- `docs/archive/phase_68_paper_integration.md`
  Medium blast radius. This is the historical archive for the previous Phase 68 slice. It must stop claiming that the generic write boundary shipped as workspace-root.
- `tests/test_phase68_paper_integration.py` and `tests/test_loop_integration.py`
  Medium blast radius. These are the most direct places to lock the runtime boundary contract and the executed-only bookkeeping contract.

## Zone Declaration
**ZONE A**

Core loop, middleware, verification, runtime bookkeeping, and trace semantics are in scope.

Stable green baseline command for this environment:

`D:\Python\nanobot\.venv311\Scripts\python.exe -m pytest tests/test_loop_integration.py tests/test_loop_cleanup.py tests/test_session_pending.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py tests/adversarial/test_truncation_safety.py tests/adversarial/test_ssrs_false_positive.py tests/adversarial/test_rpa_bounds.py tests/adversarial/test_phase64_zone_a_adversarial.py tests/adversarial/test_phase59_l0_injection.py tests/adversarial/test_path_traversal.py -W ignore -v --basetemp .pytest_tmp_execute_phase_lite_20260504_write_boundary_contract_zone_a`

Recorded result on 2026-05-04:

- `195 passed`

Environment note:

- PowerShell did not expand `tests/test_loop*.py`-style globs for `pytest`.
- Default `tmp_path` under `%LOCALAPPDATA%\Temp` and an attempted `C:\tmp` basetemp both hit permission noise in this environment.
- A repo-local `--basetemp` path inside the workspace produced the stable green baseline above.

## Implementation Strategy
1. **Make Zone C the explicit L1 write root**
   - `VerificationMiddleware` should stop passing the workspace root as the generic file-write boundary.
   - Pass an explicit `workspace / "sandbox"` root into `VerificationLayer.check_rules(...)`.
   - Prefer a parameter name that matches the real contract (`write_boundary_dir`, `allowed_write_root`, or equivalent) rather than continuing the misleading `workspace` name.

2. **Align R07 semantics and wording to Zone C**
   - `verification.py` should resolve `write_file` / `edit_file` targets against the explicit Zone C root.
   - Generic file-write failures should no longer say “within the workspace directory”; the wording must reflect the sandbox boundary.
   - This must be a contract alignment, not a permission expansion. `tool_setup.py` and `worker/bridge.py` remain the source of truth that workspace root is read-only while Zone C is writable.

3. **Move authoritative bookkeeping to executed-only calls**
   - `loop.py` must stop merging `response.tool_calls` into `tool_calls_with_args` before middleware runs.
   - Pre-dispatch proposals may still be logged ephemerally for per-turn diagnostics, but they must not become the persisted or returned source of truth.
   - After `pipeline.run_turn(ctx)`, merge only the calls that actually reached execution into `LoopResult.tool_calls_with_args` and `tools_used`.
   - The intended minimal proof that a call executed is that `ToolExecutor` ran and populated `ctx.results` for the corresponding `ctx.tool_calls`; pre-dispatch aborts should contribute nothing.

4. **Audit downstream consumers instead of patching every sink blindly**
   - Existing sinks already consume `LoopResult.tool_calls_with_args`: `_track_request_outcome`, trace dump, save prompts, implicit feedback, and the redo path.
   - The implementation should first try to fix the single shared source (`LoopResult.tool_calls_with_args` semantics).
   - Only if a consumer bypasses that source should it receive a direct patch.

5. **Repair the paper contract**
   - The manual guide’s legal path should become `sandbox/phase68_manual_ok.txt` or an equivalent Zone C path.
   - The archive text must stop claiming that the shipped generic write boundary was workspace-root.

## Contract / Data Structures / Function Signatures
```python
# nanobot/agent/verification.py
def check_rules(
    self,
    tool_calls: list[Any],
    messages: list[dict] | None = None,
    *,
    registry: Any | None = None,
    config_overrides: dict | None = None,
    write_boundary_dir: Path | str | None = None,
) -> RuleResult:
    ...

def _check_rule_sensitive_path(
    tool_calls: list[Any],
    *,
    extra_deny: list[str] | None = None,
    write_boundary_dir: Path | str | None = None,
) -> list[str]:
    ...

# nanobot/agent/loop.py
# Keep the public LoopResult field name if possible, but change its meaning:
# LoopResult.tool_calls_with_args == authoritative executed-only call list
proposed_tool_calls_this_turn: list[dict]
executed_tool_calls_this_turn = [
    {"tool": tc.name, "args": tc.arguments}
    for tc, _ in zip(ctx.tool_calls, ctx.results)
]
```

Implementation preference:

- Do not introduce a second persisted bookkeeping field if the existing `LoopResult.tool_calls_with_args` field can be redefined cleanly as executed-only.
- Do not widen `WriteFileTool` / `EditFileTool` allowlists to make old docs “true”.

## Behavior Contract Matrix
| Scenario Input | Expected Behavior / Level | Hidden Runtime State | Auto Verification | Manual Acceptance Signal |
| --- | --- | --- | --- | --- |
| `write_file(path="sandbox/phase68_manual_ok.txt")` | Allowed. L1 passes; file tool writes; executed call is recorded. | Zone C directory exists at runtime and remains the only writable generic path. | Phase 2 regression in `tests/test_phase68_paper_integration.py` | File exists under `workspace/sandbox`; no R07 |
| `write_file(path="phase68_manual_ok.txt")` at workspace root | Blocked at L1 before executor. No filesystem `allowed_dir` fallback should be needed. | Verification middleware runs before ToolExecutor and receives the same Zone C root as runtime write tools. | Phase 2 regression in `tests/test_phase68_paper_integration.py` | Rewrite hint contains R07 sandbox-boundary message; no file created |
| First proposal writes outside the boundary; later retry writes inside `sandbox/` and succeeds | Final successful bookkeeping contains only the later executed call. | Same session survives across retries; `pending_save`, `last_tool_calls`, trace dump, and implicit feedback all read the same authoritative list. | Phase 2 regression in `tests/test_loop_integration.py` | `pending_save["steps"]`, `session.last_tool_calls`, trace file, and `memory/tasks.json` omit the blocked path |
| Pre-dispatch abort for a non-L1 reason (for example future HITL or middleware abort before executor) | No call is counted as executed merely because it was proposed by the model. | The implementation must not key the contract to the literal string `l1_violation`; the true discriminator is whether ToolExecutor ran. | Phase 2 regression or adversarial probe if a stable path exists | No executed-step pollution after a pre-execution abort |

## Hermeticity / Hidden Runtime States Checklist
- The runtime write boundary is not inferred from docs. It is established by `tool_setup.py` and `worker/bridge.py`, both of which currently create and bind Zone C at runtime.
- `ctx.results` is only populated if `ToolExecutor.execute()` actually runs. This is the key hidden runtime signal that distinguishes execution from mere proposal.
- `action_log` is not a reliable generic file-write execution ledger; it currently tracks browser/RPA-style tools only.
- `session.pending_save`, `session.last_task_key`, and `session.last_tool_calls` persist across turns in session metadata. A bookkeeping bug can therefore pollute later implicit-feedback writes even when the original blocked proposal is long gone from chat.
- Trace archiving is conditional on a live trace id; the executed-only contract still has to hold when tracing is enabled.
- Tests in this repo cannot rely on default OS temp roots in the current environment. Phase 2 should keep using repo-local scratch directories or explicit repo-local `--basetemp`.
- The manual guide and archive are treated as runtime-sensitive contract artifacts, not as optional prose.

## Runtime Artifact Parity Checklist
| Component | Code Location | Runtime Artifact / State | Load Path | If Missing or Wrong |
| --- | --- | --- | --- | --- |
| Main generic write allowlist | `nanobot/agent/tool_setup.py` | `workspace/sandbox` directory and file-tool registration | AgentLoop startup | L1 can drift from runtime execution again |
| Worker generic write allowlist | `nanobot/agent/worker/bridge.py` | worker sandbox root | worker toolset creation | Main path and worker path diverge |
| L1 boundary propagation | `nanobot/agent/middleware/verification_mw.py` | explicit generic write boundary root in middleware | middleware pipeline construction | Pre-dispatch checks keep evaluating the wrong root |
| R07 path enforcement | `nanobot/agent/verification.py` | resolved write target vs Zone C root | VerificationLayer rule evaluation | Workspace-root false positives remain |
| Authoritative executed-call source | `nanobot/agent/loop.py` | `LoopResult.tool_calls_with_args` semantics | every agent turn | All downstream sinks remain polluted |
| Redo / resume bookkeeping | `nanobot/agent/state_handler.py` | `session.last_tool_calls` re-assignment from loop result | pending-knowledge / re-execute path | An alternate route can reintroduce stale proposal semantics |
| Trace proof channel | `nanobot/agent/trace_archive.py` | `workspace/memory/traces/trace_*.json` | trace dump after loop | Developer evidence still shows blocked proposals as if they happened |
| Human/runtime contract | `docs/tests/manual_guides/phase_68_manual_test_guide.md`, `docs/archive/phase_68_paper_integration.md` | manual steps and archive wording | human acceptance and handoff reading | Paper/runtime split remains visible even after code changes |

## Proof Signals / Observable Success Criteria
1. A workspace-root write outside `sandbox/` is rejected with an R07 message that names the sandbox boundary, not the workspace directory.
2. The same illegal path no longer falls through to `Error: Path ... is outside allowed directory ...` from the file tool for the normal generic write contract.
3. A legal `sandbox/phase68_manual_ok.txt` write succeeds and produces a real file in Zone C.
4. In a mixed illegal-then-legal flow, the blocked path never appears in:
   - `LoopResult.tool_calls_with_args`
   - `session.pending_save["steps"]`
   - `session.last_tool_calls`
   - `workspace/memory/traces/trace_*.json`
   - `memory/tasks.json` `last_steps_detail`
5. `docs/tests/manual_guides/phase_68_manual_test_guide.md` and `docs/archive/phase_68_paper_integration.md` both stop telling operators that a workspace-root generic write should succeed.

## Risk Notes
- The most dangerous false fix is to widen runtime write access so old docs keep passing. That would violate the accepted candidate and the existing Zone A / Zone C design.
- If implementation keys “executed-only” to `ctx.action_reason == "l1_violation"`, it will be brittle by design and can miss other pre-execution abort paths.
- If implementation only patches one sink such as `pending_save`, the repo will still fail the accepted design because task tracking, trace dump, and redo bookkeeping will keep old semantics.
- The current environment’s temp-root noise can create misleading failures unrelated to this contract. Phase 2 and Phase 3 commands should continue to use repo-local temp roots where needed.

## Validation Plan
1. In Phase 2, lock direct boundary regressions in `tests/test_phase68_paper_integration.py` for:
   - workspace-root-but-not-sandbox write blocked at L1
   - legal sandbox write allowed
2. In Phase 2, lock executed-only bookkeeping regressions in `tests/test_loop_integration.py` for:
   - mixed illegal-then-legal flow
   - downstream persistence into save prompts / implicit feedback
3. During implementation, rerun the locked red tests first.
4. Before acceptance, rerun the ZONE A green baseline command recorded above.
5. Before acceptance, run a scoped `auto_reviewer.py` pass over the touched files to verify the implementation stayed inside the allowed write set and did not widen the boundary.
