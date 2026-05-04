## Findings

1. [High] Draft 把“非法提案过滤”的验收面收得太窄。当前污染源不是 `pending_save` 或 `last_tool_calls` 两个字段，而是 `tool_calls_with_args` 在 `await pipeline.run_turn(ctx)` 之前就已经累计（`nanobot/agent/loop.py:937-940,961-973`）。这同一份列表后续还会进入 `TaskTracker`（`nanobot/agent/loop.py:475-505`）、TraceArchive（`nanobot/agent/loop.py:999`）、保存提示（`nanobot/agent/loop.py:1797-1806`），而重执行路径还会直接把 `result.tool_calls_with_args` 回写到 `session.last_tool_calls`（`nanobot/agent/state_handler.py:311-325`）。如果实现只补 `pending_save["steps"]` / `session.last_tool_calls`，假阳性仍会留在任务视图、trace、重执行路径里。

2. [Medium] Draft 在“唯一可写边界”与“generic file-write boundary”之间来回切换，证据范围不够支撑前者。`problem_statement.md` 的 `In Scope` 只覆盖 `write_file` / `edit_file`，`Out of Scope` 还明确把 `write_artifact`、`save_skill`、审批型写工具排除在外；`baseline.md` 也把这些列为未决反证。当前证据足够支持“唯一 generic file-write boundary = Zone C / sandbox”，不够支持“所有写路径的唯一边界”。

3. [Medium] Draft 把“至少在 `ctx.action_reason == \"l1_violation\"` 时丢弃本轮暂存”当成最小兜底，但这还是把“executed vs proposed”的分界绑在单个 action reason 字符串上。已知污染点发生在 `pipeline.run_turn(ctx)` 之前（`nanobot/agent/loop.py:937-973`）；如果后续再出现别的 pre-dispatch abort path，这种按 reason 回滚的修法仍可能漏。要么过滤发生在统一 source-of-truth，要么 Candidate 明确承认这只是修当前已知 `l1_violation` 路径，不是稳定记录契约。

## Must Keep

- `write_file` / `edit_file` 的运行时真边界已经是 `workspace/sandbox`，主 Agent 和 Worker 都一致，不要把“修复口径漂移”做成“放宽运行时权限”（`nanobot/agent/tool_setup.py:50-59`, `nanobot/agent/worker/bridge.py:119-133`, `nanobot/agent/tools/filesystem.py:11-15`）。
- 当前冲突是真实存在的双边界：L1 还按 workspace 根判断，执行层按 sandbox 判断；这不是假设（`nanobot/agent/middleware/verification_mw.py:40-45`, `nanobot/agent/verification.py:282-316`）。
- `ARCHITECTURE.md` 里的 pre-dispatch / fail-closed 原则要保留：边界证明要发生在工具派发前，不能靠执行后报错或知识库记录补判（`docs/rules/ARCHITECTURE.md:114`）。
- “本地 pytest 环境有目录权限噪音”这个 caveat 要保留。它只能说明本地基线不干净，不能反过来当作契约正确或错误的证据。

## Weak Claims / Unverified Claims

- “唯一可写边界”如果不加 `generic file-write` 限定，就是超出当前证据。
- “manual guide 的 workspace 根写入只是文案漂移，不是外部承诺”目前没有硬证据；因为 archive 和 manual guide 现在都把 workspace-root 语义写成了已交付契约（`docs/archive/phase_68_paper_integration.md:40-48`, `docs/tests/manual_guides/phase_68_manual_test_guide.md:78-80`）。
- “只处理 `l1_violation` 就足够最小”目前没有被证明；它最多只覆盖当前已观察到的假阳性路径。
- “只改 `verification_mw.py` / `verification.py` / `loop.py` 就够”也还没被证明，除非过滤后的 `tool_calls_with_args` 真的是所有消费者共享的唯一源头；否则 `state_handler.py` 这样的旁路还会继续吃旧语义。

## False Positive Risks

- `workspace` 根下但不在 `sandbox` 下的路径会被当前 L1 放行，再由文件工具以 `outside allowed directory` 拒绝；这会让“边界已在 middleware 生效”看起来像是真的，其实只是执行层兜底。
- 同一请求可以先提非法写，再改成合法写并最终成功；如果 source list 不过滤，知识库和隐式反馈会把非法写提案当成成功经验。
- 如果只修保存提示链路，不修 `tool_calls_with_args` 的统一来源，`TaskTracker` 和 TraceArchive 仍可能把被挡下的提案显示成已完成/已发生步骤。
- 如果 Candidate 继续使用不加限定的“唯一可写边界”，它会在未审查审批型写工具的情况下看起来像已经统一了全部写语义。

## Acceptance Checklist

| A# | Claim | Evidence Method | Proof Signal | Expected Result | If Fail |
| --- | --- | --- | --- | --- | --- |
| A1 | `write_file` / `edit_file` 的 L1 边界与执行层一致，都是 Zone C / `workspace/sandbox` | 直接验证 `verification_mw.py` / `verification.py`，并跑一个“workspace 根但不在 sandbox 下”的写入用例 | 预执行阶段出现 R07；不再落到 `Error: Path ... is outside allowed directory ...` | `workspace/phase68_manual_ok.txt` 这类路径应在 L1 就被拒绝 | 仍然存在双边界，Phase 68 契约没有对齐 |
| A2 | `sandbox` 内合法写入不会被误伤 | 自动化或手工用例写入 `sandbox/phase68_manual_ok.txt` | 文件实际生成在 `workspace/sandbox`；无 R07 | 合法 Zone C 写入成功 | 修复过度收紧，产生回归 |
| A3 | 被 L1 挡下的写入提案不会进入成功步骤记录 | 构造“先非法写、后合法写并最终成功”的场景，检查 `pending_save["steps"]`、`session.last_tool_calls`、`memory/tasks.json` 的 `last_steps_detail`、`sessions/*.jsonl` metadata | 被挡下的路径不出现在任何成功步骤记录里 | 只有真正进入执行链的调用被记账 | 隐式反馈/知识库仍然被假阳性污染 |
| A4 | 过滤作用于统一来源，而不是只补某一个 sink | 检查 `tool_calls_with_args` 的生成/合并点，或补测试覆盖 `TaskTracker`、TraceArchive、重执行路径 | `TaskTracker` 步骤、trace dump、重执行后的 `last_tool_calls` 都不含被挡下的路径 | 所有消费者看到的是同一份“executed only”或等价过滤后的列表 | 仍有旁路保留旧语义，记录契约不闭合 |
| A5 | 纸面契约与运行时契约一致 | 检查 `docs/archive/phase_68_paper_integration.md`、`docs/tests/manual_guides/phase_68_manual_test_guide.md`、后续 `candidate.md` | manual guide 改成 Zone C 路径；archive / candidate 不再把 generic write 边界写成 workspace root | 文档、验收话术、代码边界同口径 | 仍是 paper/runtime split |
| A6 | Candidate 的措辞没有超出证据范围 | 检查 `candidate.md` 的边界表述 | 使用“generic file-write boundary”或明确声明未覆盖审批型写工具 | 结论只覆盖已取证范围 | Candidate 继续过度宣称“唯一可写边界” |
