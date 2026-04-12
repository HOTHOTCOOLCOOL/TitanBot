# ADR-49: In-Flight Context Condensation (IFCC) Protocol

**状态 (Status)**: Accepted  
**日期 (Date)**: 2026-04-12  
**决策者 (Deciders)**: Harness 5-Stage Dialectic (Claude Sonnet → Claude Opus → Gemini Pro High → Gemini Pro Low → Claude Sonnet)  
**源论文 (Source Paper)**: MemPO — Self-Memory Policy Optimization (arXiv 2603.00680v3)  
**相关 ADR**: ADR-47 (Paper Analysis Harness — BubbleRAG/SkillClaw)

---

## 背景与动机 (Context)

Nanobot 在密集工具调用场景（SSRS 多轮失败重试、复杂 RPA 错误恢复）中，Agent 历史日志以 O(n) 方式填满上下文窗口，触发 `context.py` 的 120K char 硬截断。该截断为"盲截"，关键的中间推理结论与根因诊断会随冗长的报错栈一同被丢弃，导致 Agent 陷入"遗忘循环 (Amnesia Loop)"。

MemPO 论文提出训练模型主动产出 `<mem>` 标签来压缩上下文，但其核心机制依赖 RL 微调（GRPO）——与 Nanobot 的"API 驱动、免微调"原则根本冲突。

**本 ADR 采用的策略是**：借鉴 `<mem>` 标签的形式信号，通过纯工程手段（System Prompt + 解析管道 + 截断优化）实现语义等价的上下文凝缩效果，**完全不依赖模型训练**。

---

## 决策 (Decision)

实施 **In-Flight Context Condensation (IFCC)** 协议，核心原则如下：

1. **非对称收益**: 遵从率不需要 100%。短对话中零成本（从不触发降级路径）；长灾难性序列中每次触发即可挽救崩溃上下文。
2. **消息内聚而非全局状态**: `milestone_summary` 作为原生字段融入现有 `Message` 数据结构，不引入新的独立记忆通道。
3. **与截断池融合**: Milestone 骨架通过 `_trim_history()` 的条件降级逻辑自然流转，而非独立的滚动窗口 (FIFO)。
4. **安全隔离**: 解析器严格 role-gate，仅处理 `role='assistant'` 输出，从物理上阻断用户/工具伪造 `<mem>` 的 Prompt Injection 攻击向量。

---

## 辩证历程摘要 (Dialectic Summary)

### 被拒绝的 Draft V1 设计
- ❌ 独立 `mem_snapshots: list` 挂在 Session 上（架构孤岛）
- ❌ `hasattr` monkey-patching（反模式）
- ❌ FIFO=5 滑动窗口（转移而非解决"Lost in Middle"）
- ❌ 未对 User/Tool 输入做安全隔离（Prompt Injection 漏洞）

### 采纳的 Extreme Critic 批判 (Claude Opus)
| 批判 ID | 问题 | V2 解决方案 |
|---------|------|------------|
| C2 | Prompt Injection via 伪造 `<mem>` | 严格 role-gate：仅解析 `assistant` 输出 |
| C3 | 与 `<think>` 标签管道互斥 | 强制调用顺序 `strip_think_tags()` → `extract_mem_content()` |
| C4 | 第 8 层记忆孤岛 | `milestone_summary` 作为 `Message` 原生字段 |
| C5 | `hasattr` anti-pattern | 正式扩展 `Message` TypedDict |
| C6 | FIFO=5 仅转移问题 | 依附 `_trim_history()` 截断逻辑，随消息生命周期自然流转 |
| C8 | Regex 鲁棒性不足 | `finditer` 多段提取，容忍未闭合标签，500 chars 硬截断 |
| C9 | 无失效机制 | 随 Session 清理自然老化，无需独立 TTL |

### 明确拒绝的过度批判
| 批判 ID | 拒绝理由 |
|---------|---------|
| C1 (全盘否定) | 非对称收益逻辑：遵从率低不等于 ROI 为零 |
| C7 (Token 成本) | V2 System Prompt 指导段 ~45 tokens，短对话降级路径永远不触发 |
| C10 (P1 推迟) | 上下文溢出是运行时生死问题，优先级高于 P2 流程质量优化 |

### 蓝方评审采纳的微调 (Gemini Pro Low)
1. 多段 `<mem>` 用 `" | "` 拼接（而非取最后一段）
2. 500 chars 硬截断单条 milestone（防模型写巨型备忘）
3. Checkpoint 降级消息使用 `role: assistant` 而非 `role: system`（LiteLLM 角色解析兼容性）

---

## 技术实施规格 (Technical Specification)

### 受影响文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `nanobot/session/models.py` | 修改 | 为 `Message` TypedDict 新增 `milestone_summary: str \| None` |
| `nanobot/agent/tag_extractor.py` | 新建 | IFCC 解析器，role-gated，多段，500 chars 截断 |
| `nanobot/agent/loop.py` | 修改 | `_execute_with_llm()` 管道扩展：接入 IFCC 提取 |
| `nanobot/agent/context.py` | 修改 | `_trim_history()` 条件降级逻辑 |
| `nanobot/config/schema.py` | 修改 | `MemoryFeaturesConfig` 新增 `ifcc_enabled: bool = True` |
| `tests/test_phase49_ifcc.py` | 新建 | 10 用例覆盖全路径 |

### 核心数据流

```
LLM Raw Response
       │
       ▼
strip_think_tags()          ← 现有逻辑
       │
       ▼
extract_mem_content()       ← [IFCC] role='assistant' 专属
  ├─ clean_text              → 最终发送给用户的回复
  └─ milestone_summary       → 写入 Message['milestone_summary']
       │
       ▼
Session.append(Message)     ← milestone_summary 随消息持久化
       │ (未来的 _trim_history 触发时)
       ▼
_trim_history() 降级判断
  ├─ 有 milestone_summary？ → 降级为 [assistant] "（上下文已压缩）{milestone}"
  └─ 无 milestone_summary？ → 原逻辑丢弃
```

### 配置示例

```json
{
  "agents": {
    "memory_features": {
      "evicted_context": true,
      "cls_consolidation": true,
      "time_decay": true,
      "metacognitive_reflection": true,
      "ifcc_enabled": true
    }
  }
}
```

### System Prompt 引导段（~45 tokens）

```
## Context Condensation
When you have definitively resolved a step (confirmed root cause, completed analysis),
summarize the key finding in <mem>concise conclusion ≤200 chars</mem>.
Place it AFTER any <think> block. This milestone survives context truncation.
```

---

## 测试计划 (Test Plan)

`tests/test_phase49_ifcc.py` — 共 10 个用例：

| # | 场景 | 验证点 |
|---|------|--------|
| T1 | 单段 `<mem>` 正常提取 | summary 和 clean_text 均正确 |
| T2 | 多段 `<mem>` 拼接 | `" \| "` 拼接，总长 ≤500 chars |
| T3 | 未闭合标签容忍 | 不崩溃，尽力提取已有内容 |
| T4 | 无 `<mem>` passthrough | 返回 (original_text, None) |
| T5 | 超长 `<mem>` 硬截断 | 单段截断为 500 chars |
| T6 | 嵌套标签边界 | 不崩溃，返回可接受结果 |
| T7 | `ifcc_enabled=False` 全路径跳过 | `extract_mem_content` 不被调用 |
| T8 | `_trim_history` 有 milestone 降级 | skeleton 消息格式正确，role='assistant' |
| T9 | `_trim_history` 无 milestone User 消息 | 直接丢弃 |
| T10 | `Message` JSONL 序列化/反序列化 | `milestone_summary` 字段完整保留 |

---

## 预估工作量 (Effort Estimate)

**总计**: ~7.5 小时（1.5 工作日）

| 文件 | 时长 |
|------|------|
| `models.py` 字段扩展 + 序列化 | 0.5h |
| `tag_extractor.py` 新建 | 1h |
| `loop.py` 管道接入 | 1.5h |
| `context.py` 降级逻辑 | 2h |
| `schema.py` + System Prompt | 0.5h |
| 测试套件（10 用例） | 2h |

---

## 后续注意事项 (Follow-up)

1. **实验性指标收集**: 上线后通过 `/stats` 监控 `mem_tag_triggered` 事件频率，建立 Baseline。若 30 天内触发率 < 0.1%，需重新评估 System Prompt 引导效果。
2. **P2 Agent-as-Reviewer**: 本 ADR 不涵盖。待 Phase 49 IFCC 稳定后，独立开启 Harness 评审。
3. **论文引用更新**: 完成实施后，`progress_report.md` 和 `archive/PROJECT_STATUS.md` 中的论文参考表需增加 MemPO 条目（第 12 篇）。
