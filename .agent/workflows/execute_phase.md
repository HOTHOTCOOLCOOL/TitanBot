---
description: 自动执行、结构化移交与验收工作流 (Phase Execution Workflow)
---

这是一个规范化代码落地工作流，用于承接 Harness 辩证后形成的技术方案（如 `test_plan_XX.md`）。
它的目标不是“让两个模型都更自由”，而是**让计划不丢、边界不漂、验证可回放**。

**默认假设**：当前 Antigravity / IDE 环境**不具备稳定自动派工**，因此本工作流默认按下面的方式运行：

1. AgentManager 负责规划、测试、验收与返工判定。
2. Codex 负责物理编码与结果回执。
3. 用户只负责按固定话术切换阶段、转交原始 Artifact，并在 AgentManager 因 HITL / 环境限制无法直接执行命令时提供审批或兜底执行。

若未来具备自动派工能力，也只是在第二阶段和第三阶段把同一份 Artifact 自动投递给 Codex；**契约本身不变**。

### 0. 用户速查卡（忙的时候只看这里）

如果你很忙，不想记整套流程，直接照下面复制：

1. 启动 AgentManager：

```text
请按 execute_phase 工作流启动任务。
job_id: <可留空，让 AgentManager 生成>
source: <Phase 文档 / issue / PRD / 需求路径>
goal: <一句话目标>
```

2. 第一阶段完成后，回到 AgentManager：

```text
开始测试驱动开发，job_id=<job_id>
```

3. 需要把任务交给 Codex 时，打开 Codex 并原样发送：

```text
请严格执行 execute_phase 工作流。
先读取 `.agent/artifacts/execute_phase/<job_id>/codex_handoff.md`。
再按其中 Artifact Registry 读取全部关键制品。
缺件即 blocked，不要自行重规划，不要自行重写 implementation_plan/task。
```

4. Codex 完成后，回到 AgentManager：

```text
开始验收，job_id=<job_id>
```

5. 验收失败需要返工时，打开 Codex 并原样发送：

```text
请读取 `.agent/artifacts/execute_phase/<job_id>/codex_feedback.md`。
只修复其中列出的问题。
继续遵守原 handoff 中的 Artifact Registry、Allowed Write Set、Forbidden Write Set。
缺件即 blocked，不要自行重规划。
```

6. 验收通过后，回到 AgentManager：

```text
开始收尾，job_id=<job_id>
```

**补充规则**：

- 不要自己概括计划内容给 Codex。
- 不要把 Codex 的自由文本总结再口头转述给 AgentManager。
- 一律转交原始 Artifact，或者回复上面的固定话术。

---

### 1. 默认目录与命名约定

所有本工作流的核心制品，默认落盘到同一个固定目录：

`.agent/artifacts/execute_phase/<job_id>/`

`job_id` 规则：

1. 优先使用稳定、无空格、ASCII 的名字。
2. 推荐格式：`phase_<编号>_<短描述>` 或 `job_<YYYYMMDD>_<短描述>`。
3. 如果用户没有给出 `job_id`，AgentManager 必须自行生成，并在阶段结束提示语中明确告诉用户。

该目录下至少必须有以下文件：

1. `implementation_plan.md`
2. `task.md`
3. `codex_handoff.md`
4. `codex_result.md`
5. `codex_feedback.md`

说明：

1. 红测文件、源码文件、测试文件仍然落在它们原本的目录中。
2. 这些外部文件必须在 `codex_handoff.md` 的 `Artifact Registry` 中记录精确路径。
3. 如果当前 IDE / Provider 强制使用了不同路径，AgentManager 必须在 `Artifact Registry` 和阶段结束提示语中同时写清楚实际路径。

---

### 2. 核心训诫 (Core Directives)

- **角色分离 (Role Separation)**：AgentManager **绝对不可**擅自编写大段业务代码。你只负责规划、编写测试、生成任务清单，以及最终的审查验收。具体业务代码必须交由 Codex / IDE 扩展等执行。
- **Artifact-First (制品优先)**：所有跨阶段移交都必须落盘为文件，禁止只依赖自然语言口头约定。
- **薄启动语，厚制品 (Thin Launcher, Fat Artifact)**：真正的需求、计划、边界、回执要求必须写进 Artifact。聊天提示只承担“定位文件并要求先读”的职责，禁止在聊天里重复整份规划正文。
- **路径显式化 (Path-Explicit Handoff)**：跨模型制品必须记录精确仓库相对路径；禁止只写 `implementation_plan.md`、`task.md` 这类裸文件名。
- **缺件即阻塞 (No Artifact, No Coding)**：Codex 在未成功读取 `codex_handoff.md`、`implementation_plan.md`、`task.md` 前，不得自行脑补开工。任一关键制品缺失、路径不明、内容冲突，必须立刻 `blocked`。
- **用户不是消息总线**：禁止让用户充当“帮我把这段话转告另一个模型”的中继者。若必须人工参与，也只能让用户转交固定 Artifact 或固定启动语。
- **结构化返工**：任何打回 Codex 的原因都必须写入 `codex_feedback.md`，禁止口头返工。
- **防御性开发**：必须将旧系统视作易碎品。
- **行为契约显式化 (Behavior Contract over Implied State)**：对工具、RPA、安全分级、审批链路、通道集成等运行时敏感任务，`implementation_plan.md` 必须显式写出 `Behavior Contract Matrix`。至少列出：`场景输入`、`预期行为/分级`、`隐藏运行时状态`、`自动验证方式`、`人工验收信号`。禁止把“鼠标当前在哪”“是否 headless”“是否有陈旧缓存/审批态”等真实前提留给 Codex 或人工脑补。
- **回答像对不算通过 (Answer Shape Is Not Proof)**：对运行时敏感任务，禁止仅凭“模型回答看起来正确”“工具返回语气合理”或“前台表现像成功”判定机制生效。验收必须至少命中一类硬证据：结构化日志、状态迁移、持久化文件、审批状态、禁用标记、探针脚本输出。若只能证明“行为像对”，不能证明“机制真的触发”，一律视为未完成。
- **Repo / Runtime 一致性先查明 (Repo-Runtime Parity First)**：凡依赖 `ki_rules/`、workspace 模板、工具注册、ApprovalStore、TaskTracker、Cron 配置、环境变量、Provider 开关等运行时资源的任务，必须在规划阶段逐项写清：`代码位置`、`运行时落点`、`加载路径`、`缺失时的退化行为`。禁止默认认为“仓库里有文件，运行时就一定加载到了”。
- **人工发现缺陷必须升格为确定性回归 (Promote Manual Bugs to Deterministic Regressions)**：凡在最终人工验收中发现的缺陷，必须回流到第二/第三阶段，补成 red test、behavior probe 或 adversarial test 后，才允许标记 phase complete。禁止以“人工知道怎么绕过”或“重启后大概没事”作为完成标准。
- **强制微提交 (Micro-Commits)**：每次 Codex 完成一个子功能并通过验收后，必须提醒用户做小步提交。
- **踩刹车机制**：每个阶段结束时，必须立刻停止回答，等待用户的下一条明确指令。
- **零信任基线原则（ADR-63）**：开工前必须确认 pytest 基线为全绿；基线不绿，不得进入正式编码阶段。
- **HITL 现实约束**：若运行环境存在高风险审批（HITL / ApprovalStore / Headless Block），必须诚实暴露拦截，不得伪装成“已全自动完成”。
- **手动模式优先写清楚**：既然当前环境最容易失败的地方是“手动交接丢信息”，那么每个阶段都必须明确写出“现在请用户做什么、下一句应该回什么”。

---

### 3. 标准制品规范

#### 3.1 `implementation_plan.md`

必须至少包含：

1. `Job ID`
2. `Goal`
3. `Source Context`
4. `Blast Radius Analysis`
5. `Zone Declaration`
6. `Implementation Strategy`
7. `Contract / Data Structures / Function Signatures`
8. `Behavior Contract Matrix`
9. `Hermeticity / Hidden Runtime States Checklist`
10. `Runtime Artifact Parity Checklist`
11. `Proof Signals / Observable Success Criteria`
12. `Risk Notes`
13. `Validation Plan`

若任务涉及运行时注入、审批、后台任务、工具路由、模板落盘、缓存、workspace 资源或外部 Provider 行为，以上第 8~11 项为**强制项**，不得以 `N/A` 草率跳过；若无法写清，应直接 `blocked`，不要进入编码阶段。

#### 3.2 `task.md`

这是 AgentManager 与 Codex 共享的**任务真值表**，必须遵守：

1. 每一项任务都必须有稳定编号，如 `T01`、`T02`、`T03`。
2. 一行只写一个明确交付物，禁止把多个动作揉成一条。
3. 推荐格式：

```md
# Task

- [ ] T01 补红测，锁定失败边界
- [ ] T02 修改 `xxx.py` 以满足红测
- [ ] T03 更新必要文档或契约
```

Codex 在 `codex_result.md` 中必须逐条回应这些编号，便于 AgentManager 验收。

#### 3.3 `codex_handoff.md`

这是 Codex 的**唯一执行契约**。至少必须包含：

1. `Job ID`
2. `Artifact Directory`
3. `Artifact Registry`
4. `Source Context`
5. `Goal`
6. `Allowed Write Set`
7. `Forbidden Write Set`
8. `Red Tests to Satisfy`
9. `Green Exit Criteria`
10. `Behavior Smoke Checks`
11. `Runtime Parity Checks`
12. `Proof Signals to Inspect`
13. `Stop Conditions`
14. `Codex Startup Checklist`
15. `Return Contract`

其中关键条款如下：

- `Artifact Registry`：逐项列出 `implementation_plan.md`、`task.md`、`codex_handoff.md`、红测文件、关键参考文档的精确路径。
- `Behavior Smoke Checks`：列出 1~3 个可执行的行为探针命令、半自动脚本或严格步骤，用于验证 red test 未完全覆盖的运行时行为。凡是命中 `ZONE A/B` 且涉及工具、副作用、安全分级、审批、RPA、channel、headless/visible 切换等运行时状态的任务，至少必须登记 1 个 smoke check；若某个场景可能出现“前台回答正确，但机制根本没触发”，则 smoke check 必须优先验证**机制本身**而不是话术表象。缺失即 handoff 不合格。
- `Runtime Parity Checks`：逐项列出需要在真实运行时确认的资源与状态，例如：`ki_rules` 目录、workspace 模板落盘、工具注册、ApprovalStore、TaskTracker、Cron 记录、环境变量、Provider 配置。必须写清“在哪里看、看什么、缺失会怎样”。
- `Proof Signals to Inspect`：逐项列出必须看到的日志、状态迁移、持久化字段、审批态、禁用标记或探针输出；若任务声称成功但未观测到这些信号，则默认验收失败。
- `Codex Startup Checklist`：要求 Codex 的第一动作必须是按 Registry 逐个读取关键制品，并在编码前回显“已读取哪些文件、理解到的目标/边界是什么、需要检查哪些运行时制品/证据”；若任一制品缺失或不可读，必须立刻 `blocked`。
- `Return Contract`：要求 Codex 完成后写回 `codex_result.md`，而不是只在聊天里写总结；对运行时敏感任务，必须同时写出 `Observed Proof Signals` 与 `Runtime Parity Findings`。

#### 3.4 `codex_result.md`

AgentManager 必须在第二阶段预先写好模板，要求 Codex 完成后覆盖填写。推荐格式如下：

```md
# Codex Result

Status: success | blocked | failed
Job ID: <job_id>

Artifacts Read:
- <path>

Task Coverage:
- T01: done | partial | not done — <说明>

Deviation from Plan:
- none

Changed Files:
- <path>

Executed Tests:
- `<command>` -> pass | fail

Behavior Smoke Checks Executed:
- `<command or probe>` -> pass | fail | not run

Observed Proof Signals:
- `<log/state/probe>` -> seen | not seen

Runtime Parity Findings:
- `<resource or runtime location>` -> present | missing | inferred

Suggested Validation Steps:
- <建议 AgentManager 复跑的测试或检查；对 ZONE A/B 运行时敏感任务，必须优先给出可执行 probe，而不是泛泛而谈>

Suggested Review Focus:
- <建议 AgentManager 重点审查的风险点>

Untested Runtime States:
- <本轮没有覆盖到的隐藏状态、环境前提或真实依赖>

Open Risks:
- <剩余风险>

Need Manager Review:
- <需要 AgentManager 决策或复核的事项>
```

#### 3.5 `codex_feedback.md`

AgentManager 在第三阶段验收失败时，必须生成或覆盖该文件。推荐格式如下：

```md
# Codex Feedback

Status: rework
Job ID: <job_id>

Failed Commands:
- `<command>`

Key Errors:
- <关键报错>

Severity A:
- <必须修复的 blocker>

Severity B:
- <重要但次一级的问题>

Must Fix Files:
- <path>

Regression to Add:
- <必须补的 red test / behavior probe / adversarial test>

Boundary Reminder:
- 继续遵守原 handoff 的 Allowed Write Set / Forbidden Write Set

Return Instructions:
- 修复完成后重写 `codex_result.md`
```

---

### 4. 第一阶段：深度理解与规划 + 架构划区 (Analysis & Zone Declaration)

**触发条件**：用户要求启动一个新任务，或要求按本工作流执行任务。

#### AgentManager 必须执行

1. 读取指定的 `Phase XX` 任务、计划文档或需求来源。
2. 若用户未提供 `job_id`，生成一个新的 `job_id`。
3. 创建 Artifact 目录：`.agent/artifacts/execute_phase/<job_id>/`
4. 仔细检查当前项目中将被影响的核心代码文件。
5. 生成：
   - `implementation_plan.md`
   - `task.md`
   - `codex_handoff.md`
6. 在 `task.md` 中使用稳定任务编号，如 `T01`、`T02`。
7. 在 `implementation_plan.md` 中单开 **【爆炸半径评估 (Blast Radius Analysis)】**。
8. 在 `implementation_plan.md` 中紧跟追加 **【架构划区与回归域 (Zone Declaration)】**，将本次改动归属至以下三区之一：
   - `ZONE A`：波及 `loop.py`, `context.py`, `session/manager.py`, `middleware/`, `verification.py`
     对应靶向命令：
     `pytest tests/test_loop*.py tests/test_session*.py tests/test_middleware*.py tests/test_phase31*.py tests/adversarial/ -W ignore -v`
   - `ZONE B`：波及 `tools/`, `channels/`, `skills/`, `cron/`
     对应靶向命令：
     `pytest tests/test_<具体工具名称>.py tests/test_channel*.py -W ignore -v`
   - `ZONE C`：波及 `config/`, `docs/`, `scripts/`
     对应靶向命令：
     按受影响模块精准执行，或无需测试
9. 在 `implementation_plan.md` 中继续追加 **【Behavior Contract Matrix】**，至少覆盖核心成功路径、核心拦截路径、以及 1 个最可能被隐藏状态击穿的失败路径。每一行必须写清：输入、预期行为/分级、隐藏运行时状态、自动验证方式、人工验收信号。
10. 在 `implementation_plan.md` 中继续追加 **【Hermeticity / Hidden Runtime States Checklist】**，逐项审视会影响结果的环境状态，例如：缓存文件、`tmp/` 制品、`monitor_context.json`、鼠标/焦点位置、headless/visible 模式、审批态、外部网络、登录态、时区、特定窗口布局。必须注明哪些会 mock，哪些只能通过 smoke check 或人工验收验证。
11. 在 `implementation_plan.md` 中继续追加 **【Runtime Artifact Parity Checklist】**，逐项列出本次方案依赖的 repo 制品与运行时落点，例如：规则文件目录、workspace 初始化模板、工具注册入口、审批存储、TaskTracker 状态源、Cron 持久化记录、环境变量、Provider 开关。每一项必须写清：`代码位置`、`运行时落点`、`加载路径`、`缺失时退化行为`。
12. 在 `implementation_plan.md` 中继续追加 **【Proof Signals / Observable Success Criteria】**，逐项写清必须看到的日志、状态迁移、文件落盘、审批状态、禁用标记或探针脚本输出；禁止只写“回复应当推荐 xxx”这种表层现象。
13. 在 `codex_handoff.md` 中写好 `Artifact Registry`，必须至少登记：
    - `implementation_plan.md`
    - `task.md`
    - `codex_handoff.md`
    - 关键参考文档
    - 预期会被修改的测试文件或代码文件（若此时已知）
14. 在 `codex_handoff.md` 中登记 `Behavior Smoke Checks`、`Runtime Parity Checks` 与 `Proof Signals to Inspect`；若本次任务命中 `ZONE A/B` 且涉及工具、副作用、安全/审批链路、RPA、channel 或真实运行时状态，而 handoff 中缺少这些条目，则第一阶段不合格。
15. 在终端运行 Zone 对应的绿色基线 `pytest` 命令，并记录命令与结果。
16. 若该命令被 HITL / Approval / 环境限制拦截，必须明确暴露阻塞原因，并把待执行命令原样交给用户审批或兜底执行；禁止把“跑基线”本身下放成默认用户职责。

#### 第一阶段结束时，必须明确告诉用户做什么

若绿色基线已由 AgentManager 成功跑绿，你必须输出类似下面的提示语，并**立即停止回复**：

```text
✅ 第一阶段完成
job_id: <job_id>
Artifact 目录: .agent/artifacts/execute_phase/<job_id>/
绿色基线:
<Zone 对应 pytest 命令> -> pass

请你现在先审查以下文件：
- .agent/artifacts/execute_phase/<job_id>/implementation_plan.md
- .agent/artifacts/execute_phase/<job_id>/task.md
- .agent/artifacts/execute_phase/<job_id>/codex_handoff.md

确认无误后请回复：
开始测试驱动开发，job_id=<job_id>
```

若绿色基线因 HITL / Approval / 环境限制无法由 AgentManager 直接执行，则改为输出类似下面的提示语，并**立即停止回复**：

```text
⏸️ 第一阶段阻塞
job_id: <job_id>
Artifact 目录: .agent/artifacts/execute_phase/<job_id>/

AgentManager 已完成规划与 Artifact 落盘，但绿色基线命令被环境拦截，尚未确认。

请你现在做两件事：
1. 审查以下文件：
   - .agent/artifacts/execute_phase/<job_id>/implementation_plan.md
   - .agent/artifacts/execute_phase/<job_id>/task.md
   - .agent/artifacts/execute_phase/<job_id>/codex_handoff.md
2. 处理下面这条绿色基线命令（批准 AgentManager 执行，或由你亲自运行）：
   <此处填入 Zone 对应 pytest 命令>

如果基线通过，请回复：
开始测试驱动开发，job_id=<job_id>

如果基线失败，请回复：
基线失败，job_id=<job_id>
```

#### 基线失败分支

如果 AgentManager 自跑基线失败，或用户在兜底执行后回复 `基线失败，job_id=<job_id>`，则：

1. 不得进入第二阶段。
2. 必须先判断这是既有债务还是本次任务范围选择错误。
3. 必须明确告诉用户：当前任务暂停，先处理基线问题或重新缩小任务范围。

---

### 5. 第二阶段：契约先行、红测锁定与结构化移交 (Contract-First & Structured Handover)

**触发条件**：用户回复 `开始测试驱动开发，job_id=<job_id>`，或明确确认绿色基线已通过。

#### AgentManager 必须执行

1. 编写 red test 或 Adversarial Tests，修改对应 `tests/` 文件。
2. 在终端运行 red test 命令，证明测试确实失败。
3. 若 `Behavior Contract Matrix` 中存在 red test 无法覆盖的隐藏状态，必须补出 `Behavior Smoke Checks`：可以是可执行 probe、严格脚本化步骤，或最少歧义的半自动行为检查。凡是命中 `ZONE A/B` 且涉及工具、副作用、安全/审批、RPA、channel、headless/visible 等真实状态的任务，至少保留 1 个 smoke check。
4. 若任务依赖运行时资源或注入机制，必须补出至少 1 个 **机制级 probe**：它要能证明“机制真的触发”，而不是只证明“回复像是对的”。
5. 将 red test 命令、失败摘要、预期修复边界、`Behavior Smoke Checks`、`Runtime Parity Checks`、`Proof Signals to Inspect` 补写进 `codex_handoff.md`。
6. 若实际路径与默认路径有偏差，立刻补全 `Artifact Registry`。
7. 预先创建 `codex_result.md` 模板，写入 `Job ID` 和字段骨架，且必须包含 `Behavior Smoke Checks Executed`、`Observed Proof Signals`、`Runtime Parity Findings` 与 `Untested Runtime States`。
8. 预先创建空白 `codex_feedback.md` 或至少确定其目标路径。
9. 若当前环境支持自动派工，则以 `codex_handoff.md` 为唯一执行契约发起自动派工。
10. 若当前环境**不支持**自动派工，则必须给用户一个**固定启动语**，让用户原样交给 Codex，禁止自由转述。

#### 第二阶段结束时，必须明确告诉用户做什么

你必须输出类似下面的提示语，并**立即停止回复**：

```text
⏸️ 第二阶段完成
job_id: <job_id>
Artifact 目录: .agent/artifacts/execute_phase/<job_id>/

红测已锁定，Codex 执行契约已就绪。

如果当前 IDE 无法自动派工，请你现在打开 Codex，并原样发送下面这段启动语：

请严格执行 execute_phase 工作流。
先读取 `.agent/artifacts/execute_phase/<job_id>/codex_handoff.md`。
再按其中 Artifact Registry 读取全部关键制品。
缺件即 blocked，不要自行重规划，不要自行重写 implementation_plan/task。

如果 Codex 因“找不到文件”而 blocked，请不要转述，请直接把以下文件原样附给 Codex：
- .agent/artifacts/execute_phase/<job_id>/codex_handoff.md
- .agent/artifacts/execute_phase/<job_id>/implementation_plan.md
- .agent/artifacts/execute_phase/<job_id>/task.md

Codex 完成后应回写：
.agent/artifacts/execute_phase/<job_id>/codex_result.md

收到 Codex 结果后，请回到 AgentManager 并回复：
开始验收，job_id=<job_id>
```

#### 对 Codex 的硬性要求

`codex_handoff.md` 必须明确要求 Codex：

1. 先读 Artifact，再编码。
2. 任何关键制品缺失时，不得自行补写新计划替代；只能 `blocked`。
3. 编码完成后，必须先写 `codex_result.md`，再回聊天界面。
4. 对运行时敏感任务，必须显式记录 `Observed Proof Signals` 与 `Runtime Parity Findings`；若只拿到了“回答像对”的表象，但没拿到硬证据，必须如实写为未完成或待验证。
5. 若 `Behavior Smoke Checks` 中有无法在当前环境执行的项，或发现新的隐藏运行时状态，必须在 `codex_result.md` 中明确写入 `Untested Runtime States`，禁止静默假设“应该没问题”。
6. 聊天界面里的结尾提醒应当是**薄启动语**，例如：

```text
请回到 AgentManager，并回复：
开始验收，job_id=<job_id>
请先读取 `.agent/artifacts/execute_phase/<job_id>/codex_result.md`。
```

---

### 6. 第三阶段：结构化回执验收、自动返工与防暴走拦截 (Verification & Intercept)

**触发条件**：检测到 `codex_result.md`，或用户回复 `开始验收，job_id=<job_id>`。

这是最严苛的验收阶段。AgentManager 的任务不是“听 Codex 说自己做完了”，而是**核对它是否真的按计划施工**。

#### AgentManager 必须执行

1. 优先读取 `.agent/artifacts/execute_phase/<job_id>/codex_result.md`。
2. 先核对 `Artifacts Read` 是否覆盖以下关键制品：
   - `codex_handoff.md`
   - `implementation_plan.md`
   - `task.md`
3. 若 `Artifacts Read` 缺失、覆盖不全、路径错误，或与 `Artifact Registry` 冲突，应视为**回执不合格**，直接进入返工闭环。
4. 核对 `Task Coverage` 是否逐条回应 `task.md` 中的每个任务编号。
5. 核对 `Deviation from Plan` 是否对越界实现做出解释；若发生重大偏离但未声明，应判为问题。
6. 核对 `Changed Files` 是否全部落在 `Allowed Write Set` 内，且未触碰 `Forbidden Write Set`。
7. 在终端重新运行第一阶段声明的 `pytest` 靶向命令与第二阶段锁定的红测命令。
8. 若 L1 全绿，必须执行 `codex_handoff.md` 中登记的 `Behavior Smoke Checks`。对于 `ZONE A/B` 的运行时敏感任务，缺少 smoke check、smoke check 无法执行却未明确阻塞、或实际观察结果与 `Behavior Contract Matrix` 不一致，均应直接判为验收失败。
9. 核对 `Observed Proof Signals` 与 `Runtime Parity Findings` 是否与 `Proof Signals to Inspect`、`Runtime Artifact Parity Checklist` 一致；若日志、状态、落盘、审批态或禁用标记缺失，就算前台回答正确，也不得判为通过。
10. 若本轮结果只能证明“行为像对”，不能证明“机制真的触发”，必须判为验收失败或继续补验证，禁止以“人工感觉差不多”收口。
11. 若 L1 与 `Behavior Smoke Checks` 全绿，再运行自动化 L2 语义审查：
   `python .agent/scripts/auto_reviewer.py --context "核对 task.md 落地情况，防范架构腐化"`
12. 参考 `Suggested Validation Steps`、`Suggested Review Focus` 与 `Untested Runtime States` 做补充审查；若 `Untested Runtime States` 覆盖到了本次变更的核心行为，应判定为“不能收尾，只能继续补验证”。

#### 验收失败时，必须执行结构化返工

如果 L1、`Behavior Smoke Checks` 或 L2 任一失败，或者回执本身不合格，你**绝对不可以**偷偷自己修代码。你必须：

1. 生成或覆盖 `.agent/artifacts/execute_phase/<job_id>/codex_feedback.md`
2. 明确写入：
   - 失败命令
   - 关键报错
   - `Severity A`
   - `Severity B`
   - 必须修复的文件
   - 必须新增的回归测试或行为探针
   - 不允许偏离的边界
3. 若当前环境支持自动派工，且累计返工轮次 `< 2`，则用 `codex_feedback.md` 自动回派 Codex。
4. 若当前环境**不支持**自动派工，则让用户把 `codex_feedback.md` 原样交给 Codex。

#### 第三阶段失败时，必须明确告诉用户做什么

你必须输出类似下面的提示语，并**立即停止回复**：

```text
❌ 第三阶段未通过
job_id: <job_id>

返工单已生成：
.agent/artifacts/execute_phase/<job_id>/codex_feedback.md

请你现在打开 Codex，并原样发送：

请读取 `.agent/artifacts/execute_phase/<job_id>/codex_feedback.md`。
只修复其中列出的问题。
继续遵守原 handoff 中的 Artifact Registry、Allowed Write Set、Forbidden Write Set。
缺件即 blocked，不要自行重规划。

如果 Codex 因“找不到文件”而 blocked，请不要转述，请直接把以下文件原样附给 Codex：
- .agent/artifacts/execute_phase/<job_id>/codex_feedback.md
- .agent/artifacts/execute_phase/<job_id>/codex_handoff.md
- .agent/artifacts/execute_phase/<job_id>/implementation_plan.md
- .agent/artifacts/execute_phase/<job_id>/task.md

Codex 修复后应重写：
.agent/artifacts/execute_phase/<job_id>/codex_result.md

完成后请回到 AgentManager 并回复：
开始验收，job_id=<job_id>
```

#### 第三阶段通过时，必须明确告诉用户做什么

若 L1、`Behavior Smoke Checks` 和 L2 全数通过，你必须输出类似下面的提示语，并**立即停止回复**：

```text
✅ 第三阶段通过
job_id: <job_id>

自动化 L1 / Behavior Smoke / L2 审查均已通过。
请回到 AgentManager 并回复：
开始收尾，job_id=<job_id>
```

#### 两轮返工仍失败的拦截规则

如果连续两轮返工后仍存在 `Severity A` / `Severity B` 残留：

1. 不再继续局部打补丁。
2. 必须明确建议用户：回退到 Harness 重新辩证，或重新规划为更小的任务。

---

### 7. 第四阶段：文档三权分立与靶向测试 (Wrap-up & Targeted Manual Tests)

**触发条件**：用户回复 `开始收尾，job_id=<job_id>`。

#### AgentManager 必须执行

1. 将本次协同踩到的教训追加到 `docs/rules/ARCHITECTURE.md`。
2. 将技术细节归档到 `docs/archive/`。
3. 在 `progress_report.md` 中用一句话更新进度。
4. 生成或更新 `docs/tests/manual_guides/phase_XX_manual_test_guide.md`。
5. 在人工测试手册中单开 **【连带回归靶点 (Regression Targets)】**，从 `Blast Radius Analysis` 中提取最易受损的旧功能。
6. 在人工测试手册或 ADR / progress 文档中追加 **【Postmortem / Lessons Learned】**，至少写清：本次曾经出现过的假阳性通过信号、真正的硬证据是什么、后续 workflow 护栏是否已同步更新。
7. 若最终人工验收暴露出新的 bug，必须立刻回退到第二/第三阶段：先把该 bug 升格为确定性 red test、behavior probe 或 adversarial test，再允许继续推进。禁止在“已知存在人工复现 bug”状态下宣布 phase 完成。
8. 明确提醒用户：现在应该做一次**微提交**。

#### 第四阶段结束时，必须明确告诉用户做什么

你必须输出类似下面的提示语：

```text
🎉 第四阶段完成
job_id: <job_id>

本次执行已完成：
- 代码实施
- 自动化测试回归
- Behavior Smoke 验证
- L2 语义审查
- 文档归档
- 靶向人工测试手册

建议你现在做两件事：
1. 按 manual guide 做最后一轮人工验收
2. 对本次已通过验收的子功能进行微提交

如果人工验收发现新的 bug，不要直接口头记录；请立即回到 AgentManager，并重新进入返工闭环，把该 bug 先固化为回归测试或行为探针。
```

---

### 8. 异常处理速查

#### 8.1 Codex 找不到 `implementation_plan.md` / `task.md`

处理方式：

1. 不要自己转述计划内容。
2. 直接把以下文件原样附给 Codex：
   - `codex_handoff.md`
   - `implementation_plan.md`
   - `task.md`
3. 重新发送固定启动语。

#### 8.2 Codex 没读 Artifact 就开始编码

处理方式：

1. 在第三阶段直接判为回执不合格。
2. 在 `codex_feedback.md` 中把“未按 Startup Checklist 读取制品”列为 `Severity A`。

#### 8.3 Codex 改了 Forbidden Write Set

处理方式：

1. 在第三阶段直接判为 `Severity A`。
2. 返工时必须强调只允许在 `Allowed Write Set` 内施工。

#### 8.4 用户很忙，忘记下一步该说什么

处理方式：

1. AgentManager 每个阶段结束时都必须给出“下一句请你回复什么”的精确文本。
2. 若仍然忘记，用户只需回到本文件顶部的 **用户速查卡**，照抄即可。
