# Task

- [x] T01 Add direct regressions in `tests/test_phase68_paper_integration.py` proving that generic writes to workspace root outside `sandbox/` are blocked at L1 and that legal writes inside `sandbox/` still succeed. Locked in Phase 2 by AgentManager; read-only for Codex.
- [x] T02 Add executed-only bookkeeping regressions in `tests/test_loop_integration.py` proving that a blocked write proposal never reaches `pending_save["steps"]`, `session.last_tool_calls`, trace output, or implicit-feedback step details after a later legal write succeeds. Locked in Phase 2 by AgentManager; read-only for Codex.
- [ ] T03 Update `nanobot/agent/middleware/verification_mw.py` so generic file-write checks receive an explicit Zone C boundary root instead of the workspace root.
- [ ] T04 Update `nanobot/agent/verification.py` so R07 resolves `write_file` / `edit_file` targets against the Zone C root and replaces workspace-root wording with sandbox-boundary wording.
- [ ] T05 Update `nanobot/agent/loop.py` so `LoopResult.tool_calls_with_args` and `tools_used` are built from executed calls only, not from pre-dispatch proposals.
- [ ] T06 Make the smallest necessary consumer follow-up in `nanobot/agent/state_handler.py` and/or `nanobot/agent/trace_archive.py` only if the `LoopResult` source cleanup alone does not satisfy T02.
- [ ] T07 Update `docs/tests/manual_guides/phase_68_manual_test_guide.md` and `docs/archive/phase_68_paper_integration.md` so the paper contract matches Zone C and no longer claims workspace-root generic writes are legal.
- [ ] T08 Re-run the locked red tests, the recorded ZONE A green baseline, and the scoped reviewer checks, then write the evidence summary into `.agent/artifacts/execute_phase/lite_20260504_write_boundary_contract/codex_result.md`.
