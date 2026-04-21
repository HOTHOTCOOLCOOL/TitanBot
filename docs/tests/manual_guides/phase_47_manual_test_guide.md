# Phase 47 专项人工测试指南 (论文分析架构决策与演进评级)

本指南详述了针对 Phase 47（前沿 AI Agent 论文架构适用性分析）的验收方法。虽然这是一个纯理论与架构审计的 Phase，但按照本项目的严格守则，必须通过人工回溯手段，检验“理论分析”与“代码现实”是否存在割裂，确保我们的架构护城河没有被夸大或漏判。

## 测试前置条件
1. 确保你有项目的访问权限。
2. 确保你可以查阅 `docs/adr/ADR-47-paper-analysis-harness.md` 以及核心代码文件。

---

## Part 1: Harness 辩证结果完备性审计

### 验证指标
验证 5 阶辩证（Claude Sonnet → Claude Opus → Gemini High → Gemini Low → Claude Sonnet）的输出是否已被妥善存入 ADR 体系，且并未发生逻辑冲突。

### 操作步骤
1. 打开 `docs/adr/ADR-47-paper-analysis-harness.md`。
2. 核对决议中是否明确涵盖了针对 《SkillClaw》《MIA》《Externalization》及《BubbleRAG》四篇论文的 **接受/降维采纳/拒绝** 结论。
3. **期望结果**：结论清晰，且明确指出了拒绝 MIA（全量 Trace 注入破坏 8k token 铁律）、拒绝 BubbleRAG 图数据库（违反 zero-extra-infrastructure 铁律）的红线边界。

---

## Part 2: 意外发现(代码级防御)的实地测量

### 验证指标
在 Phase 47 期间，模型自发审计代码时声明了“系统已经独立演化出了 BubbleRAG 的 Coverage Penalty 与 Schema Relaxation”。作为人类管理员，我们绝不允许“模型的幻觉审计”被直接确认为架构真理，必须通过人工查阅代码（Code Walkthrough）实地打假。

### 操作步骤
1. 在 IDE 中打开 `nanobot/knowledge_graph.py`。
2. 定位到 `get_entity_context()` 函数内部（约在 L632 - L650 附近）。
3. 查找“Coverage Penalty”护城河：
   - 是否存在对 Anchor 命中率的乘法衰减算法（例如计算已覆盖率并按比例降低评分）？
4. 查找“Schema Relaxation”护城河：
   - 是否存在针对 `score=0` 的边缘实体，依靠 `prefetch_rag` （或 Chunk Preview）进行基于共现关系的“松弛升分”？
5. **期望结果**：两段逻辑结结实实地存在于主干代码中，且逻辑自洽。这证明了 Phase 47 的架构扫描不存在幻觉。

---

## Part 3: 下游转化链路验收 (Tracing The Downstream)

### 验证指标
架构决议不能只停留在纸面（PPT 架构师行为），必须要验证已被拆解为可落地的代码 Phase。

### 操作步骤
1. 翻阅项目的演进报告或文件库。
2. 验证是否由于 Phase 47 的指引，衍生出了对应的落地任务：
   - **检查 46A**：是否存在针对 BubbleRAG 尾部降维采纳所对应的 `Fallback-Driven Query Expansion` 的实现（对应 `knowledge_workflow.py` 的重构）？
   - **检查 46B**：是否存在针对 SkillClaw 降维采纳所对应的 `Offline Experience Consolidator`？（能否在 `jobs.json` 和沙箱架构里看到对离线 Trace 的提取与分析）。
3. **期望结果**：上下游阶段完美闭环，论文的理论价值已被 100% 压榨为工程资产。

---

## 🛑 审计复盘
这是一次典型的反“形式主义”测试。即便是一个不出代码的 Research 任务，我们也要求人类通过追踪它引申出的 ADR、代码护栏（L632）和下游交付物（Phase 46A/B），来证实该 Phase 不是模型水报告的产物，而是刻在系统深处的架构灵魂验证。
