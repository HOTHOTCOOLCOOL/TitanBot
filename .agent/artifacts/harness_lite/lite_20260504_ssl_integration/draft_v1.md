# Draft V1: SSL Scheduling Layer & Normalizer Integration

## 1. 方案摘要 (Summary)

基于论文《From Skill Text to Skill Structure: The SSL Representation for Agent Skills》中的发现，设计一套机制来改善 Nanobot 的工具和技能发现能力：

1. **标准化工具元数据 (Capability Card Schema)**：借鉴 SSL 论文的 Scheduling Layer，定义一个新的轻量级 JSON schema，包含三个核心字段：`goal`（设计目标），`input_schema`（输入依赖），`output_schema`（输出形态）。
2. **KnowledgeMapTool 升级**：将这个 Capability Card 作为 metadata 附加到 Knowledge Graph 中的工具/技能实体上。当 `KnowledgeMapTool` 检索到相关工具时，不再返回模糊的描述，而是返回严格格式化的 Capability Card。
3. **轻量级提取器 (LLM Normalizer Pipeline)**：提供一个类似 `scripts/extract_capability_card.py` 的独立辅助脚本，负责读取现有的冗长文档或 `TOOLS.md` 条目，并请求 LLM 总结出符合上述 Schema 的 JSON 卡片，便于将其批量灌入 KG 供运行时检索。

## 2. 关键 Trade-off

- **精准路由 vs. 预算消耗**：附加标准化的 JSON Schema 到 KG 查询返回结果中，虽然大幅提升了路由的精准度，但每次检索返回的 Token 数量会上升。
- **静态注入 vs. 运行时检索**：我们不在 `context.py` 的 system prompt 中静态注入所有的 Capability Card（因为 19 个工具会直接把预算爆掉），而是保持当前架构，依赖 `KnowledgeMapTool` 的拓扑查询懒加载这些卡片。

## 3. 风险与假设

- **假设 1**：现存的 `KnowledgeMapTool` 已经实现了 KG 的实体挂载功能，可以直接把新字典结构塞进 node 的 attributes 中，而不会破坏已有的 GraphML 序列化。
- **假设 2**：`KnowledgeMapTool` 的字符截断机制可以像 Phase 65 中的 reasoning template 一样有效地控制长文本爆炸。

## 4. False Positive Success Paths (假阳性盲区)

- **情景 A：LLM “假装”使用了结构化数据**：由于底层 LLM 极其智能，可能在没有任何结构化注入的情况下，仅凭 `TOOLS.md` 或少量的描述名字就能猜出工具怎么用。这时我们看到任务成功，可能误以为是 Capability Card 起效了，但实际上机制可能根本没触发（例如：卡片生成失败被吞掉，或者在 KG 查找时被全截断了）。
  - *应对方案*：必须要有硬日志证明：`L0: Capability Card [XXX] loaded from KG`，并检查 prompt dump 里面是否真的存在格式化的 JSON schema。

## 5. 仍待验证的点

- `knowledge_map.py` 内部 `_MAP_OUTPUT_CAP` 是否足够容纳 3-5 个带有 Capability Card 的节点信息。
- 如果将 JSON 序列化并硬塞给 LLM 作为上下文，是否会与我们 Phase 62 追求的 "Content/Schema Null Compliance" 原则发生歧义？（例如，工具调用层面的 Schema 和 我们仅作为知识灌输的 Schema 之间的语义碰撞）。
