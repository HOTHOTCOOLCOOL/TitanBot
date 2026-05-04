# Codex Handoff

Job ID: `phase_20260425_harness_orchestration_phase1_mvp`
Artifact Directory: `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/`

## Handoff Status

当前文件已完成 **execute_phase 第 2 阶段红测锁定**。  
它现在是可交给 Codex 的正式执行契约。

AgentManager 已完成：

1. 第 2 阶段红测编写与失败锁定
2. `Red Tests to Satisfy` 回填
3. `codex_result.md` 模板预创建
4. `codex_feedback.md` 路径预创建

## Artifact Registry

- `implementation_plan.md`
  - `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/implementation_plan.md`
- `task.md`
  - `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/task.md`
- `codex_handoff.md`
  - `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_handoff.md`
- `codex_result.md`
  - `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_result.md`
- `codex_feedback.md`
  - `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_feedback.md`
- Accepted Lite Candidate
  - `.agent/artifacts/harness_lite/lite_20260425_harness_orchestration_plan/candidate.md`
- Candidate Evidence Gate
  - `.agent/artifacts/harness_lite/lite_20260425_harness_orchestration_plan/evidence_gate.md`
- Harness Lite Workflow
  - `.agent/workflows/harness_lite.md`
- Blueprint
  - `docs/harness_orchestration_blueprint.md`
- Historical Phase 1 Draft (superseded reference only)
  - `docs/Harness Orchestration Phase 1 Artifact-only MVP.md`
- Existing CLI Entry
  - `nanobot/cli/commands.py`
- Packaging / CLI Script Entry
  - `pyproject.toml`
- Existing CLI Tests
  - `tests/test_commands.py`
  - `tests/test_cli_input.py`
- New Red Tests
  - `tests/test_harness_cli.py`
- Planned Target Code
  - `nanobot/cli/commands.py`
  - `nanobot/agent/harness/__init__.py`
  - `nanobot/agent/harness/root.py`
  - `nanobot/agent/harness/job.py`
  - `nanobot/agent/harness/scaffold.py`
  - `nanobot/agent/harness/stages.py`
  - `nanobot/agent/harness/prompts.py`

## Source Context

上游 `harness_lite` 已完成计划门禁，当前 accepted candidate 已将本任务收敛为：

- repo-local
- Artifact-first
- lite-only
- fail-closed root policy
- exact-output launcher protocol
- `state.json` snapshot, not truth source

本次 execute_phase 的目标不是扩展设计，而是把这套契约代码化，并以 A1-A6 为退出条件。

## Goal

实现 Harness Orchestration Phase 1 MVP：

- `nanobot harness start --mode lite --goal ... --source ...`
- `nanobot harness status --job <job_id>`
- `nanobot harness advance --job <job_id>`

并满足 A1-A6。

## Allowed Write Set

- `nanobot/cli/commands.py`
- `nanobot/agent/harness/__init__.py`
- `nanobot/agent/harness/root.py`
- `nanobot/agent/harness/job.py`
- `nanobot/agent/harness/scaffold.py`
- `nanobot/agent/harness/stages.py`
- `nanobot/agent/harness/prompts.py`
- `tests/test_harness_cli.py`

如果实现中需要对 `nanobot/agent/harness/` 再细分文件，可以新增同目录文件；但不要把逻辑扩散到该目录之外，除非 AgentManager 在第 2 阶段显式更新 Allowed Write Set。

## Forbidden Write Set

- `.agent/workflows/`
- `.agent/artifacts/harness_lite/lite_20260425_harness_orchestration_plan/`
- `docs/`
- `progress_report.md`
- `nanobot/agent/loop.py`
- `nanobot/agent/context.py`
- `nanobot/session/manager.py`
- `nanobot/agent/middleware/`
- `nanobot/agent/verification.py`
- `nanobot/agent/tools/`
- `nanobot/channels/`
- `nanobot/cron/`

## Red Tests to Satisfy

命令：

- `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_harness_cli.py -W ignore -v`

当前失败摘要：

- `9 failed`
- 根因已经被锁定为：CLI 尚未实现 `harness` 命令，错误为 `No such command 'harness'. Did you mean 'channels'?`
- 一旦 `harness` 命令存在，测试会继续约束以下 6 组行为边界：
  - `A1`: lite 路径落盘正确；heavy 明确拒绝；launcher 路径一致
  - `A2`: 实现面保持 lite-only，错误提示明确 `heavy deferred to later phase`
  - `A3`: 缺少 `A# / Status / Evidence / Meaning` 的 `evidence_gate.md` 必须 not ready / blocked
  - `A4`: start / advance launcher exact-output
  - `A5`: repo 根 / 子目录 / repo 外 / repo-workspace 分离 root 行为
  - `A6`: 手工篡改 `state.json` 后，`status/advance` 仍以 Artifact 现状重算并刷新快照

## Green Exit Criteria

- A1-A6 对应测试全部通过
- `tests/test_commands.py` 与 `tests/test_cli_input.py` 继续保持绿色
- 组合回归命令通过：
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py -W ignore -v`
- `start/status/advance` 全部遵守 lite-only、Artifact-first、fail-closed、exact-output 四条主边界
- `state.json` 不再能被当作真相源驱动错误阶段推进

## Stop Conditions

- 任一关键 Artifact 缺失、路径不明或内容互相冲突
- 红测尚未锁定就要求直接开工
- 需要把范围扩展到 `heavy`
- 需要修改 Forbidden Write Set 内的文件
- 需要通过“语义接近”替代 exact launcher contract
- 需要把 `state.json` 变成权威状态机才能实现功能

## Codex Startup Checklist

1. 先读 `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_handoff.md`
2. 再按 `Artifact Registry` 逐项读取关键制品
3. 确认 `Red Tests to Satisfy` 已被 AgentManager 在第 2 阶段改写为具体测试与命令
4. 确认 `codex_result.md` 模板已存在
5. 若以上任一条件不满足，立即 `blocked`
6. 开工前先回显“已读取哪些文件、理解到的目标/边界是什么”

## Return Contract

完成后必须先写回：

- `.agent/artifacts/execute_phase/phase_20260425_harness_orchestration_phase1_mvp/codex_result.md`

内容至少包括：

- `Status`
- `Artifacts Read`
- `Task Coverage`
- `Deviation from Plan`
- `Changed Files`
- `Executed Tests`
- `Suggested Validation Steps`
- `Suggested Review Focus`
- `Open Risks`
- `Need Manager Review`

若执行失败或被阻塞，也必须把原因按上述格式写入 `codex_result.md`，而不是只在聊天里口头总结。
