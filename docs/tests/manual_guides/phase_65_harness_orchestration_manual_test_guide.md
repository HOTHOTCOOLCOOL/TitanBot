# Phase 65 Harness Orchestration Manual Test Guide

本手册用于人工验证 Harness Orchestration Phase 1 MVP 是否真的以 **repo-local、artifact-first、lite-only** 的方式落地，而不是退化成“多几个命令包装”的假自动化。

> 范围说明：本手册验证的是 `nanobot harness start/status/advance` 和对应 `nanobot/agent/harness/` 辅助层，不覆盖 heavy orchestration、session-aware routing 或 auto-dispatch。

## Automated Confirmation (2026-05-04)

本手册中的核心 contract 场景现在已经有确定性自动化覆盖：

- `tests/test_harness_cli.py`
  - 覆盖 A1-A6：lite scaffold、heavy 显式拒绝、repo root fail-closed、exact launcher、`evidence_gate.md` 结构校验、stale `state.json` 纠正
- `tests/test_auto_reviewer.py`
  - 覆盖 execute_phase Artifact 限域 review scope 与本地 L2 fallback 的基础行为
- `tests/test_phase65_execute_phase_contract.py`
  - 覆盖 `execute_phase` handoff/result/feedback 的 Artifact 契约完整性，避免 Phase 65 的上下游约束退化

推荐先跑以下自动化确认，再决定是否还需要人工复测：

- `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v`

2026-05-04 记录结果：

- `24 passed`

因此，这份 manual guide 现在主要保留给以下场景：

- 作为 A1-A6 的人工可读验收映射
- 排查真实多会话 / IDE / sandbox / provider 交互问题
- 处理无法在 hermetic pytest 中稳定复现的环境级异常

## 测试准备

1. 确保当前仓库包含 `.agent/workflows/harness_lite.md`，并在可写目录中执行命令。
2. 准备两个工作目录：
   - 一个仓库内的子目录
   - 一个仓库外的临时目录
3. 如需先跑自动化基线，可执行：
   - `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py -W ignore -v`

---

## 场景 1：`start --mode lite` 只创建 lite 本地脚手架

**目标**：验证 A1/A2 的最小 happy path。

**操作步骤**

1. 在仓库根目录或仓库内子目录执行：
   - `nanobot harness start --mode lite --goal "Implement Harness Orchestration" --source "docs/harness_orchestration_blueprint.md"`
2. 记录输出中的 `job_id`。
3. 打开 `.agent/artifacts/harness_lite/<job_id>/`。

**成功标准（期望结果）**

- 只创建 `.agent/artifacts/harness_lite/<job_id>/`，不会创建 `.agent/artifacts/harness_heavy/`。
- 目录下至少存在：
  - `problem_statement.md`
  - `baseline.md`
  - `draft_v1.md`
  - `review_packet.md`
  - `candidate.md`
  - `evidence_gate.md`
  - `state.json`
- 终端输出是固定的启动 launcher，且只替换了 `job_id/source/goal`。
- 新建的待后续填写文件仍带有 stub sentinel，而不是被误判为 ready。

---

## 场景 2：`--mode heavy` 必须显式拒绝

**目标**：验证 Phase 1 的 lite-only 边界没有被偷渡。

**操作步骤**

1. 执行：
   - `nanobot harness start --mode heavy --goal "Heavy flow" --source "docs/spec.md"`

**成功标准（期望结果）**

- 命令非零退出。
- 输出包含 `heavy deferred to later phase` 或等价的显式拒绝文案。
- 仓库内不会生成任何 `.agent/artifacts/harness_heavy/` 目录。

---

## 场景 3：repo root 解析必须 fail-closed

**目标**：验证 A5 的根目录边界。

**操作步骤**

1. 在仓库内子目录执行一次 `start --mode lite`。
2. 切到仓库外目录，不带 `--root` 再执行一次。
3. 仍在仓库外目录，补上 `--root <repo_root>` 再执行一次。

**成功标准（期望结果）**

- 仓库内子目录执行时，Artifact 仍写回真实 repo root。
- 仓库外且不带 `--root` 时，命令非零退出，并明确提示 `repo` 与 `--root`。
- 仓库外但显式提供 `--root` 时，可以成功写入指定仓库。
- 不允许静默回退到任意 `workspace_path` 或当前目录。

---

## 场景 4：`advance` 必须输出固定 launcher，而不是自由发挥

**目标**：验证 A4 的 exact-output 契约。

**操作步骤**

1. 选择一个已有 lite job，确保以下文件已经去掉 stub 且具备结构头：
   - `problem_statement.md`
     - `Job ID`
     - `Goal`
     - `Source Context`
     - `In Scope`
     - `Out of Scope`
     - `Expected Output`
   - `baseline.md`
     - `Claim / Evidence / Status`
     - `Source of Truth Files`
     - `Unknowns`
     - `Questions the Critic Must Attack`
   - `draft_v1.md`
     - `当前方案摘要`
     - `关键 trade-off`
     - `风险与假设`
     - `仍待验证的点`
2. 运行：
   - `nanobot harness advance --job <job_id> --root <repo_root>`
3. 之后把 `review_packet.md` 也填成 ready，至少包含：
   - `Findings`
   - `Must Keep`
   - `Weak Claims / Unverified Claims`
   - `Acceptance Checklist`
4. 再次运行同一条 `advance` 命令。

**成功标准（期望结果）**

- 第一次 `advance` 输出 Critic launcher，只引用：
  - `problem_statement.md`
  - `baseline.md`
  - `draft_v1.md`
- 第二次 `advance` 输出 Synthesis launcher，只要求先读 `review_packet.md`，然后产出 `candidate.md` 和 `evidence_gate.md`。
- 输出文案应与 `harness_lite` 工作流约定一致，而不是“语义接近即可”。

---

## 场景 5：`evidence_gate.md` 结构不全时必须 `BLOCKED`

**目标**：验证 A3，不允许“看起来像 PASS”就推进。

**操作步骤**

1. 让 `candidate.md` 达到 ready 状态，至少包含：
   - `Adopted Criticisms`
   - `Rejected Criticisms`
   - `Final Candidate`
   - `Residual Risks`
   - `Evidence Plan`
2. 故意把 `evidence_gate.md` 写成结构不全版本，例如只保留：
   - `PASS`
   - `Decision`
3. 运行：
   - `nanobot harness advance --job <job_id> --root <repo_root>`
4. 再把 `evidence_gate.md` 改成结构完整版本，确保出现：
   - `A#`
   - `Status`
   - `Evidence`
   - `Meaning`
   - 独立 decision line：`PASS` / `FAIL` / `BLOCKED`
5. 再次执行 `advance` 或 `status`。

**成功标准（期望结果）**

- 结构不全时命令非零退出，并以 `BLOCKED:` 开头说明缺失项。
- 结构补齐且 decision 为 `PASS` 后，流程进入 `DONE`，不会继续要求新的 launcher。

---

## 场景 6：`state.json` 被篡改后仍会按 Artifact 真相纠正

**目标**：验证 A6，确保 snapshot 不是第二真相源。

**操作步骤**

1. 选择一个已经完成到 `DRAFT_V1_READY` 或更后阶段的 lite job。
2. 手工编辑 `.agent/artifacts/harness_lite/<job_id>/state.json`，把：
   - `derived_stage` 改成错误值，例如 `INIT`
   - `blockers` 改成伪造值，例如 `["stale snapshot"]`
3. 运行：
   - `nanobot harness status --job <job_id> --root <repo_root>`
4. 重新打开 `state.json`。

**成功标准（期望结果）**

- 终端输出的 `Derived Stage` 取决于当前磁盘上的 Artifact 现状，而不是你手工写入的旧值。
- `state.json` 会被刷新为重新派生后的 `derived_stage` 和 `blockers`。
- 在 Windows 上连续多次执行 `status/advance` 时，不应出现 `replace`/占用类写盘异常。

---

## 可选场景：L2 审查在禁网环境下也应能落地

**目标**：确认 Stage 3 的默认 reviewer 命令不再因为外部 provider 不可用而永久阻塞。

**操作步骤**

1. 在仓库根目录执行：
   - `.\\.venv311\\Scripts\\python.exe .agent\\scripts\\auto_reviewer.py --context "核对 task.md 落地情况，防范架构腐化"`

**成功标准（期望结果）**

- 命令最终返回 `EXIT=0`。
- 若当前环境禁网或远端 provider 不可用，输出应清楚说明启用了本地 fallback runtime，而不是直接中断整条验收链。
- 审查范围应以 execute_phase Artifact 推导出的 write set 为准，而不是扫描整个仓库。

---

## Regression Targets

根据本次 `Blast Radius Analysis`，人工收尾时除了验证新功能本身，还要重点盯住以下旧功能边界没有被破坏：

1. **现有 CLI 主入口仍然稳定**：`tests/test_commands.py` 和 `tests/test_cli_input.py` 对应的 help、输入与基础命令行为不能因为新增 `harness` 子命令而回归。
2. **旧 runtime 主回路未被波及**：`loop.py`、`context.py`、`session/manager.py`、`middleware/`、`verification.py`、`tools/`、`channels/`、`cron/` 应继续保持未受本次 Phase 1 CLI helper 影响。
3. **repo 外运行仍然 fail-closed**：不允许因为“方便使用”而偷偷回退到 workspace 或当前目录。
4. **heavy 仍是显式 defer，而不是半成品支持**：任何出现 `.agent/artifacts/harness_heavy/` 或模糊成功文案都应视为回归。
5. **`state.json` 仍是快照不是状态机**：手工篡改后必须能被 `status/advance` 纠正。
6. **Windows 写盘路径仍然稳定**：多次刷新 `state.json` 时不应重新出现裸 `Path.replace()` 导致的占用/替换问题。
