# Implementation Plan

Job ID: `phase_20260425_harness_orchestration_phase1_mvp`

## Goal

按已通过的 lite-only Phase 1 MVP 计划实现 Harness Orchestration，并满足 A1-A6 验收条件。

## Source Context

- 已通过方案: `.agent/artifacts/harness_lite/lite_20260425_harness_orchestration_plan/candidate.md`
- 验收依据: `.agent/artifacts/harness_lite/lite_20260425_harness_orchestration_plan/evidence_gate.md`
- 上游工作流契约: `.agent/workflows/harness_lite.md`
- 设计蓝图: `docs/harness_orchestration_blueprint.md`
- 历史草案（仅作对照，已被上游 candidate 收敛/修正）: `docs/Harness Orchestration Phase 1 Artifact-only MVP.md`
- 现有 CLI 入口: `nanobot/cli/commands.py`
- CLI 测试基线: `tests/test_commands.py`, `tests/test_cli_input.py`
- 开工前绿色基线:
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py -W ignore -v` -> pass (7 passed)

## Blast Radius Analysis

本次改动是一个 repo-local、Artifact-first、lite-only 的辅助层，不是新的 runtime agent，也不是新的 planning state machine。

受影响面预期收敛为三类：

1. CLI 入口
   - `nanobot/cli/commands.py`
   - 新增 `nanobot harness start/status/advance` 子命令，并保持接入现有 `Typer` 主入口。
2. 新增的 Harness 辅助包
   - `nanobot/agent/harness/`
   - 负责 repo root 解析、Artifact 脚手架、launcher 模板、ready 检查、`state.json` 快照刷新。
3. 新增回归测试
   - 以 `CliRunner` 为主，覆盖 A1-A6。

明确不应波及的区域：

- `nanobot/agent/loop.py`
- `nanobot/agent/context.py`
- `nanobot/session/manager.py`
- `nanobot/agent/middleware/`
- `nanobot/agent/verification.py`
- `nanobot/agent/tools/`
- `nanobot/channels/`
- `nanobot/cron/`

这意味着本次实现应保持为一个窄表面积的 CLI + 文件系统协作层，不进入运行时主回路，不改写既有安全/HITL 边界。

## Zone Declaration

**ZONE C**

原因：

- 本次改动不进入 `loop.py` / `context.py` / `session/manager.py` / `middleware/` / `verification.py`
- 也不进入 `tools/` / `channels/` / `cron/`
- 主要是新 helper 包、CLI 接线和精确的单元/集成测试

对应靶向命令：

- 基线:
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py -W ignore -v`
- 实施后回归:
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py -W ignore -v`

## Implementation Strategy

1. 建立 fail-closed 的 repo root 解析
   - 保留 `--root` 显式入口。
   - 未显式传入时，从 `cwd` 向上搜索 repo marker `.agent/workflows/harness_lite.md`。
   - 找不到 marker 时硬失败，并提示“请在仓库内运行或显式传入 `--root`”。
   - 不允许静默回退到 `Config.workspace_path`。

2. 只实现 lite-only 的 Artifact 脚手架
   - `start --mode lite` 创建 `.agent/artifacts/harness_lite/<job_id>/`。
   - 创建 `problem_statement.md` / `baseline.md` / `draft_v1.md` / `review_packet.md` / `candidate.md` / `evidence_gate.md` / `state.json`。
   - Markdown 模板统一带 stub 哨兵，例如 `<!-- HARNESS:STUB -->`，防止“文件存在即误判 ready”。
   - `start --mode heavy` 必须显式失败，并提示 `heavy deferred to later phase`。

3. 把 `state.json` 限定为“诊断快照”，不是第二真相源
   - 每次 `status/advance` 都先扫描当前 Artifact 文件系统。
   - 基于当前文件内容重算 `derived_stage` 与 `blockers`。
   - 然后再覆盖写回 `state.json`。
   - 人工篡改 `state.json` 不得影响真实阶段判断。

4. 将 ready 规则收紧到 workflow 契约强度
   - 通用 ready:
     - 文件存在
     - 去除空白后仍有正文
     - 不再包含 stub 哨兵
   - 关键文件附加规则:
     - `review_packet.md` 必须包含 `Acceptance Checklist`
     - `candidate.md` 必须包含 `Adopted Criticisms` / `Rejected Criticisms` / `Final Candidate`
     - `evidence_gate.md` 必须包含 `A#` / `Status` / `Evidence` / `Meaning`
     - `evidence_gate.md` 必须给出总结果 `PASS` / `FAIL` / `BLOCKED`

5. 把 launcher 视为 exact-output protocol
   - `prompts.py` 维护逐字模板。
   - `start` 输出 `harness_lite.md` 中的固定启动语（只替换具体 `job_id/source/goal`）。
   - `advance` 在对应阶段输出送往 Critic 或回到 Lead 的固定启动语。
   - 测试对路径、读取顺序、限制语句做 exact match，而不是“语义接近”。

6. 让 `status/advance` 体现“文件派生阶段”而不是“命令式推进”
   - `status` 输出当前 `derived_stage`、blockers 和当前可执行的下一步。
   - `advance` 只在当前 Artifact 已满足进入下一 handoff 边界时打印下一条固定 launcher。
   - 如果 Artifact 尚未满足条件，则明确 blocked/not ready，而不是盲目推进 snapshot。

7. 用 A1-A6 直接驱动测试设计
   - A1: lite 目录落盘 + heavy 显式拒绝 + launcher 路径一致
   - A2: help/实现/测试叙事都明确 lite-only
   - A3: `evidence_gate.md` 结构不全时 not ready / blocked
   - A4: start/advance launcher exact-output
   - A5: repo root / 子目录 / repo 外 / repo-workspace 分离四类 root 行为
   - A6: stale `state.json` 被 `status/advance` 纠正

## Contract / Data Structures / Function Signatures

建议收敛为以下最小实现面：

- `nanobot/agent/harness/root.py`
  - `def resolve_repo_root(explicit_root: str | None, cwd: Path | None = None) -> Path`
  - 只认 repo marker，不认 workspace fallback。

- `nanobot/agent/harness/job.py`
  - `def generate_job_id(goal: str, mode: str = "lite") -> str`
  - `def load_state(path: Path) -> dict`
  - `def write_state(path: Path, payload: dict) -> None`
  - `safe_replace()` 用于原子写回 `state.json`。

- `nanobot/agent/harness/scaffold.py`
  - `def scaffold_lite_job(repo_root: Path, job_id: str, source: str, goal: str) -> Path`
  - 创建 Artifact 目录、模板文件与初始 `state.json`。

- `nanobot/agent/harness/stages.py`
  - `def derive_lite_state(artifact_dir: Path) -> dict`
  - 产出:
    - `derived_stage`
    - `blockers`
    - `next_launcher_key`
    - `artifacts_status`

- `nanobot/agent/harness/prompts.py`
  - `def build_start_launcher(job_id: str, source: str, goal: str) -> str`
  - `def build_critic_launcher(job_id: str) -> str`
  - `def build_synthesis_launcher(job_id: str) -> str`

- `nanobot/cli/commands.py`
  - `harness_app = typer.Typer(...)`
  - `start`, `status`, `advance` 三个子命令挂接到顶层 `app`

`state.json` 建议字段：

- `job_id`
- `mode`
- `goal`
- `source`
- `artifact_dir`
- `created_at`
- `last_checked_at`
- `derived_stage`
- `blockers`

注意：

- `derived_stage` 与 `blockers` 是快照字段，不是权威状态。
- 权威真相始终是当前 Artifact 文件现状。

## Risk Notes

- 最大风险不是“代码写错”，而是契约漂移。
  - launcher 一旦与 workflow 文本不一致，整个 orchestration 会失去价值。
- 第二个风险是把 `state.json` 做成权威状态机。
  - 一旦允许 snapshot 先于文件真相，A6 就会失败。
- 第三个风险是 MVP 范围回潮。
  - `heavy` 必须保持显式拒绝，不能偷偷留半支持路径。
- 第四个风险是根目录误判。
  - 任何 repo 外静默落盘都会直接制造错误树与错误 launcher。

## Validation Plan

1. 保持开工前绿色基线已锁定：
   - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py -W ignore -v`

2. 第 2 阶段先补红测，再交给 Codex 实施：
   - 新增 `tests/test_harness_cli.py`
   - 先让 A1-A6 至少一部分处于失败状态
   - 再允许进入正式编码

3. 最终回归命令：
   - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py -W ignore -v`

4. 人工复核重点：
   - `nanobot harness start --mode heavy ...` 是否明确拒绝
   - launcher 是否与 `.agent/workflows/harness_lite.md` 固定文案一致
   - repo 外/分离场景是否 fail-closed
   - 手工改坏 `state.json` 后 `status/advance` 是否仍以文件真相为准
