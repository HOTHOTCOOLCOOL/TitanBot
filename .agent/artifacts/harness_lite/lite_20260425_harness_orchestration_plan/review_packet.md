# Review Packet

## Findings

### F1 (High) Artifact 落盘路径仍然写成 `harness_<mode>`，和现有 workflow 契约不兼容

`draft_v1.md` 在 `start` 里仍写“创建 `.agent/artifacts/harness_<mode>/<job_id>/`”。但当前仓库的固定工作流约定是 `.agent/artifacts/harness_lite/<job_id>/` 与 `.agent/artifacts/harness_heavy/<job_id>/`，固定 launcher 也绑定这两个具体目录。按 draft 实现，CLI 真实落盘位置和后续 launcher 会直接错位。

Refs: `draft_v1.md:100-107`; `.agent/workflows/harness_lite.md:73,232-238`; `.agent/workflows/harness_heavy.md:81,330-364`; `docs/Harness Orchestration Phase 1 Artifact-only MVP.md:21`.

### F2 (High) Phase 1 MVP 的范围仍未收敛，`heavy` 同时被纳入实现面又被保留为待决项

`problem_statement.md` 把“明确 Phase 1 MVP 的最小可交付边界”列为本阶段目标。但 `draft_v1.md` 一边把 `lite/heavy` 一起写进 `stages.py`、ready 断言和测试计划，一边又把“是否在 Phase 1 正式支持 heavy”留在“仍待验证”。这会让实现范围、测试矩阵和完成标准继续漂移。

Refs: `problem_statement.md:25-30`; `baseline.md:53-68`; `draft_v1.md:47-49,132-135,150-152,160,167-170,177-182`; `.agent/workflows/harness_heavy.md:81-96,154-163`.

### F3 (High) Evidence Gate 的 ready 判定仍弱于 `harness_lite` 契约

`draft_v1.md` 对 Evidence Gate 的结构断言仍然只是“至少出现 `PASS / FAIL / BLOCKED`”。但 `harness_lite` 的 BLOCKED 条件明确要求 Evidence Gate 至少包含 `A# / Status / Evidence / Meaning`。如果检查器只按 draft 的最小断言实现，就会把格式不合格的 `evidence_gate.md` 误判为可推进。

Refs: `draft_v1.md:132-135`; `.agent/workflows/harness_lite.md:204-208,262-263`.

### F4 (Medium) Launcher 仍被描述成“语义一致”，没有被锁成可验证协议

workflow 文档要求用户“原样发送”固定 launcher。`draft_v1.md` 目前只要求 prompt 与 workflow “保持同一语义”，并把 snapshot test 放到“仍待验证”。这里不够严格，因为 launcher 不是普通 UI 文案，而是跨会话协议的一部分。

Refs: `baseline.md:18,59`; `draft_v1.md:56-57,96,157,181`; `.agent/workflows/harness_lite.md:221-249`; `.agent/workflows/harness_heavy.md:319-400`.

### F5 (Medium) 默认 root 解析策略仍缺少失败语义和边界定义

`draft_v1.md` 继续把 repo 根目录 `.agent/` 作为默认 root，并建议向上查找 `.agent/workflows/harness_lite.md`。但 baseline 已经明确指出，现有 CLI、`write_artifact`、`TaskTracker` 的落盘语义偏向 workspace。draft 仍没定义 repo 外启动、安装态、repo/workspace 分离、或误命中上层目录时到底该硬失败、警告还是回退。

Refs: `baseline.md:14,55,64`; `draft_v1.md:18,32,43-46,147-149,158,171-172`; `nanobot/config/schema.py:491-493`; `nanobot/utils/helpers.py:25-39`; `nanobot/tools/write_artifact.py:25-28`; `nanobot/agent/task_tracker.py:164-168`.

## Must Keep

- 保留从独立 `argparse` CLI 改为接入现有 `Typer` 主入口的方向；这和仓库现有 CLI 入口、脚本注册和测试模式一致。 Refs: `baseline.md:7,17`; `draft_v1.md:16,23,58-61,141-143`; `nanobot/cli/commands.py:27,702-707,886-887,1096-1097`; `nanobot/__main__.py:1-8`; `pyproject.toml:76-77`; `tests/test_commands.py:6-10`.
- 保留“不要再造一个权威 `state_machine.py`”的纠偏方向；如果保留 `state.json`，它只能是元数据与派生快照，不应再长成第二真相源。 Refs: `baseline.md:9-10,57,68`; `draft_v1.md:17,40-41,65,84,144-146`; `docs/adr/ADR-59-antigravity-pattern-integration.md:31-32,112-129,236-237`; `docs/antigravity_architecture_reference.md:111-120,124`.
- 保留用 stub 哨兵拆开“脚手架文件存在”与“阶段 ready”的思路；这确实是在处理原始文档里 `scaffold` 与 `non-empty gate` 的内部冲突。 Refs: `baseline.md:12,58,66`; `draft_v1.md:19,53-55,124-137`; `docs/Harness Orchestration Phase 1 Artifact-only MVP.md:24-34,57-59`.
- 保留复用 `safe_replace()` 的建议；Windows 原子替换问题在仓库里已有现成处理。 Refs: `baseline.md:15`; `draft_v1.md:42,175`; `nanobot/utils/helpers.py:90-109`.
- 保留“repo-local、Artifact-first helper，而不是自动派工 runtime”的边界。 Refs: `problem_statement.md:32-37`; `draft_v1.md:5-11,30,156`; `docs/Harness Orchestration Phase 1 Artifact-only MVP.md:3,45-49`.

## Weak Claims / Unverified Claims

- “默认根目录应当是 repo 根目录 `.agent/`，而不是 `workspace_path`。”这是 open decision，不是已验证结论。 Refs: `baseline.md:14,55`; `draft_v1.md:18,32`.
- “向上搜索最近的 `.agent/workflows/harness_lite.md` 足以可靠地确定 root。”缺少 repo 外启动、安装态、monorepo、repo/workspace 分离场景的证据。 Refs: `draft_v1.md:43-46`.
- “Phase 1 可以顺手纳入 `heavy`，而不会显著扩大 MVP。”baseline 已把它列成风险与攻击面，draft 还没给收口证据。 Refs: `baseline.md:16,56,67`; `draft_v1.md:47-49,150-152,160,179`.
- “Prompt 模板可以长期与 workflow 文档保持同步。”目前只有意图，没有同步机制或唯一真相源。 Refs: `baseline.md:59`; `draft_v1.md:56-57,157,181`.
- “`state.json` 会始终停留在诊断性快照层。”这是设计愿望，尚未被行为约束和测试锁死。 Refs: `baseline.md:10,57,68`; `draft_v1.md:40-41,65,84,119`.

## Acceptance Checklist

| A# | Claim | Evidence Method | Expected Result | If Fail |
| --- | --- | --- | --- | --- |
| A1 | CLI 为每个支持模式创建的 Artifact 目录，与对应 workflow 的固定路径完全一致。 | 在临时 repo 运行 `start`；检查真实目录和输出 launcher。若 Phase 1 支持 `heavy`，同样验证 `heavy`。 | `lite` 使用 `.agent/artifacts/harness_lite/<job_id>/`；`heavy` 若支持，则使用 `.agent/artifacts/harness_heavy/<job_id>/`；若不支持，则命令显式拒绝。 | CLI 落盘路径和工作流错位，后续阶段按固定 launcher 会读错目录。 |
| A2 | Phase 1 的范围被定成单一结论，不再把 `heavy` 留成悬空决策。 | 检查 candidate/实现计划/帮助文案/测试列表。 | 只剩一种清晰结论：要么 Lite-only MVP，`heavy` 明确延后；要么 Lite+Heavy 一起交付且各自有完整阶段、模板和测试覆盖。 | 实现范围继续漂移，无法判断交付物是否完成。 |
| A3 | Evidence Gate 检查器严格执行 `harness_lite` 的结构契约，而不是只看 `PASS / FAIL / BLOCKED`。 | 构造一个只包含 `PASS / FAIL / BLOCKED`、但缺少 `A# / Status / Evidence / Meaning` 的 `evidence_gate.md`。 | 检查结果为 not ready / blocked。 | 工具会放过不合格的 Evidence Gate。 |
| A4 | Launcher 被当成协议产物验证，而不是“语义差不多”。 | 对每个支持阶段做 golden/snapshot test，或建立单一 canonical 模板源并验证输出。 | 输出与当前 workflow 契约在路径、读取顺序、关键限制上保持一致。 | 工具与 workflow 文档会逐步漂移。 |
| A5 | 默认 root 解析在 repo 根、子目录、repo 外、以及 repo/workspace 分离场景下都有可预测行为。 | 覆盖这些场景的测试，并核对帮助文案。 | 要么解析到预期 repo 根；要么硬失败并给出明确提示；不能静默落到错误位置。 | Artifact 会写到错误树，`state.json` 与真实 job 目录分叉。 |
| A6 | `state.json` 不是阶段真相源，阶段结果始终从当前 Artifact 现状重算。 | 人工把 `state.json` 中的 `derived_stage` 改成过期值，再运行 `status/advance`。 | 输出仍以当前文件系统状态为准，并刷新快照。 | 设计重新退化成“两套状态真相源”。 |
