## Claim / Evidence / Status

| Claim | Evidence | Status |
| --- | --- | --- |
| 主 Agent 运行时把 `write_file` / `edit_file` 限制在 `workspace/sandbox`，不是整个 workspace。 | `tool_setup.py` 明确写着 “Zone A (Workspace) is Read-only. Zone C (sandbox) is writable”，并把 `WriteFileTool` / `EditFileTool` 的 `allowed_dir` 设为 `agent.workspace / "sandbox"`（`nanobot/agent/tool_setup.py:50-59`）。 | Verified |
| Worker 路径重复实现了同样的 Zone A / Zone C 口径。 | `worker/bridge.py` 明确写着 “Zone A (reads) / Zone C (writes) strict boundary” 与 “Writes MUST strictly align to Zone C”，并把 `WriteFileTool` / `EditFileTool` 绑定到 `sandbox_dir`（`nanobot/agent/worker/bridge.py:119-133`）。 | Verified |
| Phase 68 纸面契约当前把 Allowed Write Set 叙述成 “workspace boundary”。 | Phase 68 archive 写明 middleware 把 `self._agent.workspace` 传给 L1，并把 `R07` 文案定义为 “Target path must be within the workspace directory.”（`docs/archive/phase_68_paper_integration.md:12,40-49`）；manual guide 还要求写入 `workspace` 根下的 `phase68_manual_ok.txt` 并期望成功（`docs/tests/manual_guides/phase_68_manual_test_guide.md:78-80`）。 | Verified |
| 当前 L1 验证确实以 `workspace` 根而非 `sandbox` 作为写边界。 | `VerificationMiddleware` 调用 `check_rules(..., workspace=self._agent.workspace)`（`nanobot/agent/middleware/verification_mw.py:36-46`）；`verification.py` 对 `write_file` / `edit_file` 的边界判定是 `resolved_path.is_relative_to(workspace_root)`，并在越界时返回 “within the workspace directory”（`nanobot/agent/verification.py:282-316`）。 | Verified |
| 当前 runtime 已经存在“L1 允许，但文件工具实际拒绝”的双边界。 | `filesystem._resolve_path()` 会在目标路径不在 `allowed_dir` 下时抛出 `PermissionError("Path ... is outside allowed directory ...")`，`WriteFileTool.execute()` 再把它包装成 `Error:` 返回（`nanobot/agent/tools/filesystem.py:11-15,120-130`）。结合 `tool_setup.py:57-59`，可推导出 “workspace 内但 sandbox 外” 的路径会通过当前 L1，却被工具执行层拒绝。 | Verified |
| `tool_calls_with_args` 在进入 middleware / L1 之前就被记录，因而可能收录尚未执行甚至已被 L1 拦截的提案。 | `loop.py` 在 `await pipeline.run_turn(ctx)` 之前就把每个 `response.tool_calls` 追加进 `tools_used` / `tool_calls_with_args`（`nanobot/agent/loop.py:937-940,961-973`）。 | Verified |
| 成功轮次会把上述 `tool_calls_with_args` 直接喂给保存提示和隐式反馈路径。 | 成功时 `pending_save["steps"] = tool_calls_with_args`，`session.last_tool_calls = tool_calls_with_args`（`nanobot/agent/loop.py:1792-1807`）；下一个用户回合若不是负反馈，则 `record_outcome(success=True)` 并对 `session.last_tool_calls` 做 `silent_update_steps()`（`nanobot/agent/loop.py:1350-1373`）。 | Verified |
| “保存到知识库”与“隐式反馈步骤更新”都会把这些记录落到 workspace 内部文件。 | `handle_pending_save()` 直接把 `pending["steps"]` 与 `pending["result_summary"]` 传给 `save_to_knowledge()`（`nanobot/agent/state_handler.py:79-98`）；`TaskKnowledgeStore._save()` 会写 `workspace/memory/tasks.json`（`nanobot/agent/task_knowledge.py:74-78`），而 `Session` 还会把 `pending_save` / `last_task_key` / `last_tool_calls` 持久化到 `sessions/*.jsonl` 元数据（`nanobot/session/manager.py:43-48,345-358`）。 | Verified |
| 当前 shell 中的本地 pytest 基线存在环境级目录权限噪音，不能单独拿来证明代码契约正确与否。 | 尝试执行 `tests/test_phase68_paper_integration.py` 与 `tests/test_loop_integration.py tests/test_session_manager.py` 时，夹具创建 `tmp_path` / `--basetemp` 目录被当前环境拒绝，报 `PermissionError`；错误点是目录创建，不是本任务核心断言。 | Verified (env-noisy) |

## Source of Truth Files

- 边界注册真相：
  - `nanobot/agent/tool_setup.py`
  - `nanobot/agent/worker/bridge.py`
  - `nanobot/agent/tools/filesystem.py`
- Phase 68 纸面契约真相：
  - `docs/tests/manual_guides/phase_68_manual_test_guide.md`
  - `docs/archive/phase_68_paper_integration.md`
  - `docs/rules/ARCHITECTURE.md`
- 运行时记录真相：
  - `nanobot/agent/loop.py`
  - `nanobot/agent/state_handler.py`
  - `nanobot/agent/task_knowledge.py`
  - `nanobot/session/manager.py`
- L1 边界传递真相：
  - `nanobot/agent/middleware/verification_mw.py`
  - `nanobot/agent/verification.py`

## Runtime Artifacts / Hidden Runtime States

- `agent.workspace / "sandbox"`：
  - 当前 generic file write / edit 的真实 allowlist 根。
- `self._agent.workspace`：
  - 当前被传入 L1 R07 的边界根；这是与 `sandbox` 口径漂移的隐藏前提。
- `session.pending_save`：
  - 保存提示挂起状态，携带 `steps` / `result_summary` / `user_request`。
- `session.last_task_key` 与 `session.last_tool_calls`：
  - 下一个用户回合触发隐式反馈时使用；会决定 success/failure 统计与 `last_steps_detail` 更新。
- `sessions/*.jsonl`：
  - `pending_save`、`last_task_key`、`last_tool_calls` 会被持久化进去。
- `memory/tasks.json`：
  - 保存后的知识条目、`result_summary`、`success_count`、`last_steps_detail` 会写入这里。
- 当前 shell / pytest 目录权限：
  - 会影响本地基线命令的可执行性，但不改变上述代码事实。

## Observable Proof Signals

- `R07: Out of bounds write. Target path must be within the workspace directory.`
- `Error: Path <...> is outside allowed directory <.../sandbox>`
- `pending_save["steps"]`
- `session.last_tool_calls`
- `memory/tasks.json` 里的 `steps` / `result_summary` / `last_steps_detail`
- `sessions/*.jsonl` metadata 中的 `pending_save` / `last_task_key` / `last_tool_calls`

## Unknowns

- `write_artifact` 这类带 `SENSITIVE` / HITL 的高风险写工具，是否应被纳入与 `write_file` / `edit_file` 同一“Allowed Write Set”语义，目前未在本任务 source 中被明示。
- 外部 handoff / ADR / execute_phase Artifact 是否还有额外文本依赖 “workspace root 可写” 的口径，本轮未穷举。
- 若仅修复 `loop.py` 的 L1 假阳性记录，TaskTracker / TraceArchive 是否还需要同步引入 “executed vs proposed” 区分，当前属于设计取舍而非既定事实。

## Questions the Critic Must Attack

- 推荐边界到底应是 `workspace/sandbox`，还是应该把 runtime 实现扩宽到整个 workspace？哪一边更符合既有系统约束而不是当前文案？
- “只在 L1 violation 时回滚本轮提议 tool call 记录” 是否足够最小，还是必须引入更明确的 executed-call 结构？
- `write_artifact` / HITL 型写路径若不纳入本轮修复，是否会让“唯一可写边界”这个表述本身失真？
- 若将 manual guide 改成 `sandbox/phase68_manual_ok.txt`，是否会破坏任何现有对外承诺，还是只是修正文档漂移？
