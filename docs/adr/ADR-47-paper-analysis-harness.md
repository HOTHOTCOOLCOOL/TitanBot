# ADR-47：论文分析架构决策备忘录 (Harness 5阶辩证定稿)

**日期**：2026-04-12  
**状态**：已接受 (Accepted)  
**辩证模型接力**：Claude Sonnet → Claude Opus → Gemini High → Gemini Low → Claude Sonnet  
**触发事件**：对三篇 AI Agent 论文（SkillClaw、MIA、Externalization）及 BubbleRAG 进行架构适用性分析

---

## 背景

Phase 38A/38B 完成后，系统进入架构稳定期。趁此时机对近期四篇 AI Agent 领域论文进行系统性分析，评估其核心技术对 Nanobot 的适用性，并通过 5 阶 Harness 辩证工作流对初始分析结论进行严格批判与重构。

涉及论文：

| 论文 | 核心主张 |
|------|---------|
| SkillClaw (Ding et al., 2026) | 基于执行 Trace 自动进化和验证 Agent Skill |
| MIA (Memory Intelligence Agent) | 将历史 CoT 轨迹注入 Planner 的 few-shot 上下文 |
| Externalization of LLM Agent | 将 Memory、Skills、Protocols 从模型权重外化为可检查结构 |
| BubbleRAG (HKUST-GZ) | 用 Bubble Expansion 算法解决黑盒知识图谱的多跳检索问题 |

---

## 决策

### A. 永久保留的核心设计（坚守决策）

以下是经 5 阶辩证确认正确、不应改变的现有架构设计：

| 设计 | 决策依据 |
|------|---------|
| **Hybrid Retrieval 快路径（亚秒级）** | BubbleRAG 的端到端延迟 ~21s/query，Nanobot 的 Exact→Substring→BM25→Dense 渐进回退链更优，且专为小规模个人 KG 优化 |
| **TraceArchive 纯 append-only 设计** | 不引入 runtime 查询接口，符合"零 runtime 污染"原则（ADR-46 已确认） |
| **Offline Bridging Facts（P29-3）** | 比 BubbleRAG 的 runtime Bubble Expansion 更适合个人 Agent：索引时预计算，查询时零延迟 |
| **knowledge_graph.py Phase 34 Coverage Penalty & Schema Relaxation** | 代码审查发现 `get_entity_context()` L632-L650 **已实现** Coverage Penalty 和 Schema Relaxation。BubbleRAG 的对应灵感**已落地**，无需额外工作 |
| **Experience Bank Directive Signal（P29-1）** | 已实现 `extract_and_save_directive()` 的失败反馈→战术提示注入管道，MIA 论文的 "former failed traces as few-shot examples" 本质上与此重叠 |
| **7 层分层记忆体系（L1-L7）/ 8000 Token 注入上限** | MIA 建议将 2-3 条 Trace 全量注入 Planner 上下文，但单条 Trace 可达 2000+ chars，无法在 8000 chars 铁律下共存 |
| **CapabilityTag L1 安全拦截（Phase 45）** | Externalization 论文充分论证了"可检查的外部化协议比模型内部能力更可靠"——Nanobot 的标签驱动拦截是这一理论的最佳实践实现 |

### B. 采纳的关键批评与重构建议（改变决策）

| 被否决的 Draft V1 方向 | Opus 关键批判 | 最终修正方向 |
|----------------------|-------------|------------|
| SkillClaw 全自动 Skill 代码进化闭环 | TraceArchive 无 status 字段；Phase 45 是 L1 标签拦截器不是可执行沙箱；Nanobot Skill 是自然语言文档不是可测试代码 | 降维为**离线经验整编器**：利用 Cron + SubAgent 归因失败 Trace，生成 Directive Signal 文本存入 Experience Bank |
| BubbleRAG 隐式概念查询前置 LLM 调用 | 违反 ARCHITECTURE.md 确定性优先原则；每次 KG 查询增加 >600ms；破坏 Phase 39 极速路由 | **后置到 Fallback 最末端**：仅当所有回退层均 Zero Match 时触发，主路径不受影响 |
| MIA 失败 Trace Few-Shot 注入 | 与 Phase 29-1 Directive Signal 高度重叠；8000 Token 铁律严重不适 | **放弃采纳** |
| BubbleRAG CEG Ranking Coverage Penalty | `hybrid_retrieve()` 单维字符串接口不支持多概念评分基础 | **放弃采纳**；`knowledge_graph.py` Phase 34 已有类似机制 |

### C. 最终实施路径

#### Phase 46A (P0)：Fallback-Driven Query Expansion（最末端语义扩展）

- **灵感来源**：BubbleRAG §3.2 Semantic Anchor Grouping（降维实现）
- **触发条件**：`knowledge_workflow.py` `match_knowledge()` 的 Exact/Substring/Hybrid 三层全部返回 `None`
- **实施方式**：复用 `workflow_models.key_extraction` 的轻量模型路由，推断查询中的隐式概念词，展开为 1-3 个备选词，对每个词发起静默第二次 `hybrid_retrieve()`，取最高分结果
- **安全门**：`timeout=3.0s` 熔断保护；超时静默失败，维持原始 Zero Match 结果
- **量化预期**：P50 延迟不变；P95 长尾增加约 1.5s；挽回约 30% 因隐式概念未命中的语义失败
- **改动范围**：仅修改 `knowledge_workflow.py` `match_knowledge()` +30 行，无新依赖

#### Phase 46B (P1)：Offline Experience Consolidator（离线经验整编器）

- **灵感来源**：SkillClaw §3 空闲期自动归因（降维：代码进化 → 经验文本增殖）
- **实施位置**：Phase 44 Cron 引擎新增每日低谷时段（如 03:00）CronJob
- **实施方式**：
  1. Cron 触发 `SubagentManager.spawn()` 派发分析任务
  2. Worker 遍历 `TraceArchive` 最近 N 个 JSON，启发式识别失败 Trace（`final_content` 以 `Error:` 开头 或 `tool_chain` 末端含 `outcome: failed`）
  3. 对失败 Trace 调用 LLM 归因，产出 `{trigger, prompt}` Directive Signal
  4. 通过 `add_experience()` 存入 Experience Bank，附加 `[Auto-Generated]` 标签供人工审查
- **安全门**：产出为纯文本，**零代码执行风险**；不修改任何 Skill 目录文件
- **量化预期**：每日自动追加约 2-5 条战术规则；随运行时间增长，错误字典自动增厚
- **改动范围**：`jobs.json` 新增 1 个 cron_job；SubAgent 归因逻辑 +60 行

### D. 明确拒绝的借鉴方向

| 被拒绝项 | 拒绝原因 |
|---------|---------|
| BubbleRAG Bubble Expansion 图算法 | 需引入图数据库（Neo4j），违反"零额外架构"原则；500 三元组个人 KG 不是黑盒 KG 场景 |
| SkillClaw 全自动代码层 Skill Merge | Nanobot Skill 是自然语言文档；HITL 无法防御嵌入式 Prompt Injection |
| MIA 全量 Trace 注入 Planner | 8000 Token 上下文铁律不兼容；Phase 29-1 已覆盖 |
| BubbleRAG CEG Ranking Coverage Penalty | `hybrid_retrieve` 单维接口不支持；Phase 34 已有类似实现 |

---

## 意外发现（代码审查红利）

Opus 阶段的代码级批判驱动了深层代码审查，发现两个已在代码中独立实现、但在初始论文对比分析中被忽略的机制：

1. **Coverage Penalty（`knowledge_graph.py` L632-L641）**：`get_entity_context()` 已用 anchor 覆盖率对实体评分实施乘法惩罚，与 BubbleRAG CEG Ranking 核心思想高度一致，但更简洁且不依赖图数据库。

2. **Schema Relaxation（`knowledge_graph.py` L644-L650）**：已用 `prefetch_rag` 向量预取结果作为 "Community Preview"，对 score=0 的实体进行基于共现的"松弛升分"，与 BubbleRAG Schema Relaxation via Chunk Preview 精准对应。

> **结论**：Nanobot 的 KG 子系统已独立推演出与 BubbleRAG 论文相近的两个核心思路。

---

## 论文最终价值判定

| 论文 | 判定 | 结论 |
|------|------|------|
| **Externalization of LLM Agent** | ✅ 完全验证 | Nanobot 已完整实践，无需新工作 |
| **BubbleRAG** | ✅ 部分借鉴 | Phase 34 已有核心思路 + Phase 46A 低侵入尾部扩展；核心算法不适用 |
| **SkillClaw** | ⚠️ 降维借鉴 | 代码 Skill 自动进化 → 经验文本自动整编（Phase 46B）；全自动 Merge 不适用 |
| **MIA** | ❌ 放弃采纳 | 全量 Trace 注入不兼容；Phase 29-1 Directive Signal 已覆盖相应价值 |

---

## 后续影响

- `knowledge_workflow.py` 的 `match_knowledge()` 将在 Phase 46A 中增加后置语义扩展逻辑
- `jobs.json` 将在 Phase 46B 中新增 `daily_experience_consolidation` 定时任务
- `docs/architecture_harness_baseline.md` 对应 KG 子系统小节补充 Phase 34 代码审查发现
