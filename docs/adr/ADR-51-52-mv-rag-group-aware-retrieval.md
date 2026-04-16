# ADR-51/52: K-V 解耦索引 & Group-Aware 并发推理

**状态 (Status)**: Accepted  
**日期 (Date)**: 2026-04-12  
**决策者 (Deciders)**: Harness 5-Stage Dialectic (Claude Sonnet → Claude Opus → Gemini Pro High → Gemini Pro Low → Claude Sonnet)  
**源论文 (Source Papers)**:
- M-RAG: Making RAG Faster, Stronger, and More Efficient (arXiv 2603.26667v1)
- GroupRAG: Cognitively Inspired Group-Aware Retrieval and Reasoning (arXiv 2603.26807v1)
- SkillX: Automatically Constructing Skill Knowledge Bases for Agents (arXiv 2604.04804v1)  

**相关 ADR**: ADR-47 (Paper Analysis Harness), ADR-49 (IFCC), ADR-50 (KG-Wiki)

---

## 背景与动机 (Context)

通过 Harness 辩证分析对三篇论文的评估（详见 `paper_analysis_report.md`）：

- **M-RAG** 指出传统文本 Chunking 存在根本性的粒度错配：检索的匹配特征（Retrieval Key）与注入给 LLM 的生成上下文（Generation Value）被强制绑定在同一段落块中，导致检索噪声放大。
- **GroupRAG** 指出对于高复杂度的多信息点任务，单线程 Chain-of-Thought 推理存在遗漏率高的问题，提出"分散→收敛"的并发推理拓扑（Convergent Reasoning Net）。
- **SkillX** 的核心贡献（三级技能层次 + 主动探索）已被明确评估为**不适合 Nanobot 架构**（详见"明确否决"部分）。

Nanobot 当前（Phase 48）的检索管线使用 Dense + BM25 混合检索，但索引单元为传统 Chunking，存在：
1. `attachment_analyzer.py` 解析长文后暴力拆块，破坏语义边界。
2. 高复杂度任务（如"对比三篇论文"）依赖单线程 CoT，易产生上下文衰减。

---

## 核心决策 (Decision)

### Phase 51：K-V 解耦索引 (M-RAG Pattern)

将向量索引的**匹配键（Retrieval Key）**与**注入值（Generation Value）**显式解耦。

**关键约束**：
1. `MetaMarker` 提取为 **Lazy Opt-in 旁路**，不替换默认 Chunking 主路径。
2. 提取结果按 `sha256(file_content + prompt_version)` 哈希缓存，保证确定性与可复现性。
3. `BM25` 索引锚定在完整 `value`（词频保全），`Dense` 索引锚定在短句 `key`（意图精准匹配）。
4. 默认 `config.features.marker_indexing = false`，主路径 P50 延迟零影响。

### Phase 52：Group-Aware 并发推理 (GroupRAG Pattern)

在 Phase 38B `SubagentManager` 基础上，为高复杂度任务开启分组并发推理。

**关键约束**：
1. 触发判定器为**纯确定性启发式规则**，零 LLM 调用（满足以下任意 2 条触发）：
   - 输入 Token > ~500（约 2000 chars）
   - L7 KG 本地缓存估算实体数 > 8
   - 用户显式使用 `/parallel` 或 `/deep-analyze`
   - 任务描述包含结构化关键词（"对比"/"分析"/"综合"/"compare"/"analyze"/"summarize"）
2. SubAgent 结论冲突检测基于嵌入余弦距离（阈值 = 0.3），冲突时**阻断自动裁决，触发 HITL 上报**。
3. 默认 `config.features.parallel_reasoning = false`，不影响任何现有功能。

---

## 辩证历程摘要 (Dialectic Summary)

### Draft V1 的原始缺陷（被批判阶段识别）

| 缺陷 | 批判内容 |
|------|---------|
| Marker 提取走主路径 | 每文档触发一次 LLM 调用，50 文档 = 爆炸性成本；违反 deterministic-first 原则 |
| LLM 判定复杂度 | 判定器本身是另一个非确定性黑盒，误判成本和幻觉风险双重叠加 |
| BM25 仅索引 key | 短句词频极度稀疏，BM25 通道实质废弃，5 层检索金字塔缺一层 |
| SubAgent 矛盾无仲裁 | 未定义冲突结论时的裁决机制，盲目 LLM 仲裁引入幻觉风险 |
| 7 层记忆兼容性未交代 | L5（慢路径整合）/ L7（实体图谱）如何兼容 MetaMarker 结构未说明 |
| 实体数统计触发隐式 NER | 可能导致主路径上意外的 LLM NER 调用 |

### 采纳的批判与修复

| 批判 | Draft V2 解法 |
|------|--------------|
| LLM 成本爆炸 | Lazy Opt-in 旁路 + Hash 缓存（纳入 prompt_version 版本因子） |
| 判定器黑盒 | 纯确定性 4 条启发式规则，满足 2 条触发，零 LLM 调用 |
| BM25 失效 | 双索引分离：Dense→key，BM25→value；命中后注入 value |
| 矛盾裁决缺失 | 余弦距离检测冲突，冲突时透明上报并附证据，人类裁决 |
| 7 层记忆兼容性 | 仅在 ChromaDB metadata 新增 `index_type` 字段；L5/L7 不变 |
| 隐式 NER 风险 | 实体计数直接读取 L7 KG 本地缓存，零额外 LLM 调用 |

### 明确拒绝的过度批判

| 批判 | 拒绝理由 |
|------|---------|
| "M-RAG/GroupRAG 不适用于产品场景" | 借鉴的是工程设计模式，非追求特定 Benchmark 分数 |
| "SubAgent 矛盾须用 Policy Gradient 仲裁" | Nanobot 是 HITL 产品，绝大多数场景结论互补而非互斥；硬冲突时用户裁决是正确选择 |

### 明确否决的 SkillX 组件

| 组件 | 否决理由 |
|------|---------|
| 三级技能层次（Planning/Functional/Atomic） | Phase 46B Experience Bank 已满足需求，强制切分带来维护债务 |
| 主动探索式技能扩展（Exploratory Expansion） | LLM 无限制自生成任务的代币成本和沙箱穿越风险不可接受 |

### 蓝方评审锚定的核心设计（必须保留）

1. **双轨混合检索模式**：Dense→key + BM25→value，二者不可合并。
2. **纯确定性触发网络**：零 LLM 判定，4 条规则满足 2 条触发。
3. **HITL 矛盾上报**：冲突时透传证据，拒绝自行 LLM 裁决。
4. **Lazy Opt-in + Hash 缓存**：主路径零染色，Prompt 版本纳入 Hash 因子。

---

## 技术架构规格 (Architecture Spec)

### Phase 51 数据流

```
attachment_analyzer.py (or Cron)
  │
  ├─ [默认] → Chunking → Vector Store (unchanged)
  │
  └─ [--deep or Cron idle] → MarkerExtractor
        ├── Hash Check → .marker_cache/<sha256>.json (命中则复用)
        └── LLM Extraction (zero-shot, universal template)
              ↓
         [MetaMarker(key, value, source_hash, paragraphs)]
              ↓
         vector_store.upsert(
           document=value,               ← Dense 向量化对象
           metadata={
             "index_type": "marker",
             "marker_key": key,          ← BM25 全文索引对象
           }
         )

hybrid_retriever.retrieve(query):
  ├── Dense Search: embed(query) vs embed(key)    ← 精准意图锚定
  ├── BM25 Search: query terms vs value fulltext  ← 词频完整保全
  └── Inject to LLM: value (complete context block)
```

### Phase 52 执行拓扑

```
CoordinatorManager.handle_task(task)
  │
  ├─ ComplexityDetector.should_parallelize(task, ctx)  ← 纯确定性规则
  │     满足 ≥ 2 条: Token>500, Entities>8, /parallel, 结构化关键词
  │
  ├─ [NO] → _standard_cot(task, ctx)  ← 不变，零额外开销
  │
  └─ [YES] → GroupAwareOrchestrator.run_parallel(task)
        ├── _extract_groups(task)  ← prompt 拆分，<500ms，一次 LLM 调用
        ├── asyncio.gather(*[SubagentManager.spawn(g) for g in groups])
        │     每个 SubAgent: RestrictedWorkerToolset(scope="readonly_search")
        └── _converge(local_results)
              ├── embed each conclusion
              ├── pairwise cosine < 0.3? → ⚠️ CONFLICTING_CONCLUSIONS + HITL
              └── else → confidence-weighted merge → global conclusion
```

### 受影响文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `nanobot/agent/marker_extractor.py` | **[NEW]** | MetaMarker 提取器 + Hash 缓存 |
| `nanobot/agent/complexity_detector.py` | **[NEW]** | 纯确定性触发规则（零 LLM） |
| `nanobot/agent/vector_store.py` | 修改 | 新增 `index_type`/`marker_key` metadata 字段 |
| `nanobot/agent/hybrid_retriever.py` | 修改 | 双索引检索：Dense→key，BM25→value |
| `nanobot/agent/subagent.py` | 修改 | 新增 `GroupAwareOrchestrator` |
| `nanobot/agent/commands.py` | 修改 | `/parallel`、`/deep-analyze` 命令路由 |
| `nanobot/config/schema.py` | 修改 | 新增 `marker_indexing: bool = False`、`parallel_reasoning: bool = False` |
| `tests/test_phase51_marker_extractor.py` | **[NEW]** | Hash 缓存、覆盖率、BM25 分数对比 |
| `tests/test_phase52_group_orchestrator.py` | **[NEW]** | 触发规则、矛盾检测、HITL 上报 |

---

## 核心 API 规格

### `MetaMarker` (dataclass)

```python
@dataclass
class MetaMarker:
    key: str            # 浓缩查询意图："生成一个详细问句，同时作为内容摘要和检索锚点"
    value: str          # 富上下文块，200-300 词，覆盖 1-3 个原始段落
    source_hash: str    # sha256(file_content + prompt_version)
    paragraphs: list[int]  # 来源段落索引（0-based）
```

### `GroupResult` (dataclass)

```python
@dataclass
class GroupResult:
    status: Literal["OK", "CONFLICTING_CONCLUSIONS"]
    conclusion: str | None          # status=OK 时有效
    confidence: float | None        # 0.0-1.0，加权平均
    evidence: list[ConflictEvidence]  # status=CONFLICTING 时有效
    requires_human_input: bool
```

### MarkerExtractor 提示模板规范（单一通用版）

```
提取规则：
1. 细粒度分割：每个 meta-marker 覆盖 1-3 个段落，不超过 3 个
2. 代词消解：用显式名称替换代词
3. v（信息块）：200-300 词聚焦段落，单一主题，自洽
4. k（摘要查询）：生成一个详细问句，同时作为内容摘要和检索锚点；
   包含关键实体、日期、数值；足够具体以区分其他内容
5. paragraph_indices：最多 3 个（0-based），必须有重用以保证覆盖率
覆盖率门槛：0.95；失败 3 次后退化为传统 Chunking
```

---

## 配置示例

```json
{
  "features": {
    "marker_indexing": false,
    "marker_prompt_version": "v1",
    "parallel_reasoning": false,
    "parallel_complexity_token_threshold": 500,
    "parallel_complexity_entity_threshold": 8,
    "parallel_conflict_cosine_threshold": 0.3
  }
}
```

---

## 验收标准

| 验收项 | 通过条件 |
|--------|---------|
| 主路径无回归 | `marker_indexing=false` + `parallel_reasoning=false` 时，P50 延迟无变化 |
| Marker 缓存命中 | 同文件第二次调用 `MarkerExtractor.extract()` 命中缓存，零 LLM 调用 |
| BM25 通道有效 | `index_type=marker` 记录的 BM25 分数 ≥ `chunk` 记录的 80% |
| HITL 矛盾上报 | 构造余弦距离 < 0.3 的两个 SubAgent 结论，验证 `CONFLICTING_CONCLUSIONS` 触发 |
| 确定性触发规则 | 4 条规则的各个组合（满足 0/1/2/3/4 条）行为符合预期 |
| 提示版本失效缓存 | 修改 `marker_prompt_version` 后，旧缓存被自动跳过并重新提取 |

---

## 预估工作量 (Effort Estimate)

**总计**: ~5.5 工作日

| Phase | 内容 | 工时 |
|-------|------|------|
| 51A | `marker_extractor.py`：MetaMarker + Hash 缓存 + 覆盖率校验 | 1 天 |
| 51B | `hybrid_retriever.py`：双索引改造 + `vector_store.py` schema 扩展 | 1 天 |
| 51C | 触发入口（`--deep` 参数、Cron 旁路）+ 配置开关 | 0.5 天 |
| 52A | `complexity_detector.py`：4 条确定性规则 + L7 KG 缓存读取 | 0.5 天 |
| 52B | `GroupAwareOrchestrator`：分组派发、余弦冲突检测、HITL 上报 | 1.5 天 |
| 52C | `CoordinatorManager` 集成 + `/parallel` 命令 + 全量回归测试 | 1 天 |

---

## 与 SkillX 的明确边界声明

本实施**有意识地不采用** SkillX 的以下组件：

| SkillX 组件 | Nanobot 的处理方式 | 理由 |
|------------|-----------------|------|
| 三级技能层次（Planning/Functional/Atomic） | 沿用 Phase 46B Experience Bank | 已满足需求；强制三层切分增加维护成本 |
| 主动探索式技能扩展（Exploratory Expansion） | 明确否决 | Token 成本爆炸 + 沙箱穿越风险不可接受 |
| 迭代精炼管线（Iterative Refinement Loop） | 已由 Offline Consolidator（Phase 46B）覆盖 | 被动离线 Trace 整编更安全、成本更可控 |

---

## 后续注意事项 (Follow-up)

1. **Phase 51/52 完成后**，`README.md` 的 Academic Papers Referenced 表需同步新增 M-RAG（第 14 篇）和 GroupRAG（第 15 篇）条目。
2. **监控指标**：Cron 旁路执行 MarkerExtractor 时，应将"提取耗时"、"Token 消耗"与"缓存命中率"写入 `metrics.py`，供 Dashboard 展示。
3. **Phase 53 候选**：如用户反馈 Group-Aware 并发效果显著，可评估将 GroupAwareOrchestrator 的分组逻辑接入到 Dashboard 的"任务可视化"面板，让用户直观看到并发推理拓扑图。
