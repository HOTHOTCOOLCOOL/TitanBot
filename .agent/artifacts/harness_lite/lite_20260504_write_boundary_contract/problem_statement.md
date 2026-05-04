## Job ID

`lite_20260504_write_boundary_contract`

## Goal

对齐 Phase 68 写边界契约与隐式反馈结果记录，确定唯一可写边界，并给出最小修复方案草案。

## Source Context

- `docs/tests/manual_guides/phase_68_manual_test_guide.md`
- `nanobot/agent/tool_setup.py`
- `nanobot/agent/verification.py`
- `nanobot/agent/middleware/verification_mw.py`
- `nanobot/agent/loop.py`

补充只读核对文件（用于建立事实基线）：

- `nanobot/agent/tools/filesystem.py`
- `nanobot/agent/state_handler.py`
- `nanobot/agent/task_knowledge.py`
- `nanobot/session/manager.py`
- `nanobot/agent/worker/bridge.py`
- `docs/archive/phase_68_paper_integration.md`
- `docs/rules/ARCHITECTURE.md`

## In Scope

- `write_file` / `edit_file` 在主 Agent 路径中的真实可写边界。
- Phase 68 文档、手工验收文案、L1 验证实现三者之间的边界口径是否一致。
- `tool_calls_with_args`、`pending_save`、`last_tool_calls`、隐式反馈更新之间是否会把被 L1 拦截的写入提案误记成成功步骤。
- 最小修复方案的边界定义、代码落点与回归测试需求。

## Out of Scope

- 直接实现代码修复。
- 完整重构 HITL、TaskTracker、TraceArchive 或更大的 Phase 68 orchestration。
- 为 `write_artifact`、`save_skill` 等高风险 / 审批型写工具重新定义统一产品语义，除非它们对本任务结论构成直接反证。
- Phase 68 其余开放项（Codex auto-dispatcher、`codex_result.md` detector、plan token 等）。

## Expected Output

- 一份 `draft_v1.md`，明确：
  - 当前代码中真正生效的写边界；
  - Phase 68 纸面契约与运行时记录之间的冲突点；
  - 推荐的唯一写边界口径；
  - 最小修复方案与需要新增的证明信号 / 回归测试。
