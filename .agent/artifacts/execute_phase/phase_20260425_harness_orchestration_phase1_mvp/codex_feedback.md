# Codex Feedback

Status: rework
Job ID: phase_20260425_harness_orchestration_phase1_mvp

Failed Commands:
- `.\\.venv311\\Scripts\\python.exe .agent\\scripts\\auto_reviewer.py --files nanobot/cli/commands.py nanobot/agent/harness/__init__.py nanobot/agent/harness/root.py nanobot/agent/harness/job.py nanobot/agent/harness/scaffold.py nanobot/agent/harness/stages.py nanobot/agent/harness/prompts.py tests/test_harness_cli.py --context "核对 task.md 落地情况，防范架构腐化"` -> completed, but L2 review conclusion = failed

Key Errors:
- 之前阻塞 Stage 3 的 reviewer/provider 环境问题已经解除：`auto_reviewer.py` 现已能在默认命令下完成 provider 选择、git diff、L2 调用与正确退出码返回；因此这次不再是“外部环境 blocked”。
- 当前剩余问题在 `nanobot/cli/commands.py`：`_load_harness_symbol()` 只做了 stdout/stderr 静默，没有把 `ImportError` / `AttributeError` / 下游 backend runtime error 归一化成用户可读的 fail-closed CLI 错误。
- 结果是：当 `nanobot.agent.harness.*` 模块缺失、符号名漂移、或 backend 运行期抛异常时，`nanobot harness start/status/advance` 可能直接向终端泄露原始 Python traceback，而不是输出明确、可执行的 `BLOCKED:` / 失败提示。
- 这与当前 Phase 1 MVP 的“fail-closed、operator-facing、exact contract”目标不一致，且现有测试未锁定这条异常路径。

Severity A:
- none

Severity B:
- 在 `nanobot/cli/commands.py` 中为动态 harness 依赖加载与下游调用增加 fail-closed 错误处理：
  - `start/status/advance` 遇到 harness 模块/符号缺失或 backend runtime error 时，不得裸抛 traceback 到用户界面。
  - 应输出简洁、可读、可定位的失败信息，并以非零退出码结束。
- 在 `tests/test_harness_cli.py` 中补一条或多条定向测试，锁定上述异常路径，防止后续回归。

Must Fix Files:
- `nanobot/cli/commands.py`
- `tests/test_harness_cli.py`

Boundary Reminder:
- 继续遵守原 handoff 的 Allowed Write Set / Forbidden Write Set。
- 不要扩展到 `heavy` 模式，不要重做架构分层，不要把 CLI 改成依赖新的公共 facade。
- 不要修改 `state.json` “snapshot, not truth source” 的语义；`status/advance` 继续允许按 Artifact 真相重算并刷新快照。
- 不要因为 L2 的过度保守建议去改 A6 已锁定的 `status` 快照刷新行为，也不要为了“未来 heavy”提前重构。

Return Instructions:
- 只修复上面的 CLI 异常处理缺口，并重写 `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_result.md`。
