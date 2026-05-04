# Review Packet

## Scope

- 本次只读取了：
  - `problem_statement.md`
  - `baseline.md`
  - `draft_v1.md`
  - `nanobot/agent/tools/knowledge_map.py`
  - `TOOLS.md`
  - `nanobot/agent/context.py`
- 未读取 `.agent/artifacts/paper_analysis_report.md`。按本次 launcher 约束，它不在允许读取范围内。
- `draft_v1.md` 点名的 `scripts/extract_capability_card.py` 当前不存在。

## Findings

1. **[High] 主集成路径和当前实现不一致。**
   `draft_v1.md` 把核心方案写成“把 Capability Card 挂到 KG 实体上，然后由 `KnowledgeMapTool` 返回结构化卡片”。但当前 `KnowledgeMapTool` 只盯 `memory/graph.json`，只读取 `triples`，只计算 degree/adjacency，然后拼出编号文本列表并做 3000 字截断；它没有读取节点 attributes、没有读取 Capability Card JSON、没有读取 `TOOLS.md`，也没有读取任何 normalizer 输出。这里不是“小改一下返回字段”，而是数据源、输出契约、缓存逻辑三件事一起改。  
   证据：`nanobot/agent/tools/knowledge_map.py:84-108,113-149`；`TOOLS.md:217-225`

2. **[High] 预算路径被混写了，当前代码里没有现成的 Capability Card 预算闭环。**
   `draft_v1.md` 和 `baseline.md` 把三条不同路径混在了一起：
   - `KnowledgeMapTool` 自己的 3000 字输出上限；
   - `ToolRegistry` 的 50000 字全局工具输出上限；
   - `context.py` 里对 `reasoning_template` 的 1000 字截断和 KG/system prompt 注入。
   当前 `context.py` 只会在 `entry.type == "reasoning_template"` 时截断 `summary`，并把 KG context 直接拼进 system prompt；它没有任何“Capability Card 专用预算”或“KnowledgeMapTool 返回卡片后再做预算治理”的逻辑。`draft_v1.md` 里“像 Phase 65 一样控制长文本”的说法，目前没有代码证据支撑。  
   证据：`nanobot/agent/context.py:27-28,147-159,449-459`；`nanobot/agent/tools/knowledge_map.py:24,149`；`TOOLS.md:17-21,225`

3. **[High] source of truth 和缓存失配没有解。**
   `problem_statement.md`/`baseline.md`/`draft_v1.md` 在“Capability Card 挂到 KG 节点”与“挂到 `TOOLS.md`/从文档抽取”之间来回切，但没有钉死唯一权威来源。当前 `KnowledgeMapTool` 的缓存只跟 `memory/graph.json` 的 mtime 绑定。如果卡片实际落在 `TOOLS.md`、sidecar JSON、或 normalizer 产物里，现有缓存不会因为这些文件变化而失效。即使功能做出来，也很容易出现“数据改了但查询结果没变”的假阳性。  
   证据：`nanobot/agent/tools/knowledge_map.py:84-86,98,104-105,152-153`

4. **[Medium] 问题定义写得过满。**
   `baseline.md` 把“Nanobot tools lack a standardized capability card with precise inputs, outputs, and invocation goals”标成 VERIFIED，但允许读取的 repo 证据只支持更弱的版本：当前工具层已经有参数 JSON Schema，`TOOLS.md` 也明确把“Structured, parseable output (JSON preferred)”列为审计标准，多个工具已经输出结构化 JSON。当前真正缺的是“统一的、可检索的 Scheduling Layer 卡片”，不是“系统里完全没有结构化输入/输出定义”。如果问题定义不收窄，后面很容易叠出第二套 schema。  
   证据：`nanobot/agent/tools/knowledge_map.py:76-79`；`TOOLS.md:11,44,108,205`

5. **[Medium] 假阳性分析只打到一半。**
   `draft_v1.md` 只写了“模型可能没加载卡片也能猜对工具用途”，这是一个假阳性路径；但没有打第二条更危险的路径：normalizer 生成了错误卡片，但 JSON 形状看起来很规范，评审和 demo 都会把它当成“结构化成功”。当前草案没有定义任何可追溯证据，来区分“卡片是真的来自源文档”还是“卡片只是 LLM 编得像真的”。这会直接影响 P2 是否能自动灌入 KG。  
   证据：`draft_v1.md` 的 False Positive 只覆盖“未加载也猜对”，未覆盖“加载了错误卡片还看起来正确”

6. **[Medium] 关键论据在本会话里不可审，不能当已验证事实使用。**
   `baseline.md` 把“论文证明 Scheduling Layer 明显提升 MRR”标成 VERIFIED，但引用的是 `.agent/artifacts/paper_analysis_report.md`，本次 Critic 会话按 launcher 不允许读取它，所以这里不能独立复核。`draft_v1.md` 还把 `scripts/extract_capability_card.py` 当成类比对象，但该文件当前不存在。结论：这些点可以作为作者动机，不能作为本轮 review 的 repo-level 已验证事实。  
   证据：`baseline.md` 的 `Claim / Evidence / Status`；`draft_v1.md` 点名脚本；repo 中该脚本缺失

## Must Keep

- 保留“不把所有卡片静态塞进 system prompt，而是走按需检索”的方向。当前 `KnowledgeMapTool` 的价值本来就是零常驻开销；这一点不要丢。
- 保留“必须看硬信号，不能因为回答像对就算机制生效”的要求。`draft_v1.md` 里要求日志 / prompt dump / 返回载荷里真的出现结构化卡片，这一条是对的。
- 保留把 Execution / Security 层排除出本轮范围的边界。当前任务是 Scheduling Layer 元数据，不是 Phase 64 隔离机制改造。

## Weak Claims / Unverified Claims

- “`KnowledgeMapTool` 已经支持把新字典结构挂进 node attributes，且不会破坏 GraphML 序列化。”  
  允许读取的代码里没有证据。

- “现有字符截断机制可以像 Phase 65 reasoning template 一样治理 Capability Card。”  
  允许读取的代码里只看到对 `reasoning_template` 的专门截断，没有通用卡片预算。

- “`TOOLS.md` 主要还是自然语言描述，所以缺少精确结构。”  
  现有证据最多支持“缺少统一的 Scheduling Layer 卡片”，不支持“一般性缺少结构”。

- “论文对本 repo 场景的收益已经被验证。”  
  本会话无法复核引用的 paper artifact。

- “`scripts/extract_capability_card.py` 可作为现成参考物。”  
  当前文件不存在。

- “normalizer 幻觉最多只是略微降低检索效果，不会影响更大范围行为。”  
  草案没有给出证据。

## False Positive Risks

- Capability Card 根本没被加载，模型仍然靠工具名、描述文本和已有先验把任务做对，导致演示看起来“方案生效”。
- Capability Card 实际保存在 `TOOLS.md` 或 sidecar 文件里，但 `KnowledgeMapTool` 仍然只读 `memory/graph.json` 且命中旧缓存，结果看起来稳定，实则新机制完全未接线。
- 卡片通过 KG context / tool output 某一路进入上下文后被截断或半截注入，结果仍然像结构化信息，但关键字段缺失或破碎。
- normalizer 输出了看起来很整齐的 JSON，但字段内容脱离源文档；因为“长得像 schema”，评审误判为高质量抽取。
- 评估只看“最终任务成功”，不看日志、返回 payload、prompt dump 中是否真的出现 Capability Card，导致无法区分“机制触发”与“模型自己猜对”。

## Acceptance Checklist

| A# | Claim | Evidence Method | Proof Signal | Expected Result | If Fail |
| :--- | :--- | :--- | :--- | :--- | :--- |
| A1 | `KnowledgeMapTool` 确实从选定的唯一权威来源读取 Capability Card | 选一个工具，改动其卡片数据，再执行一次真实查询 | 查询结果中出现改动后的卡片字段；并能指明读取来源 | 输出变化与权威来源变化一一对应 | 还不能声称主集成路径已打通 |
| A2 | 卡片数据的缓存失效规则与权威来源一致 | 只改权威来源文件，不改无关文件，连续查询前后结果 | 缓存 miss / reload 的硬信号，或结果立即更新 | 不需要碰无关文件也能看到新卡片 | 说明缓存和数据源脱节 |
| A3 | 最坏情况下的卡片载荷仍在真实传输路径预算内 | 用 3-5 个代表性大卡片跑一次真实路径（tool output 或 KG/system prompt 注入） | 实际字符数、截断标记、载荷完整性 | 无 silent truncation；关键字段完整可读 | 当前卡片尺寸/数量或传输路径不成立 |
| A4 | 新卡片层不会和现有工具 schema / 描述层打架 | 选一个现有工具，对比 `parameters`、描述文本、提议卡片字段 | 一一映射后的字段语义一致 | 不出现两套互相矛盾的 input/output 定义 | 新层会制造 schema 冲突 |
| A5 | 评估能区分“机制生效”与“模型自己猜对” | 做一次 ablation：禁用/断开卡片路径，再跑同类查询对照 | 日志、payload、prompt dump 能明确显示有无卡片载入 | 成功与否能归因到卡片路径，而不是模型先验 | 假阳性路径未被打掉 |
| A6 | normalizer 产出的字段可被追溯并达到可用精度 | 取若干 README / `TOOLS.md` 条目做样本，对照源文本逐字段核对 | 每个字段都能指出来源片段或人工核对结果 | 抽取结果可审计，错误率在可接受范围内 | 不能直接自动灌入 KG |
| A7 | 系统最终只保留一条明确的运行时接线路径 | 明确验证“走 `KnowledgeMapTool` 返回”还是“走 KG context 注入”，不要两条都算 | 单一路径的日志、预算、输出形态都可复现 | 运行时路径可解释、可测量 | 结果不可解释，Evidence Gate 无法成立 |
