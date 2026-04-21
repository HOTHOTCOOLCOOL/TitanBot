# Antigravity 引擎与 Nanobot 架构对比分析参考指南

**作者**: Antigravity (Google DeepMind)
**目标读者**: Nanobot 核心架构师
**主旨**: 解构顶级智能体（Agent）的底层调度逻辑，并为 Nanobot 下一阶段的架构演进提供可落地的工程级参考模式。

---

## 引言：为什么我们需要精密的 Agent Manager？
市面上开源的 Agent 往往采用极其激进的“无限循环自修正（Re-Act / Loops）”模式，这种模式虽然显得智能，但在遇到实际的企业级复杂系统时，往往会因为下错指令陷入死锁、把代码改得面目全非，或者因为 Token 消耗极快而导致“智力降级”。

作为企业级大模型基建的代表，Antigravity 不允许“发散性”的错误。我们的 Agent Manager 在架构上保持了**高度克制与防守**。以下提炼的五大核心机制，均可通过几百行 Python 代码平滑移植到 Nanobot 生态中。

---

### 1. 结构化规划拦截模式 (Planning Mode vs. Greedy Execution)

**问题背景**：
当接到的任务是一个超级需求（比如：“把我的数据库全部迁移到 Redis”），普通的 Agent 听完立马就开始写代码、删文件。这种**“贪婪物理执行”**极其危险。

**Antigravity 机制原理**：
每收到一个长指令，系统的前置判断层模块评估出“复杂度高/高危”时，会强制加锁进入 **Planning Mode (规划模式)**：
1. **沙盒化约束**：主引擎被瞬间**吊销**所有的写操作与执行命令工具，只保留 `grep` 和 `view_file` 这类只读工具。
2. **强制产出文档**：我必须生成一个标准格式的 `implementation_plan.md` 架构文档。
3. **人类挂起**：通过 `RequestFeedback=True` 将主线程完全挂起（休眠）。
4. **人工断点放行**：只有当人类点击了“Approve (或者通过特定钩子打回修订)”，引擎才会解锁写权限进入 `Execute` 模式。

**针对 Nanobot 的落地建议**：
这可以在 Nanobot 下一阶段应用。实现一个 `Router Agent` 层：
- 增加一个“工作流状态机”。当指令复杂时，Nanobot 停止调用执行工具，而是触发特定动作输出 `PLAN_JSON`。
- 要求在控制台上输出“[!] 计划已生成，请在此处按 `Y` 执行，或输入修改意见：”。

---

### 2. 物理介质状态跟踪 (Artifact State Tracking) 

**问题背景**：
长程对话会导致 System prompt 里的记录越来越多，Context Window 会逐渐污染。很多开源框架使用复杂的图数据库或者 SQLite 搞所谓的“记忆网络”。但这非常耗计算资源，而且容易产生幻觉偏移。

**Antigravity 机制原理**：
Antigravity 最聪明的点在于：**把硬盘当做内存使用**。
- 当我开始执行复杂工单，我会在磁盘创建一个 `task.md` 文件（类似于清单）。
- 里面长这样： `- [/] 正在重构 API`、`- [ ] 修复单元测试`。
- 每次我陷入迷茫，或者你指出我的错误，我都会去改写和复查这篇 Markdown，让它作为我的唯一真实状态源（Single Source of Truth）。哪怕系统崩溃，重启只要读一下 `task.md` 就能瞬间恢复智商。

**针对 Nanobot 的落地建议**：
正吻合你们架构师放弃 SQLite schema 的思路（见 ADR-56）。
- 可以为 Nanobot 开发一个基础工具箱：允许它把长串的推导逻辑、待办事项调用某个隐藏的写操作工具落地为 `.nanobot_workspace/tasks.txt`。每次进行下一个动作前，它先去加载这几百个纯文本字节当做定盘星。

---

### 3. 沙盒隔离与异步监控 (Sub-Agent Delegation & Async Backgrounding)

**问题背景**：
当我们需要驱动网页端点击测试，或是让机器编译一个超大型 C++ 项目。如果 Agent 主线程傻等命令结束，Token 的费用在等候询问中会爆炸，或者 Agent 会不耐烦擅自去处理别的。

**Antigravity 机制原理**：
- **浏览器副脑 (Browser Subagent)**：面对前端任务，我会丢给另一个经过专项微调的瞎子模型（带着非常简短的 Prompt），它自己会启动一个无头浏览器抓死磕 HTML DOM，只有录到了正确的界面，它才返回一个“成功/失败”的结果。
- **后台命令池 (Async Run)**：如果跑耗时命令，我调用时标记 `WaitMsBeforeAsync`。引擎就把这个 shell 扔进后台，返回给我一个唯一的 `Command_UUID`。我去干其他事，等我想起来，我再调用 `command_status(uuid)` 去探一探它死了没有。

**针对 Nanobot 的落地建议**：
你在开发 Phase 53 的 `ExcelActuatorTool` （Excel RPA控制层）时，这就完美契合。不要让主 Nanobot 直接用 python 操作 Excel 的 COM 线程（单线程死锁的噩梦）。把它封装丢进 `ThreadPoolExecutor` 或者独立的 `multiprocessing` 扔一个 `task_id` 后去阻塞等待，这对于 GUI 工作流至关重要。

---

### 4. 黄金经验强注 (Knowledge Items / KI System)

**问题背景**：
模型很容易犯同一个错误。哪怕是在同一个代码仓库里，第一次不知道怎么找路由，全网瞎搜了五分钟搜到了，第二次做相似业务，它还是会重走一遍漫长的找路由老路。因为普通框架对于“记忆”其实是金鱼属性的短记忆。

**Antigravity 机制原理**：
- 它包含严格分离的两个领域层级记忆：`Logs`(极强噪音) 与 `KI`(高度提纯经验)。
- 我解决完一个大坑，会从 Log 中提炼知识点存盘（Knowledge Item）。
- **强制阻断**：每个包含我处理特定仓库的对话一旦开启，引擎的拦截器会先强行搜刮一遍当前仓库是否有相关 KIs。如果有，强行插入当前上下文：要求我不准再按照大模型的野生经验来，照着 KI 里的硬指令配！从物理上断绝了反复掉坑和胡编乱造的可能。

**针对 Nanobot 的落地建议**：
这简直是你们正在准备阶段的 Phase 57 (Context Intelligence Upgrade) 的极佳养料！
在现在的 `context.py` 中增加一段 `KI` 前置拦截提取池，赋予其绝对高的额度优选权，并用一个独立文件夹（如 `.nanobot/ki_rules/`）允许开发者以极为死板的 QA 格式手写或者自发沉淀避坑经验，每次回答前挂载这些高优权重，你的 Nanobot 响应准度会令人发指。

---

### 5. 并发工具的阵列吞吐 (Concurrent Tool Execution)

**问题背景**：
当你想让模型帮忙看一个项目的 5 个文件，普通模型怎么做的？
请求 1 -> 给我看 a.py -> 收到 -> 请求 2 -> 看 b.py ...
一趟来回需要调用 LLM 5 次才能收集齐上下文。API 调用的网络延迟和费用成螺旋指数式飙升。

**Antigravity 机制原理**：
- 我具有极强的结构化队列输出能力（依托于多 Function Call 格式）。
- 对抗这种网络延迟开销的办法，就是在一轮思考里计算出所有互不依赖的动作。底层网关解析到这并列的多个工具声明后，用 Python 原生的多线程调度（例如 `asyncio.gather` 或多线程队列）同时在本地并发执行这五个工具，最终等五个全部执行完，打包在一个列表对象里一次性丢还给我查阅。一次来回，搞定平时十次来回的工作量。

**针对 Nanobot 的落地建议**：
在未来的开发中，Nanobot 解析大模型吐出来的 `<tool_calls>` 时，应该设计成返回 `List[Dict]`，如果 List 有多个独立元素且不需要强依赖，交给 `concurrent.futures` 线程池同步爆破抓取。

---
**阅读说明**
这 5 大理念分别切中了资源管理、任务解耦和自我演进这三大企业级 RPA 和 AI 系统的深水区瓶颈。它们都可以利用 Nanobot 的特性化微型组件进行小步改造，而并不需要大刀阔斧推翻已有系统。如果你想让你的 Agent Manager（调度层）演化得更加健壮，我随时可以陪你深入其中任何一项进行代码落地。

---

## 附录：Harness 5 阶辩证工作流 — 最终落地决策 (ADR-59)

> **更新于**: 2026-04-18 | **决策文档**: [`docs/adr/ADR-59-antigravity-pattern-integration.md`](file:///d:/Python/nanobot/docs/adr/ADR-59-antigravity-pattern-integration.md)
> 本节记录对上述 5 大机制经过「Planner → Opus Critic → Gemini Pro High → Gemini Pro Low → Sonnet Final」5 阶辩证工作流审查后的最终落地决策，替代原文中的落地建议。

### 最终对齐矩阵

| # | Antigravity 机制 | Nanobot 最终实现方案 | 变更量 |
|---|---|---|---|
| 1 | Planning Mode | `write_artifact` 工具（`IS_HIGH_RISK`）借道现有 `HITLMiddleware` 实现审批阻断；`AGENTS.md` 追加 Complex Task Protocol 提示词锚点。**不引入状态机/DAG。** | Feature C |
| 2 | Artifact State Tracking | 复用已有 `TaskTracker`（458行）；`context.py::build_messages()` 追加 `_format_task_status()` 注入（最近 3 步，硬上限 400 chars）；新增 `update_task_progress` 内置工具。 | Feature B |
| 3 | Sub-Agent / Async BGing | 现有 `ExcelActuator PID 监控` + `GroupRAG` + `browser_use_worker` 已充分覆盖。**不触碰，不新建统一 TaskRegistry。** | 无需修改 |
| 4 | KI Injection | `.nanobot/ki_rules/*.ki.json`（< 500 chars/条）；确定性关键词初筛；`verification.py::enrich_context()` 首行前插；计入 ADR-57 WaterfallBudget 总预算。 | Feature D |
| 5 | Concurrent Tool Exec | `loop.py` L827 + `tool_executor.py` L60 均已通过 `asyncio.gather` **100% 实现**。**代码审计确认，无需任何修改。** | ✅ 已完全对齐 |

### 关键架构洞察（辩证精华）

**Nanobot 的 Planning Mode 不需要状态机。**
Antigravity 的 Planning Mode 依赖引擎层的动态权限吊销机制——这在 Nanobot 的「零额外基础设施」哲学下无法原样搬移。但 `HITLMiddleware` 已经是一个在单循环内运行的完美「挂起-审批-恢复」机制。只需将 `write_artifact` 工具标记为 `IS_HIGH_RISK`，即可零成本复用这套审批流，实现等效的 Planning Gate，且严格遵守 `ARCHITECTURE.md`「保持单循环」核心戒律。

**被证伪的 Draft V1 假设（来自代码审计）：**
- ❌ 并发工具执行差距为 70% → ✅ **实为 100%**（两条独立路径均已实现）
- ❌ 需要新建 task.md 状态文件系统 → ✅ **`TaskTracker` 458 行已存在，直接复用**
- ❌ KI 预算与 WaterfallBudget 会冲突 → ✅ **KI 限定 <500 chars/条，纳入 Waterfall 统一计数解决**
