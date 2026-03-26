# Anthropic Harness Design 文章分析 — Nanobot 借鉴意义

> 原文: [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
> 作者: Prithvi Rajasekaran (Anthropic Labs)
> 分析日期: 2026-03-26

---

## 文章核心观点速览

Anthropic 在构建长时间自主编码 agent 时，发现两个关键瓶颈：
1. **Context 焦虑** — 上下文窗口填满后模型会"赶着收工"，compaction 无法解决
2. **自我评估失效** — 模型评价自己的输出时总是"自我感觉良好"，质量判断不可靠

他们用 **GAN 启发的三 agent 架构**（Planner → Generator → Evaluator）解决了这些问题，并在不断迭代中发现了一个元规律：**harness 的每个组件都编码了对模型能力不足的假设，这些假设会随模型进步而过期**。

---

## 与 Nanobot 的对比分析

### ✅ 我们已经做对的

| 文章观点 | Nanobot 现状 | 评价 |
|---------|-------------|------|
| Simple loop > 复杂 DAG | `loop.py` 单循环架构 | **完全一致**，我们的核心哲学 |
| 工具调用后继续循环 | `_CONTINUE_TOOLS` 机制 | **完全一致** |
| Circuit breaker 防止失控 | 3x circuit breaker + 重复检测 | **完全一致** |
| 提示工程对产出质量影响大 | Skills progressive loading + 结构化 prompt | **完全一致** |
| 模型能力进步后应简化 harness | 我们有 Phase 制度，定期 audit | **方向一致** |

### 🔶 部分覆盖，可以加强

#### 1. Context 管理：Compaction vs Reset

**文章观点**: Context Reset（完全清空上下文+结构化交接）优于 Compaction（原地摘要）。模型会产生 "context anxiety"，在认为接近上下文限制时提前收工。

**Nanobot 现状**: 
- 有 L4 Evicted Context（MemGPT 风格虚拟分页）
- 有 auto-consolidation（每 20 条消息）
- Session 持久化支持跨会话
- **但没有主动的 context reset 机制**

**借鉴意义**: ⭐⭐⭐
> 对于长任务（如 cron job 触发的多步骤自主执行），我们可以引入 **Context Reset 策略**：当检测到上下文接近阈值时，不是做原地摘要，而是生成一个结构化交接文档（handoff artifact），然后重启一个干净的 agent session 来继续。这比 compaction 更能保证后续执行质量。

> [!IMPORTANT]
> 不过文章也指出，Opus 4.6 已经不需要 context reset 了——说明这是一个随模型进步而可能消失的问题。我们应该先测量 Nanobot 在当前使用的模型上是否存在 context anxiety，再决定是否投入。

---

#### 2. 外部评估器（Evaluator Agent）

**文章观点**: 将"执行者"和"评判者"分离，用一个专门的 Evaluator agent 来检查 Generator 的输出。Evaluator 需要经过校准（few-shot 示例 + 评分标准），才能避免"仁慈评分"。

**Nanobot 现状**:
- VLM Feedback Loop（截屏→VLM验证→重试）**已经是这个思路的轻量实现**
- Knowledge Judge（add/merge/discard 决策）**也是分离评估的体现**
- 但对于**工具执行结果的质量**没有独立评估

**借鉴意义**: ⭐⭐⭐⭐
> 这是最值得做进 Nanobot 的理念。具体场景：
> 
> **场景 A：自主任务的 QA 回路**
> 当 Nanobot 执行复杂多步操作（如"整理本周邮件并生成周报"），执行完毕后 spawn 一个轻量 evaluator subagent，用不同的 prompt 检查产出质量。这可以复用现有的 `subagent.py` 基础设施。
> 
> **场景 B：Skill 执行质量评估**
> Skill 执行后，用 evaluator 检查输出是否符合预期格式/内容质量，作为 auto-upgrade 前的额外验证层。
> 
> **场景 C：Browser 自动化 QA**
> 类似文章用 Playwright MCP 测试 UI，我们的 BrowserTool 完成操作后，可以用 VLM 对最终页面做 QA 检查。

---

#### 3. Sprint 合同（Sprint Contract）

**文章观点**: Generator 和 Evaluator 在每个 sprint 前协商一个"合同"——定义"完成"的标准。这避免了验收时标准模糊。

**Nanobot 现状**:
- Knowledge workflow 有 extract_key → match 的流程
- 但对于多步骤任务没有预定义的"完成标准"

**借鉴意义**: ⭐⭐
> 可以在 Skill 定义中增加一个可选的 `success_criteria` 字段，让 agent 在执行前知道什么算"成功"。这对 auto-upgrade 决策也有帮助——不只看执行次数，还看是否真正满足了验收标准。
>
> 不过这增加了 Skill 的复杂度。在单 agent 架构下，可以简化为在 Skill prompt 中增加自查清单，而不需要完整的合同协商机制。

---

### ❌ 文章方案不适合 Nanobot 的部分

| 文章方案 | 为什么不适合 |
|---------|------------|
| 三 agent 架构（Planner + Generator + Evaluator） | Nanobot 核心哲学是 **single agent loop**，三 agent 编排违背极简原则。但可以选择性引入 evaluator 作为工具 |
| Context Reset 作为常规机制 | 增加延迟和成本，对个人助手的交互式场景来说 overkill |
| Sprint 分解（feature-by-feature） | 适合长跑编码任务，但 Nanobot 的典型任务粒度较小 |
| 文件通信（agent 间通过写文件交流） | Nanobot 有 MessageBus，用事件驱动更高效 |

---

## 🎯 可落地的具体建议（按优先级排序）

### P0: Evaluator as Tool（评估器工具化）

将"外部评估"理念融入单 agent 架构，**不需要引入多 agent 编排**：

```python
# 在 tool_setup.py 中注册一个 SelfEvaluateTool
class SelfEvaluateTool(Tool):
    """让 agent 用不同的 prompt 角色来评估自己的输出"""
    
    async def execute(self, output: str, criteria: str) -> str:
        # 使用一个 "严格评审者" 系统 prompt
        # 调用 LLM 以第三方视角评估输出
        # 返回评分 + 改进建议
        ...
```

更务实的入口是增强现有 `subagent.py`——让 spawn 出的 subagent 可以作为 evaluator 角色运行。

### P1: Context Health Monitor（上下文健康监控）

在 `loop.py` 中增加上下文使用率的监控指标：

- 当前 token 使用量 / 模型上下文窗口大小
- 当上下文使用率 > 80% 时触发告警
- 在 `/stats` 命令中展示上下文健康状态
- 可选：达到阈值后自动触发 deep_consolidation 或 session 切换

### P2: Skill Success Criteria（技能验收标准）

在 SKILL.md 的 YAML frontmatter 中增加可选字段：

```yaml
---
name: email-weekly-report
description: 生成本周邮件周报
success_criteria:
  - 输出包含本周邮件统计摘要
  - 报告按日期分组
  - 覆盖所有指定发件人
---
```

agent 可以在执行后自检这些标准，作为 auto-upgrade 决策的额外信号。

### P3: Periodic Harness Audit（定期脚手架审计）

文章最核心的元观点：**harness 的每个组件都在编码对模型弱点的假设，随着模型进步这些假设会过期**。

我们已经有 Phase 制度，可以在每个 Phase 结束时增加一个检查项：

> "当前 harness 中哪些保护机制是否仍然必要？新模型是否已经原生解决了某些问题？"

例如：
- 重复工具调用检测 → 新模型是否还需要？
- `_CONTINUE_TOOLS` 机制 → 新模型是否会自己判断何时继续？
- Circuit breaker 阈值 → 是否需要调整？

---

## 总结

| 维度 | 文章方法 | Nanobot 现状 | 建议动作 |
|------|---------|-------------|---------|
| 架构 | 三 agent 编排 | 单 agent loop | **保持不变**，但引入 evaluator 作为工具 |
| 上下文管理 | Context Reset | Compaction + Evicted Context | 增加**健康监控**，按需 reset |
| 质量保障 | 外部 Evaluator | VLM Feedback Loop | **扩展评估能力**到更多场景 |
| 任务分解 | Sprint + Contract | Knowledge Workflow | 增加 Skill **验收标准** |
| 持续优化 | 模型升级时简化 harness | Phase 制度 | 增加**脚手架审计**检查项 |

> [!TIP]
> 文章最有价值的一句话：*"The space of interesting harness combinations doesn't shrink as models improve. Instead, it moves."* — 好的 agent 架构不是静态的，而是随模型能力边界的移动而持续演化的。这与我们的 Phase 迭代哲学完全契合。
