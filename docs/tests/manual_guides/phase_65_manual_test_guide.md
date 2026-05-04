# Phase 65 Manual Test Guide

本手册用于人工验证 `execute_phase` 工作流从“用户转述驱动”升级为“Artifact-First 协同驱动”后，是否真正遵守新的移交、回执与返工契约。

> 注意：本手册验证的是**工作流约束和制品产出**。它不等于系统已经具备完整的自动派工代码。

## Automated Confirmation (2026-05-04)

本手册中的核心 Artifact-first 契约现在已经有自动化回归证据，不再只能依赖人工口头复核：

- `tests/test_phase65_execute_phase_contract.py`
  - 校验 `execute_phase.md` 仍然要求 `codex_handoff.md` / `codex_result.md` / `codex_feedback.md`
  - 校验代表性 Phase 65 job 的 `codex_handoff.md` 结构完整
  - 校验 `codex_result.md` 对 `task.md` 做逐条覆盖
  - 校验 `codex_feedback.md` 仍然是结构化返工单，而不是自由文本中继
- `tests/test_harness_cli.py`
  - 校验 Harness Phase 1 的 A1-A6 不回退，保证上游 orchestration helper 仍符合预期
- `tests/test_auto_reviewer.py`
  - 校验 Stage 3 审查在 Artifact 限域与本地 fallback 方向上仍保持 Phase 65 follow-up 的基本契约

推荐预检命令：

- `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v`

2026-05-04 记录结果：

- `24 passed`

因此，这份 manual guide 现在主要保留给以下剩余人工价值：

- 真实 AgentManager / Codex 多会话交接体验
- HITL / 审批拦截 / provider 故障下的操作层现象
- 任何需要真实 IDE、真实路径可见性、真实人工接力的环境级验收

## 测试准备

1. 确保工作区已包含最新的 `.agent/workflows/execute_phase.md`。
2. 准备一个适合多阶段落地的任务，例如“为某个工具补红测、修复实现并完成回归验收”。
3. 确保可以在当前环境中运行对应的 `pytest` 靶向命令；若不能运行，也要验证 workflow 是否明确暴露这一限制。

---

## 阶段一：规划制品完整性

**目标**：验证 AgentManager 在第一阶段不再只写 `implementation_plan.md` / `task.md`，而是强制生成带有路径登记与启动清单的 `codex_handoff.md` 作为跨模型执行契约。

**操作步骤**：

1. 触发 `execute_phase` 工作流，对一个真实开发任务执行第一阶段。
2. 检查工作区是否生成以下文件：
   - `implementation_plan.md`
   - `task.md`
   - `codex_handoff.md`
3. 打开 `codex_handoff.md`，确认至少包含以下字段或等价章节：
   - Artifact Registry
   - Codex Startup Checklist
   - Goal
   - Allowed Write Set
   - Forbidden Write Set
   - Red Tests to Satisfy
   - Green Exit Criteria
   - Stop Conditions
   - Return Contract
4. 检查第一阶段输出是否已经由 AgentManager 运行绿色基线；若未运行，是否明确说明被 HITL / 环境限制拦截，并给出原样命令供用户审批或兜底执行。

**成功标准 (期望结果)**：

- AgentManager 不会把对 Codex 的要求散落在聊天文本里，而是写入 `codex_handoff.md`。
- `codex_handoff.md` 不只写裸文件名，而是明确登记 `implementation_plan.md` / `task.md` / 红测文件的精确路径。
- `Codex Startup Checklist` 明确要求“先读制品，再编码；缺件即 blocked”，防止 Codex 自行脑补需求。
- 绿色基线默认由 AgentManager 执行，而不是下放给用户。
- 若绿色基线被环境拦截，输出会明确暴露阻塞原因，并把待执行命令原样交给用户审批或兜底执行。
- 第一阶段结束提示语明确把 `codex_handoff.md` 列为必审查制品之一。

---

## 阶段二：红测锁定与结构化移交

**目标**：验证第二阶段完成后，系统默认要求“转交 Artifact”，而不是让用户自由复述需求。

**操作步骤**：

1. 在第一阶段完成后，回复 `开始测试驱动开发`。
2. 检查 AgentManager 是否：
   - 修改了 `tests/` 中对应红测文件
   - 运行了红测命令并确认失败
   - 将失败摘要补写进 `codex_handoff.md`
   - 若默认路径不适用，已补全 `Artifact Registry` 中的实际路径
3. 检查输出文本是否要求：
   - 优先读取 `codex_handoff.md` 发起自动派工
   - 若当前环境无自动派工能力，则让用户**原样交给 Codex 该文件**
   - 启动语是“先读 handoff 与 Registry 所列制品”，而不是长篇复述规划
4. 检查是否准备了 `codex_result.md` 的固定回执模板。
5. 检查 `codex_result.md` 模板是否包含以下附加字段：
   - `Artifacts Read`
   - `Task Coverage`
   - `Deviation from Plan`
   - `Suggested Validation Steps`
   - `Suggested Review Focus`

**成功标准 (期望结果)**：

- 输出中不出现“请你把下面这段话转告 Codex”这类自由文本中继话术。
- 第二阶段的交接对象是 `codex_handoff.md`，而不是一段聊天消息。
- 若手工唤醒 Codex，交付给 Codex 的应该是极简启动指令 + `codex_handoff.md` 路径，而不是重新复制一遍 implementation plan。
- 工作流明确声明第三阶段的触发条件包括 `codex_result.md` 或自动派工完成信号，而不是“用户说 Codex 做完了”。

---

## 阶段三：结构化验收与返工闭环

**目标**：验证第三阶段先读回执，再验收；失败时必须生成 `codex_feedback.md`，而不是临场口述返工意见。

**操作步骤**：

1. 让 Codex 执行第二阶段任务，或手工准备一份 `codex_result.md` 作为模拟回执。
2. 触发第三阶段（例如回复 `开始验收`）。
3. 观察 AgentManager 是否首先读取 `codex_result.md`，并先核对：
   - `Artifacts Read` 是否覆盖 `Artifact Registry` 中的关键制品
   - `Task Coverage` 是否逐项回应 `task.md`
   - `Deviation from Plan` 是否解释越界实现
4. 之后再运行 pytest 与自动审查。
5. 若故意制造失败：
   - 检查是否生成或覆盖 `codex_feedback.md`
   - 检查其中是否写明失败命令、关键报错、A/B 级审查意见、必须修复文件、禁止偏离边界
6. 检查失败后的提示是否要求：
   - 有自动派工能力时，使用 `codex_feedback.md` 自动回派
   - 无自动派工能力时，让用户**原样转交 `codex_feedback.md`**

**成功标准 (期望结果)**：

- 验收前先读 `codex_result.md`，而不是跳过回执直接拍脑袋判断。
- AgentManager 会拿 `codex_result.md` 中的 `Artifacts Read` / `Task Coverage` / `Deviation from Plan` 去核对 Codex 是否真的按计划施工，而不是只看一句“已完成”。
- 返工单以 `codex_feedback.md` 的形式存在，可追踪、可复盘。
- 输出中不允许出现“你就跟 Codex 说一下这些问题”之类的自由转述指令。

---

## Regression Targets

在验证 Phase 65 时，除了新行为本身，还要重点回归以下旧约束没有被破坏：

1. **绿色基线铁律仍然保留**：第一阶段完成前必须确认 Zone 对应的 pytest 基线；默认由 AgentManager 执行，若受环境限制则明确暴露并让用户兜底，不能因为引入 Artifact 流程而跳过基线确认。
2. **角色分离仍然保留**：第二阶段之后 AgentManager 仍只负责测试、规划、验收，不能借“自动化升级”名义擅自编写业务实现。
3. **HITL 现实约束仍然保留**：若当前环境存在审批拦截，workflow 必须诚实暴露“尚未自动放行”，不能谎称全自动。
4. **返工上限意识仍然保留**：连续两轮 A/B 级问题后，必须建议回退到 Harness 或整体重构，不能无上限打补丁。

---

> ⚠️ 如果在以上任一阶段中，workflow 重新退化成“用户口头转述需求/返工意见”的模式，或虽然提到了 Artifact 但没有落盘具体文件，则说明本次 Phase 65 升级未真正生效。
