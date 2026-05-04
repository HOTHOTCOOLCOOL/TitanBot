# Epoch 65: Harness Orchestration Phase 1 MVP

**Date:** 2026-04-26  
**Status:** shipped and accepted

## 1. Background

`docs/harness_orchestration_blueprint.md` 将 Harness Orchestration 的第一步定义为 **Artifact-only Orchestration**：先把 Lite 流程的 job 创建、Artifact 脚手架、阶段派生和固定 launcher 做成 repo-local CLI 辅助层，再谈 session-aware routing 和 auto-dispatch。

本次 execute_phase job 以上游已通过的 lite-only candidate 为唯一契约，目标是把这层 MVP 真正落地，并用 A1-A6 验收项把边界钉死。

## 2. What Shipped

本次交付新增了一个窄表面积的 CLI + 文件系统协作层：

- `nanobot/cli/commands.py`
  - 接入 `nanobot harness start/status/advance`
  - 对动态加载失败保持 fail-closed，不向终端用户泄露原始 traceback
- `nanobot/agent/harness/`
  - `root.py`: fail-closed 的 repo root 解析，只认 `.agent/workflows/harness_lite.md`
  - `scaffold.py`: lite-only Artifact 脚手架与 stub sentinel 落盘
  - `stages.py`: 基于磁盘上真实 Artifact 内容派生阶段与 blockers
  - `prompts.py`: 固定 launcher 文案，保证 exact-output 契约
  - `job.py`: `state.json` 诊断快照读写，Windows 写盘复用仓库现成的 `safe_replace()`

设计边界保持为：

- 只支持 `lite`
- `heavy` 明确拒绝并提示 deferred
- `state.json` 只是诊断快照，不是真相源
- 真正的阶段推进始终由当前 Artifact 文件内容决定

## 3. Acceptance Mapping (A1-A6)

- **A1**: `start --mode lite` 只在 `.agent/artifacts/harness_lite/<job_id>/` 下落盘所需文件；`heavy` 不会半实现。
- **A2**: CLI 帮助、实现和测试叙事都明确保持 lite-only。
- **A3**: `evidence_gate.md` 结构不完整时，`advance` 必须 `BLOCKED`，不能假装 ready。
- **A4**: `start/advance` 打印的是固定 launcher，而不是语义相近的自由文本。
- **A5**: repo 根目录解析覆盖 repo 根、子目录、repo 外和 repo/workspace 分离四类场景，并保持 fail-closed。
- **A6**: `status/advance` 会根据磁盘上的 Artifact 重新派生阶段，并纠正陈旧或被篡改的 `state.json`。

## 4. Validation

实现验收时，L1 回归命令通过：

- `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py -W ignore -v` -> `16 passed`

为使 Stage 3 在禁网 / provider 不可用环境下仍可回放，本次还补强了 reviewer 基建：

- `.agent/scripts/auto_reviewer.py` 现在会优先从 execute_phase Artifact 推导 review scope
- 远端 provider 全部失败或 `allow_network=false` 时，会降级到 `local_static_fallback`
- `tests/test_auto_reviewer.py` 新增 3 个回归测试，覆盖 scope 推导、本地 fallback pass、merge marker fail
- 组合回归：
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py -W ignore -v` -> `19 passed`
- Stage 3 的默认 L2 命令现在可在当前 sandbox 内直接 `EXIT=0`：
  - `.\\.venv311\\Scripts\\python.exe .agent\\scripts\\auto_reviewer.py --context "核对 task.md 落地情况，防范架构腐化"`

2026-05-04 follow-up 自动化确认：

- 新增 `tests/test_phase65_execute_phase_contract.py`，把 Phase 65 依赖的 `execute_phase` Artifact-first handoff/result/feedback 契约也锁进回归
- 最新定向组合回归：
  - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v` -> `24 passed`

这意味着 Phase 65 不再只是“有 manual guide 可照着看”，而是 Harness CLI 核心边界与其上游 `execute_phase` 契约都已有确定性自动化证据。

## 5. Boundaries Kept

根据原 Blast Radius Analysis，本次实现保持没有进入以下高风险区域：

- `nanobot/agent/loop.py`
- `nanobot/agent/context.py`
- `nanobot/session/manager.py`
- `nanobot/agent/middleware/`
- `nanobot/agent/verification.py`
- `nanobot/agent/tools/`
- `nanobot/channels/`
- `nanobot/cron/`

这意味着本次交付是一个 repo-local orchestration helper，而不是新的 runtime agent、planning state machine 或安全边界改写。

## 6. Remaining Non-Goals

本次 MVP 仍然刻意没有做以下能力：

- heavy orchestration
- session-aware routing
- auto-dispatch / wait / auto-promotion
- 任何绕过 Harness / execute_phase 既有 Artifact-first 契约的“捷径”

后续若继续推进，应回到 blueprint 的 Phase 2 / Phase 3 路线，在现有 lite-only 基座上扩展，而不是把 Phase 1 CLI helper 继续膨胀成不透明的状态机。
