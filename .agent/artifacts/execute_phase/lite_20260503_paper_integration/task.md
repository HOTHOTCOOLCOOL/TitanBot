# Task

- [ ] T01: Add `_is_valid_plan` regex check in `nanobot/agent/loop.py` right before tool dispatch, supporting both `<think>` and `reasoning_content` with numbered or bulleted lists.
- [ ] T02: If invalid, block dispatch, inject user error message, and continue loop.
- [ ] T03: Update `nanobot/agent/middleware/verification_mw.py` to pass `self._agent.workspace` into `check_rules()`.
- [ ] T04: Update `VerificationLayer.check_rules()` and `_check_rule_sensitive_path` in `nanobot/agent/verification.py` to accept `workspace` and enforce `is_relative_to` boundary for `write_file` and `edit_file`.
- [x] T05: Add regression test `test_p0_observability_block` in `tests/test_phase68_paper_integration.py`. Locked in Phase 2 by AgentManager; read-only for Codex.
- [x] T06: Add regression test `test_p0_observability_reasoning_only_pass` in `tests/test_phase68_paper_integration.py`. Locked in Phase 2 by AgentManager; read-only for Codex.
- [x] T07: Add regression test `test_allowed_write_set_block` in `tests/test_phase68_paper_integration.py` using a non-sensitive out-of-bounds path (e.g., `../outside_workspace.txt`). Locked in Phase 2 by AgentManager; read-only for Codex.
