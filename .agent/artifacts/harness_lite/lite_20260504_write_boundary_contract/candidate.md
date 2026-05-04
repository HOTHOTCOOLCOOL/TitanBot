## Adopted Criticisms

1. **采纳 Finding 1（High）**  
   记录污染的统一源头不是 `pending_save` 或 `last_tool_calls` 两个 sink，而是 `tool_calls_with_args` 在 `await pipeline.run_turn(ctx)` 之前就已累计。Candidate 因此不再把修复描述成“补两个字段”，而是改成：所有面向持久化、任务视图、trace、重执行路径的记录，都必须共享同一份 **executed-only** 工具调用列表。

2. **采纳 Finding 2（Medium）**  
   本 Candidate 明确把结论收窄为 **generic file-write boundary**，只覆盖 `write_file` / `edit_file` 及其直接消费链路，不再使用无限定的“唯一可写边界”表述。

3. **采纳 Finding 3（Medium）**  
   本 Candidate 不再把“`ctx.action_reason == "l1_violation"` 时回滚”当成稳定契约。`l1_violation` 最多只是当前已知症状；真正的 source-of-truth 必须是“该调用是否通过 pre-dispatch gate 并进入执行链”，而不是某个 abort reason 字符串。

## Rejected Criticisms

- **无实质性 findings 被驳回。**  
  Critic 的三条主 findings 都被采纳。

- **拒绝把本 Candidate 扩成“所有写路径统一边界”的结论。**  
  这不是对 Critic finding 的反驳，而是对范围膨胀的拒绝：当前 job 的 `In Scope`、`baseline.md` 与证据文件只覆盖 generic file-write contract；`write_artifact`、`save_skill`、审批型写工具仍保持 out of scope，不应被本 Candidate 顺手冒充统一完成。

## Final Candidate

### 结论

本 job 的最终 Candidate 是：

1. **唯一被本任务证明并收口的 generic file-write boundary = Zone C = `workspace/sandbox`。**
2. **L1 的 generic file-write 判定必须与执行层共用同一边界根。**  
   也就是说，`write_file` / `edit_file` 不能再由 L1 按 workspace 根判断、执行层按 sandbox 根判断。
3. **所有面向任务记录、trace、保存提示、隐式反馈的工具调用账本，都必须表示 “executed-only” 调用，而不是 LLM 原始提议。**

### 最小修复方案

1. `nanobot/agent/middleware/verification_mw.py`
   - 不再把 `workspace=self._agent.workspace` 传给 generic file-write 检查。
   - 改为显式传 `self._agent.workspace / "sandbox"`，并建议同步把参数名从 `workspace` 改成更准确的 `write_boundary_dir` 或 `allowed_write_root`，避免继续制造“L1 用的是 workspace 根”的语义错觉。

2. `nanobot/agent/verification.py`
   - R07 的 generic file-write 边界改成相对 Zone C 根检查，而不是相对 workspace 根检查。
   - R07 文案同步从 “within the workspace directory” 收口到与 Zone C 对齐的表述。
   - 这一步的目标不是放宽权限，而是让 pre-dispatch contract 与 runtime allowlist 真正同口径。

3. `nanobot/agent/loop.py`
   - 将当前 “提议即累计” 的 `tool_calls_with_args` 语义拆分为：
     - **ephemeral proposed calls**：可用于当轮日志，但不进入持久化/用户态/trace 契约；
     - **authoritative executed calls**：只有通过 pre-dispatch gate 并真正进入执行链的调用，才可并入 `LoopResult.tool_calls_with_args` 与 `tools_used`。
   - 最小实现方式应当是：在 `pipeline.run_turn(ctx)` 之后，依据真正进入执行链的调用列表再合并到返回值；而不是在 `response.tool_calls` 刚生成时就永久落账。
   - 这样一来，`TaskTracker`、TraceArchive、`pending_save`、`session.last_tool_calls`、重执行路径都会自动继承同一份过滤后语义，而不需要逐个 sink 打补丁。

4. 文档 / 手工验收契约
   - `docs/tests/manual_guides/phase_68_manual_test_guide.md` 的合法写入样例应改为 `sandbox/phase68_manual_ok.txt` 或等价 Zone C 路径。
   - `docs/archive/phase_68_paper_integration.md` 与后续 handoff 文本，不得再把 generic write boundary 写成 workspace 根。

### 为什么这是最小修复

- 它不扩大既有权限面；只消除 Phase 68 引入的 paper/runtime 口径漂移。
- 它不需要为每个消费者各写一套“非法路径过滤”；只要统一 `LoopResult.tool_calls_with_args` 的语义即可。
- 它兼容 Critic 指出的旁路：`TaskTracker`、TraceArchive、保存提示、隐式反馈、重执行路径都依赖这一统一来源。

## Runtime Preconditions / Parity Assumptions

- `tool_setup.py` 与 `worker/bridge.py` 继续作为 generic file-write allowlist 的事实来源，保持 `workspace/sandbox` 可写、workspace 其余区域只读。
- `LoopResult.tool_calls_with_args` 继续是下游记录消费者共享的主数据源；若后续发现有旁路消费者直接读原始 `response.tool_calls`，则本 Candidate 需要补充覆盖。
- `write_artifact`、`save_skill`、审批型写工具不被纳入本 Candidate 的边界宣称；它们若需要统一设计，应另起 job。
- 本地 shell 环境当前存在目录创建权限噪音，因此运行时 smoke proof 需要在可写测试环境中补齐。

## Residual Risks

- 若实现阶段只修 L1 边界、不修 authoritative executed-call source，则 generic write boundary 虽对齐，成功记录仍会继续污染。
- 若实现阶段只修 `pending_save` / `last_tool_calls` 两个 sink，而不收口 `LoopResult.tool_calls_with_args`，`TaskTracker`、TraceArchive、重执行路径仍会保留旧语义。
- 审批型写工具仍未纳入本 job 的统一边界结论；因此 Candidate 必须持续使用 `generic file-write boundary` 的限定措辞。
- 当前环境下缺少干净的 runtime smoke，因此 A2 这类“合法 Zone C 写入不误伤”的证明还需后续补足。

## Evidence Plan

- `A1`：确认 L1 与执行层共用 Zone C 根，而不是 `workspace` 根。
- `A2`：在干净运行环境中证明 `sandbox/phase68_manual_ok.txt` 可写且无 R07。
- `A3`：证明先非法写、后合法写的混合场景里，被挡下的路径不会出现在 `pending_save["steps"]`、`session.last_tool_calls`、`memory/tasks.json`、`sessions/*.jsonl` 成功记录中。
- `A4`：证明 authoritative record 来源已经统一，因此 `TaskTracker`、TraceArchive、重执行路径看到的也是同一份 executed-only 列表。
- `A5`：证明 manual guide、archive、candidate 的 generic write 口径与代码一致。
- `A6`：证明 Candidate 的措辞始终限定在已取证范围内，没有把审批型写工具混进“唯一边界”。

## Revision Notes

- 本轮 Evidence Gate 不通过：当前 repo 仍然保留 `workspace` vs `sandbox` 双边界，且 `tool_calls_with_args` 仍在 pre-dispatch 阶段累计。
- 因此本 Candidate 现在是 **可执行设计候选**，不是已验证完成的 Phase 68 收口结果。
- 后续若进入实现，应先按本 Candidate 改代码与文档，再重新执行至少一次 Critic + Evidence Gate，或切换到 `execute_phase` 做正式实现与验收。
