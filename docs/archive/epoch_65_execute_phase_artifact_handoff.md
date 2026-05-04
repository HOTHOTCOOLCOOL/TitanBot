# Epoch 65: execute_phase Artifact-First Handoff Upgrade

**Date:** 2026-04-25
**Status:** Phase 65 slice complete; remaining runtime orchestration spun out to Phase 68

## 1. Background

`execute_phase.md` 之前已经完成了 Phase 63 的绿色基线、Zone A/B/C、pytest(L1)/Codex(L2) 双层门控强化，但仍保留一个明显的工程断点：

- AgentManager 负责规划和验收
- Codex 负责物理编码
- **用户负责在两者之间来回传话**

这个设计在小规模协作时勉强可用，但一旦要追求稳定的半自动闭环，就会暴露三个问题：

1. 需求与返工边界会在用户转述过程中漂移。
2. 审计链和回放链断裂，无法可靠复盘“当时到底交给 Codex 的是什么”。
3. 后续即使补自动派工代码，也缺少统一的 Artifact 契约可以挂接。

## 2. This Session's Workflow Upgrade

本次会话没有直接实现自动派工代码，而是先把 `execute_phase.md` 升级为 **Artifact-First** 协同协议，为后续代码化编排打底。

### 2.1 New Collaboration Contract

工作流新增了三类固定制品：

- `codex_handoff.md`
  - AgentManager 写给 Codex 的唯一执行契约
  - 包含 Goal、Allowed/Forbidden Write Set、Red Tests、Green Exit Criteria、Stop Conditions
- `codex_result.md`
  - Codex 回写给 AgentManager 的结构化回执
  - 包含 Status、Changed Files、Executed Tests、Open Risks、Need Manager Review
- `codex_feedback.md`
  - AgentManager 验收失败后写给 Codex 的结构化返工单
  - 固定记录失败命令、关键报错、A/B 级审查意见、必须修复文件与边界

### 2.2 Policy Shift

工作流策略从“人工传话优先”切换为：

1. **自动派工优先**
2. **人工转交 Artifact 兜底**
3. **禁止用户自由转述**

也就是说，用户仍然可以参与，但只能转交原始制品，不再承担口头中继职责。

### 2.3 Verification Gate Upgrade

验收阶段的入口也做了收紧：

- 先读 `codex_result.md`
- 再跑 pytest / auto reviewer
- 失败则产出 `codex_feedback.md`
- 若环境具备能力，则自动回派；否则要求用户转交返工单

这使得“返工”首次成为可追踪、可复盘、可自动化的固定节点，而不是聊天里的临时发挥。

## 3. What This Change Does Not Claim

本次升级**不等于**系统已经具备完整的无人值守闭环。当前仍然缺失以下代码层能力：

1. 读取 `codex_handoff.md` 后自动调度 Codex 执行
2. 自动监听 `codex_result.md` 或等价完成信号
3. 将 Planning Gate / HITL 批准和后续步骤的 tool-scope / plan-scope 凭证联动起来

因此，本次落盘的正确表述是：

- **工作流协议已升级**
- **自动编排接口仍待实现**

## 4. Files Affected

- `.agent/workflows/execute_phase.md`
- `docs/rules/ARCHITECTURE.md`
- `progress_report.md`
- `docs/tests/manual_guides/phase_65_manual_test_guide.md`
- `docs/archive/epoch_65_execute_phase_artifact_handoff.md`

## 5. Recommended Next Engineering Steps

下一步若要把这套协议真正跑起来，优先级建议如下：

1. 新增 Codex 派工器：读取 `codex_handoff.md` 并以固定上下文启动 Codex provider / bridge
2. 新增回执检测器：监听 `codex_result.md`、完成信号或 worker event，自动推进到验收阶段
3. 新增 plan-scoped approval token：在 Planning Gate 获批后，将后续允许动作批量注册为 session 内短期凭证
4. 为上述三点各自补 adversarial / integration tests，避免流程“看起来自动，实际上仍靠人”

## 6. Follow-up Hardening After First Live Run

真实跑了一轮后，暴露出一个重要缺口：**即使 AgentManager 已经写出了 `implementation_plan.md`、`task.md` 和 handoff prompt，Codex 仍可能因为不知道这些制品的精确路径，或者没有被强制要求先读取它们，而退化成“按自己理解重新分析”**。这会直接带来 Token 浪费、任务边界漂移和重复生成文件。

因此后续对 `execute_phase.md` 的强化方向应当明确为：

1. `codex_handoff.md` 必须内置 `Artifact Registry`，显式列出 `implementation_plan.md`、`task.md`、红测文件、参考文档的精确路径
2. Codex 必须遵守 `Codex Startup Checklist`：先读制品，再编码；缺件即 `blocked`
3. `codex_result.md` 不能只写“改了哪些文件”，还必须写 `Artifacts Read`、`Task Coverage`、`Deviation from Plan`、`Suggested Validation Steps`、`Suggested Review Focus`
4. 人工唤醒 Codex 时，启动语应尽量薄，只负责指向 `codex_handoff.md`，而不是把规划正文再复述一遍

这意味着工作流已经从“Artifact-First”进一步收敛为：

- **Prompt 只负责定位 Artifact**
- **Artifact 才是唯一真实契约**
- **缺件时阻塞，禁止 Codex 自行重规划**

## 7. Follow-up Automation Confirmation (2026-05-04)

在工作流协议落盘之后，我们又补上了针对 Phase 65 契约本身的确定性回归：

- 新增 `tests/test_phase65_execute_phase_contract.py`
  - 校验 `.agent/workflows/execute_phase.md` 仍然要求 Artifact-first launcher 与结构化返工
  - 校验代表性 Phase 65 job 的 `codex_handoff.md`、`codex_result.md`、`codex_feedback.md` 没有退化回“聊天口头协议”
- 联动既有 `tests/test_harness_cli.py` 与 `tests/test_auto_reviewer.py`
  - 验证 Harness Phase 1 边界、Artifact 限域 review scope 与本地 L2 fallback 仍然成立

定向组合回归命令：

- `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v`

2026-05-04 记录结果：

- `24 passed`

这不等于完整的无人值守 auto-dispatch 已经存在；它的含义是：Phase 65 的工作流契约已经不再只靠文档叙述，而是已经被回归测试锁定。

## 8. Phase Closure & Successor Split (2026-05-04)

截至 2026-05-04，我们将 Phase 65 正式收束为“契约与回归自动化”这一已完成切片：

- `execute_phase` 的 Artifact-first handoff / result / feedback 协议已落盘
- Harness Phase 1 lite-only orchestration 已落盘
- Phase 65 两份 manual guide 的核心 contract 场景已有 `24 passed` 的定向自动化证据

但以下工作不再继续挂在 Phase 65 名下，而是拆分为新的 **Phase 68**：

- Codex 自动派工器
- `codex_result.md` 完成信号检测器
- plan-scoped approval token
- 真实多会话 / HITL / provider / sandbox 环境下的 runtime orchestration 验收

这样做的目的，是避免把“已完成的 contract hardening”与“尚未完成的 runtime automation”混在同一个 phase 里，导致 Phase bookkeeping 与验收口径持续模糊。
