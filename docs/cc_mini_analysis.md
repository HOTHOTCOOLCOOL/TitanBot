# CC-Mini / Claude Code Architecture Analysis

> **Date**: 2026-04-02
> **Target**: [e10nMa2k/cc-mini](https://github.com/e10nMa2k/cc-mini)
> **Goal**: 逆向挖掘 Claude Code / cc-mini 的核心架构范式，输出对 Nanobot 高 ROI 的方案参考。

## 1. 核心架构对标分析

`cc-mini` 是一个仅约 1000 行 Python 代码的极简框架，但实现了原生 Claude Code 中甚至还未公开发布的高级功能。由于 Nanobot 同为"无额外基础设施"理念的极简纯 Python 框架，这些范式可视为极为对口的最佳实践。

| CC-Mini / Claude Code 范式 | 针对的工程痛点 | 对标 Nanobot 的模块 | 契合度与价值 |
|--------------------------|--------------|-------------------|------------|
| **Auto-Compaction** (平滑压缩) | 解决长期会话硬性 Token 截断导致的关键上下文丢失。在溢出前按频率主动进行摘要。 | `memory.py` (L4 Eviction) | ⭐⭐⭐⭐⭐ 高！是对现有 L4 简单阶段截断方案的极大提升。 |
| **CLI Native Skills** (`/skill`) | 绕过大模型意图推断的不稳定性，为常用任务（Review/Test）降维提供确定性的命令直达。 | `skills.py` & `cli/main.py` | ⭐⭐⭐⭐⭐ 高！将已有的 plugin 变成终端 First-class citizen。 |
| **Bubblewrap Sandbox** | 纯语法 AST Sandbox 在面对深层 shell 套娃时依然有穿透风险。`bwrap` 提供了 OS 级沙盒保障。 | `base.py` & `tools/shell.py` | ⭐⭐⭐⭐ 中。彻底解决 RCE (远程代码执行) 防御漏洞，但依赖 Linux 底层环境。 |
| **Coordinator Mode** (后台组) | 长时间代码执行与资料搜集（如浏览器任务）会阻塞用户交互。主 Agent 可派生出并在后台与子 Agent 通信。 | `subagent.py` & `loop.py` | ⭐⭐⭐⭐ 高！真正的多代理并发。 |
| **Buddy System** (养成互动) | 降低长交互枯燥感，游戏化开发流程。 | Channel Telegram/Discord / UI | ⭐⭐⭐ 附加项。对企业效率无硬性影响，但在交互形态上较有新意。 |

## 2. 提炼出的高 ROI 开发方案

出于零基建架构的包袱考量，**平滑上下文压缩** 与 **强类型终端原生指令** 是当前实现周期最短（估计1-3天）、收益影响最广的两项：

### 📌 ROI #1: 上下文滑动压缩管道 (Auto-Compaction)
**问题：** 当前 Agent 遇到极长的 log 和网页读取时，Token 超出后直接利用 L4 将最早的消息 Eviction。这会导致模型完全“失忆”自己 10 个轮次前制定的底层目标。
**方案：** 
- 设置一个 Token 阈值告警线（例如 `context_window` 的 85%）。
- 告警触发时，将所有位于当前轮次 N 回合前的对话消息打包（含 system、user、assistant）。
- 后台通过轻量模型迅速提取出 `SystemContextSummary` 替换原有庞大的对话记录。
- 实现 `/compact` 给用户进行手动降维提纯。

### 📌 ROI #2: 第一级 CLI 原生技能工作流 (First-Class CLI Skills)
**问题：** 想要执行代码 review 时，必须先在 prompt 里提示大模型："请使用你的 review 技能分析..."，模型再在执行链路中载入该 tool 工具集合。
**方案：**
- 在 `cli` 与 `gateway` 层面提供针对 `/[skill_name]` 格式的拦截指令。
- 直接初始化一个全新的、高度剥离且系统 Prompt 就是为改技能定制的局域 Agent 循环来解决该任务。
- 使之变得确定如一般 terminal 命令行 `nanobot --review` 一样可靠，同时返回标准的格式化报告回主会话。

### 📌 ROI #3 (中远期展望): Bwrap 与后台 Coordinator 
我们计划将 Bubblewrap OS 级沙盒概念推入已规划的 Phase 35 `跨平台 OS 沙盒`，而 Coordinator 的异步架构将作为长期 Backlog 进行逐步攻破。

---

## 3. Harness 边界测试与最终结论 (2026-04-03 审计)

经过内部 Harness 工作流的 Planner/Critic 深度碰撞与冷眼审计，我们得出以下反思与结论：

1. **Nanobot 现有机制已足够完善**：cc-mini 需要从头构建 Auto-Compaction，而 Nanobot 已经拥有完整的 `memory_manager`（后台异步合并）、`evicted_context`（虚拟分页缓冲）与 `context_limit`（预算截断）。
2. **Phase 35 痛点为"伪需求"**：
   - 上下文"失忆"仅出现在罕见的极端连续场景，可通过调参 (`memory_window` / `context_limit`) 解决。
   - 现有的 `SkillsLoader` 配合大模型工具调用已运行良好，`SubagentManager` 也提供了坚实的隔离。专门为长尾任务如 `/review` 提供复杂的专用 CLI 解析与分流通道，不仅 ROI 极低，还会违反"零架构冗余"的初衷。
3. **最终决议**：
   - **取消 Phase 35 独立迭代**。
   - `P35-1` 的手动压缩需求（`/compact` 映射至 `deep_consolidate`）降级为日常维护中的一个小 **Hotfix**。
   - `P35-2` Native CLI Skills 方案因不符合当前极简总线演进方向而被 **暂缓/搁置**。
   - 开发重点全量回溯到对实际业务感知（业务意图理解、概念推理）有实质提升的 **Phase 34 (KG 检索增强)**。
