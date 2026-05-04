# Draft V1

## 当前方案摘要

这次 Phase 1 MVP 不应被实现为“第二个 agent runtime”或“新的 planning state machine”。  
更可落地的方向是：做一个**repo-local、Artifact-first、人工切换友好**的 Harness 辅助层，负责：

1. 创建标准化的 Harness job 目录与模板文件；
2. 依据 Artifact 完成度派生当前阶段，而不是强行维护一套权威状态机；
3. 输出与现有 workflow 文档一致的固定 launcher；
4. 在不自动派工的前提下，帮用户把“开始/查看状态/继续下一阶段”这几个动作标准化。

建议保留原文的“文件驱动、不自动 dispatch worker、先支持 Artifact-only MVP”的目标，但收敛以下实现形态：

- 保留 `nanobot/agent/harness/` 作为核心逻辑包；
- 不再把 `argparse` 作为主入口，而是提供 `Typer` app，并注册到现有 `nanobot` CLI；
- 不再使用独立 `state_machine.py` 作为权威真相源，而是改成“`state.json` + stage inspector”；
- 明确 default root 为**当前 repo 根目录**下的 `.agent/`，同时提供 `--root` 覆盖；
- 通过 stub 哨兵解决“模板文件与 non-empty gate 冲突”的问题。

## 已锚定事实

- 当前 repo 的 CLI 主入口和测试模式都以 `Typer` 为中心，而不是独立 `argparse` 脚本
- `.agent/artifacts/...` 已经是现有 workflow 文档采用的 Artifact 落盘约定
- `write_artifact`、`TaskTracker`、`StateHandler` 已经分别覆盖了 planning gate、任务跟踪、运行时状态处理的既有能力
- 原始文档里的“scaffold 模板”与“non-empty gate”存在内部张力，需要额外机制消解

## 方案假设

- 这个 Harness Orchestration MVP 被视为 repo-local workflow helper，而不是 AgentLoop 运行时的一部分
- Phase 1 可以接受“派生式阶段检查器”而不是显式权威状态机
- repo 根目录 `.agent/` 比 `workspace_path` 更适合作为默认 Artifact 根目录
- 通过 stub 哨兵 + 最小结构断言，可以把模板文件和阶段 ready 判定区分开

## 建议的模块切分

### 核心文件

- `[NEW] nanobot/agent/harness/job.py`
  - 负责 `job_id` 规范化、`state.json` 读写、元数据模型
  - `state.json` 只保存元数据与最近一次 inspection snapshot，不充当唯一真相源
  - 写盘优先复用 `nanobot.utils.helpers.safe_replace()`
- `[NEW] nanobot/agent/harness/root.py`
  - 负责解析默认 root
  - 建议优先寻找最近的含 `.agent/workflows/harness_lite.md` 的目录
  - 提供 `--root` 覆盖，避免 workspace/repo 语义不清
- `[NEW] nanobot/agent/harness/stages.py`
  - 用声明式结构维护 `lite` / `heavy` 的阶段定义、必需文件、终态
  - 只存数据，不存业务副作用
- `[NEW] nanobot/agent/harness/inspector.py`
  - 从文件系统派生 `current_stage`、`blockers`、`next_prompt_kind`
  - 不允许“手动跳阶段”；`advance` 只是重新检查并刷新 snapshot
- `[NEW] nanobot/agent/harness/scaffold.py`
  - 创建目录与模板文件
  - 模板中写入统一哨兵，例如 `<!-- HARNESS:STUB -->`
- `[NEW] nanobot/agent/harness/prompts.py`
  - 固定 launcher 模板，输出必须与 workflow 文档保持同一语义
- `[NEW] nanobot/agent/harness/cli.py`
  - 提供 `Typer` 子应用，而不是自起 `argparse` CLI
- `[MODIFY] nanobot/cli/commands.py`
  - 注册 `harness` 子命令，如 `nanobot harness start/status/advance`

### `state.json` 建议字段

建议保留 `state.json` 文件名，但弱化它的“权威状态机”含义：

```json
{
  "job_id": "lite_20260425_harness_orchestration_plan",
  "requested_label": "Harness Orchestration Plan",
  "mode": "lite",
  "goal": "...",
  "source": "...",
  "root_dir": "...",
  "artifact_dir": "...",
  "created_at": "...",
  "last_checked_at": "...",
  "derived_stage": "DRAFT_V1_READY",
  "blockers": [],
  "next_prompt_kind": "critic"
}
```

这里的 `derived_stage` 和 `blockers` 每次都由 `inspector.py` 重新计算，避免 `state.json` 与真实 Artifact 漂移。

## CLI 形态建议

建议最终对外命令长这样：

```text
nanobot harness start --mode lite --goal "Test" --source "docs/..."
nanobot harness status --job <job_id>
nanobot harness advance --job <job_id>
```

兼容性上，如果以后确实需要 `python -m nanobot.agent.harness.cli`，那也应该只是同一套 `Typer` app 的另一种入口，而不是独立维护第二套参数解析。

## 阶段推进建议

### `start`

- 规范化 `job_id`
- 解析 root
- 创建 `.agent/artifacts/harness_<mode>/<job_id>/`
- 写 `state.json`
- 写模板文件
- 打印第一条固定 launcher 或当前待完成说明

### `status`

- 重新检查 Artifact
- 输出当前派生阶段、缺失文件、仍为 stub 的文件、下一步 launcher
- 不推进任何状态

### `advance`

- 重新检查 Artifact
- 如果当前阶段所需文件仍缺失或仍为 stub，则报错并列出 blockers
- 如果当前阶段满足，则刷新 `state.json` snapshot，并打印下一阶段 launcher
- 不允许通过参数强行覆盖阶段

## 模板与 ready 判定建议

原文最大的不现实点，是“先脚手架模板文件”与“只要 non-empty 就算 ready”互相冲突。  
Draft V1 建议改成下面的最小机制：

1. 所有由 CLI 生成的模板文件都带 `<!-- HARNESS:STUB -->`
2. `inspector.py` 判定 ready 时，必须满足：
   - 文件存在
   - 去掉空白后仍有正文
   - 不再包含 `HARNESS:STUB`
3. 对少数关键文档，再加最小结构断言：
   - Lite `review_packet.md` 必须包含 `Acceptance Checklist`
   - Heavy `validation_packet.md` 必须包含 `Acceptance Matrix`
   - Evidence Gate 文件必须至少出现 `PASS / FAIL / BLOCKED`

这样既保留“用户一启动就有完整骨架”，也避免模板文件误触发阶段推进。

## 关键 trade-off

- `Typer` 集成 vs 独立 `argparse`
  - 取舍：集成到现有 CLI 更符合 repo 习惯，也更容易复用 `CliRunner`
  - 代价：命令注册耦合到 `nanobot/cli/commands.py`
- 派生式阶段检查器 vs 权威状态机
  - 取舍：更贴合 Artifact-first，不容易漂移
  - 代价：不能依赖内存中的“强制推进”能力
- repo-root `.agent` vs `workspace_path`
  - 取舍：repo-root 更符合当前 harness workflow 文档与人类操作模型
  - 代价：与 runtime 的 workspace 语义不完全统一，必须显式文档化
- 同时支持 `lite` + `heavy` vs 先做 `lite`
  - 取舍：如果用声明式 `stages.py`，两种模式可以共用大部分逻辑
  - 代价：测试矩阵会变大，MVP 节奏可能被拉长

## 风险与假设

- 假设这套 harness orchestration 是**repo-local workflow helper**，不是 AgentLoop 运行时的一部分
- 假设现有 workflow 文档在短期内相对稳定，否则 prompt 模板会发生漂移
- 风险：如果 root 解析策略不清晰，用户可能会把 Artifact 写到 `workspace` 而不是 repo `.agent/`
- 风险：结构化 ready 检查只能验证“像样地写了”，不能判断内容质量；质量仍要靠 Critic / Evidence Gate
- 风险：若 Phase 1 同时做 heavy，但没有足够测试，容易把一个小工具做成大表面积脆弱层

## 建议的验证计划

- `tests/test_harness_cli.py`
  - `CliRunner` 验证 `start/status/advance`
  - 验证 `Typer` 子命令接入方式
- `tests/test_harness_inspector.py`
  - 验证 stub 文件不会被误判为 ready
  - 验证缺失文件会给出 blocker
  - 验证 `review_packet.md` / `validation_packet.md` 的最小结构断言
- `tests/test_harness_root.py`
  - 验证默认 root 解析与 `--root` 覆盖
- `tests/test_harness_job.py`
  - 验证 `job_id` 规范化
  - 验证 `state.json` 原子写盘与 snapshot 刷新

## 仍待验证的点

- 是否要在 Phase 1 正式支持 `heavy`，还是先只把它的数据结构预留出来
- `state.json` 是否沿用原命名，还是直接重命名为 `job.json`
- Prompt 模板应否在代码中做 snapshot test，以降低与 workflow 文档的漂移风险
- 是否需要一个 `doctor` / `check` 命令，专门做“路径存在性 + 模板完整性 + root 解释”诊断
