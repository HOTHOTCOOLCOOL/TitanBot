## 当前方案摘要

当前 Draft V1 的主张是：

1. **把 Phase 68 的 generic file-write Allowed Write Set 收口到 `workspace/sandbox`（Zone C）**，而不是整个 workspace。
2. **把被 L1 拦截的写入提案从成功记录链路中剔除**，避免它们进入 `pending_save`、`last_tool_calls`、隐式反馈的 `last_steps_detail`，进而污染知识库里的“成功步骤”。

推荐这样定边界的原因不是“更保守所以更好”，而是因为它与当前真正执行写入的代码路径一致：

- 主 Agent 的 `write_file` / `edit_file` 已经被绑定到 `sandbox_dir`。
- Worker 桥接层也重复了同样的 Zone A / Zone C 口径。
- `exec` 的 `cwd` 也被锚定在 `sandbox`。

Phase 68 当前的 `workspace` 口径更像是一次 paper integration 把 L1 边界扩成了 “workspace root”，但没有同步更新实际 file tool allowlist，也没有同步修正成功记录语义。

## 关键 Trade-off

### 方案 A（当前推荐）

**唯一 generic write 边界 = `workspace/sandbox`**

最小修复包括两部分：

1. 把 L1 R07 的边界输入从 `self._agent.workspace` 改成显式的 `write_boundary_dir`（推荐直接传 `agent.workspace / "sandbox"`，或等价命名的 Zone C root）。
2. 把 `tool_calls_with_args` / `tools_used` 的累积从“LLM 提议时”改成“通过 L1 后再记”，至少要保证 `l1_violation` 本轮不会污染最终 `pending_save["steps"]` 与 `session.last_tool_calls`。

优点：

- 与当前 runtime 真正允许写入的位置一致。
- 不扩大写权限，不会把源码区、session 区、memory 区意外暴露给 `write_file` / `edit_file`。
- 修改面相对集中：`verification_mw.py`、`verification.py`、`loop.py`，外加对应测试 / manual guide。

代价：

- 需要修正文档、manual guide、Phase 68 archive 中已经写成 “workspace” 的话术。
- 若后续产品想允许 workspace 根级写入，需要另开设计而不是继续沿用这份契约。

### 方案 B（不推荐）

**把 runtime file tool 允许范围放宽到整个 workspace**

优点：

- 可以保留 Phase 68 当前 archive / manual guide 的口径。

缺点：

- 会把 `tool_setup.py` 和 `worker/bridge.py` 的 Zone A / Zone C 设计直接推翻。
- 写权限 blast radius 明显变大：源码、sessions、memory、artifacts 都会落到 generic file tool 的可写面上。
- 这不是“最小修复”，而是能力扩张。

## 风险与假设

- 假设本任务讨论的是 **generic file mutation contract**（`write_file` / `edit_file`）而不是所有内部持久化、HITL 写工具的总和。
- 假设知识库里的成功步骤不应该包含任何 **未通过 L1 的提案**，哪怕这些提案出现在同一个最终成功的 agent loop 里。
- 假设 manual guide 里的 `phase68_manual_ok.txt` 只是文案漂移，不是对外承诺的产品语义。

## False Positive Success Paths

1. **L1 看起来允许，执行层实际拒绝**  
   当前 R07 只检查 “是否还在 workspace 内”，所以 `workspace/phase68_manual_ok.txt` 这种路径会通过 L1；但真正执行时，`WriteFileTool` 仍然会因为路径不在 `workspace/sandbox` 下而返回 `Error: Path ... is outside allowed directory ...`。

2. **被 L1 拦截的越界写仍可能混入成功步骤**  
   `loop.py` 在 `await pipeline.run_turn(ctx)` 之前就把 `response.tool_calls` 塞进 `tool_calls_with_args`。如果第一轮提议了 `../outside_workspace.txt` 被 L1 挡下，第二轮改成合法路径并最终成功，那么最终的 `pending_save["steps"]` 和 `session.last_tool_calls` 仍可能带着第一轮的非法写提案。

3. **隐式反馈会把上述污染写进知识库**  
   下一条用户消息若不是负反馈，`record_outcome(success=True)` 会触发 `silent_update_steps()`；如果 `last_tool_calls` 已经被污染，那么 `memory/tasks.json` 里的 `last_steps_detail` 会把非法写路径当成“成功经验”。

4. **TaskTracker 也会吃到同一份污染列表**  
   `_track_request_outcome()` 同样消费 `tool_calls_with_args` 并把步骤标成 completed / failed；即使最终成功来自后续纠正轮次，前一轮 L1-blocked 提案也可能在任务视图里看起来像曾经完成过。

## 最小修复草案

### 代码落点

1. `nanobot/agent/middleware/verification_mw.py`
   - 不再把 `workspace=self._agent.workspace` 作为 generic write 边界。
   - 改为显式传 `write_boundary_dir=self._agent.workspace / "sandbox"`（名称可调整，但语义要明确成 Zone C）。

2. `nanobot/agent/verification.py`
   - R07 的边界文案从 “workspace directory” 改成与 Zone C 对齐的表达。
   - 对 `write_file` / `edit_file` 的越界判定改成相对 `sandbox` 根，而不是整个 workspace 根。

3. `nanobot/agent/loop.py`
   - 不要在 L1 之前就把本轮 `response.tool_calls` 永久并入 `tool_calls_with_args`。
   - 最小实现可以采用“本轮暂存 + L1 通过后再合并”的方式。
   - 若保持现有结构，也至少要在 `ctx.action_reason == "l1_violation"` 时丢弃本轮暂存，不能直接 `continue` 留下污染记录。

### 最小数据语义

- `pending_save["steps"]`：只允许包含 **通过 L1 且真正进入执行链** 的 tool call。
- `session.last_tool_calls`：只允许包含上述过滤后的步骤。
- `silent_update_steps()`：继续复用现有实现，但输入必须已被过滤。

### 建议新增回归

1. `write_file` 写到 `../outside_workspace.txt` 时，L1 直接给出 Zone C 越界信号。
2. `write_file` 写到 `workspace` 根但不在 `sandbox` 下时，也应被 L1 拦截，而不是放到执行层再报 `allowed directory`。
3. “第一轮非法写被 L1 拦截，第二轮合法写成功” 的组合场景下：
   - `pending_save["steps"]` 不得包含第一轮非法路径；
   - `session.last_tool_calls` 不得包含第一轮非法路径；
   - 后续 `silent_update_steps()` 写入的 `last_steps_detail` 不得包含第一轮非法路径。
4. manual guide 的“工作区内写入不应被过度拦截”用例应改为 `sandbox/phase68_manual_ok.txt` 或等价 Zone C 路径。

## 仍待验证的点

- Critic 需要挑战：`write_artifact` 这类高风险审批型写工具是否会让 “唯一可写边界” 的表述失真；如果会，则 Draft V1 需要把措辞收窄为 “唯一 generic file-write boundary”。
- Critic 需要挑战：仅处理 `l1_violation` 是否足够，还是需要把 “executed vs proposed” 区分推广到 TaskTracker / TraceArchive 等更多消费者。
- Critic 需要挑战：是否存在未纳入 source 的 execute_phase handoff 或 ADR 文本强依赖 “workspace root 可写”。
