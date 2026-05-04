# Baseline

## Claim / Evidence / Status

| # | Claim | Evidence | Status |
| --- | --- | --- | --- |
| 1 | 当前仓库的 CLI 主入口是 `Typer` 体系，而不是 `argparse` 单文件脚本。 | `nanobot/cli/commands.py` 定义顶层 `typer.Typer`；`nanobot/__main__.py` 直接导入该 app；`pyproject.toml` 的 `project.scripts` 将 `nanobot` 指向 `nanobot.cli.commands:app`；`tests/test_commands.py` 用 `CliRunner` 测 CLI。 | Verified |
| 2 | 仓库已经把 `.agent/artifacts/<workflow>/<job_id>/` 当作 Artifact-first 工作流的标准落盘位置。 | `.agent/workflows/harness_lite.md`、`.agent/workflows/harness_heavy.md`、`.agent/workflows/execute_phase.md` 与 `.agent/artifacts/execute_phase/README.md` 都采用该路径约定。 | Verified |
| 3 | 运行时侧已经存在基于 `write_artifact` + HITL 的 Planning Gate，且 ADR-59 明确写过“不要再引入新的 planning state machine / DAG”。 | `nanobot/tools/write_artifact.py`、`docs/antigravity_architecture_reference.md`、`docs/adr/ADR-59-antigravity-pattern-integration.md`。 | Verified |
| 4 | 运行时侧已经存在持久化任务跟踪能力，不宜再随意引入第二套“任务状态真相源”。 | `nanobot/agent/task_tracker.py` 将任务持久化到 `workspace/memory/tasks_tracking.json`；`docs/antigravity_architecture_reference.md` 明确建议复用 `TaskTracker`。 | Verified |
| 5 | 运行时侧已经存在 `StateHandler`，若再在 `nanobot.agent` 下新增一个泛化 `state_machine.py`，命名和职责都会出现重叠风险。 | `nanobot/agent/state_handler.py`。 | Verified |
| 6 | 原始文档中的“先脚手架空 Markdown 文件”与“只要文件存在且 non-empty 就允许推进阶段”两条要求彼此冲突。 | `docs/Harness Orchestration Phase 1 Artifact-only MVP.md` 同时要求 scaffold boilerplate Markdown files 与用“exists and non-empty”做 gate check。若模板含标题或占位符，检查将被提前满足。 | High-confidence inference |
| 7 | `nanobot/agent/harness/` 目前并不存在，因此这是一个全新的表面积，适合在边界清楚时一次性加进去。 | `rg --files nanobot` 当前没有 `harness` 包。 | Verified |
| 8 | 目前存在两种根路径语义：运行时工具偏向 `Config.workspace_path`，而 harness 工作流文档偏向 repo 根目录下的 `.agent/`。这件事在原计划里没有被定死。 | `nanobot/config/schema.py`、`nanobot/utils/helpers.py`、`nanobot/tools/write_artifact.py` 使用 workspace；`.agent/workflows/harness_lite.md` 和相关文档使用 repo 根目录 `.agent/`。 | Open decision |
| 9 | Windows 友好的原子替换辅助函数已经存在，后续若写 `state.json`，应优先复用它而不是自造一套写盘逻辑。 | `nanobot/utils/helpers.py::safe_replace()`。 | Verified |
| 10 | `harness_heavy` 已经有明确文档契约，但它明显扩大了 MVP 的阶段定义、模板与验证面。 | `.agent/workflows/harness_heavy.md`。 | Verified |
| 11 | 现有测试习惯更偏向对 Typer app 做单元/集成测试，而不是大量 shell-out 到独立 CLI 脚本。 | `tests/test_commands.py`。 | Verified |
| 12 | 当前 repo 的 Artifact-first 流程强调“thin launcher, fat artifact”，因此任何新 CLI 只能打印固定 launcher 和状态，不应把真正上下文继续塞回聊天。 | `.agent/workflows/harness_lite.md`、`.agent/workflows/execute_phase.md`。 | Verified |

## Source of Truth Files

- `docs/Harness Orchestration Phase 1 Artifact-only MVP.md`
  - 待修订的原始计划文档
- `.agent/workflows/harness_lite.md`
  - 当前会话必须遵守的 Lite 流程契约
- `.agent/workflows/harness_heavy.md`
  - Heavy 模式的阶段与 Artifact 清单，决定是否要在 MVP 中并行支持
- `.agent/workflows/execute_phase.md`
  - 下游编码阶段的 Artifact-first 交接方式
- `nanobot/cli/commands.py`
  - 现有 CLI 技术栈、命令注册方式、测试入口约定
- `nanobot/__main__.py`
  - `python -m nanobot` 的真实入口
- `pyproject.toml`
  - 包脚本与依赖约定
- `tests/test_commands.py`
  - CLI 测试的既有模式
- `nanobot/tools/write_artifact.py`
  - 已存在的 Planning Gate 工具
- `nanobot/agent/task_tracker.py`
  - 已存在的任务持久化与进度表达
- `nanobot/agent/state_handler.py`
  - 已存在的运行时状态处理器
- `nanobot/config/schema.py`
  - `workspace_path` 语义来源
- `nanobot/utils/helpers.py`
  - 路径辅助与 Windows 友好原子写盘能力
- `docs/antigravity_architecture_reference.md`
  - 既有架构对 Planning Mode / Artifact Tracking 的最终对齐结论
- `docs/adr/ADR-59-antigravity-pattern-integration.md`
  - “不要再引入 planning state machine” 的正式 ADR 背景

## Unknowns

- Harness Artifact 的默认根目录到底应当是 repo 根目录，还是 `Config.workspace_path`？
- Phase 1 是否要一次性支持 `lite` + `heavy` 两种模式，还是只把 `heavy` 设计成可扩展但暂不 fully verify？
- `state.json` 应当是“权威状态机”，还是“元数据 + 派生快照”？
- 对脚手架文件的“ready”判定到底采用什么机制，才能避免模板文件误触发阶段推进？
- Prompt 模板是否直接固化在 Python 代码里，还是与 workflow 文档做更显式的同步机制？

## Questions the Critic Must Attack

- 如果放弃显式 `state_machine.py`，改用“基于 Artifact 的派生式阶段检查器”，会不会让状态表达过弱？
- 新 CLI 默认落到 repo 根目录 `.agent/`，会不会与现有 runtime/workspace 语义冲突得太厉害？
- 把命令集挂进现有 `Typer` app 是否会带来不必要的耦合，还是这是最小摩擦路径？
- 通过 `<!-- HARNESS:STUB -->` 之类的占位哨兵来解决脚手架冲突，是否足够稳健？
- Phase 1 同时支持 `heavy` 是否值得，还是应该把 `lite` 先做稳，再把 `heavy` 做成 Phase 1.5？
- 当前计划是否仍然在实质上重造了一个“第二运行时”，违背了 repo 已有的架构戒律？
