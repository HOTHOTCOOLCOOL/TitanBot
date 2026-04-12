# ADR-50: Knowledge Graph Wiki Export (KG-Wiki)

**状态 (Status)**: Accepted  
**日期 (Date)**: 2026-04-12  
**决策者 (Deciders)**: Harness 5-Stage Dialectic (Claude Sonnet → Claude Opus → Gemini Pro High → Gemini Pro Low → Claude Sonnet)  
**源论文 (Source Paper)**: LLM Wiki — A pattern for building personal knowledge bases using LLMs (Karpathy, 2026)  
**相关 ADR**: ADR-47 (Paper Analysis Harness), ADR-49 (IFCC)

---

## 背景与动机 (Context)

Karpathy 的 LLM Wiki 提出了一个核心设计理念：LLM 不仅仅是查询时的检索器，而应当成为**增量式、持久化知识编译器**——在原始文档与用户之间维护一层可持续积累的 Markdown Wiki，使知识结构不断沉淀，交叉引用自动生成，矛盾点自动浮现。

Nanobot 拥有高度复杂的 7 层记忆架构（L1 Preferences → L7 Knowledge Graph），以及 5 层混合检索金字塔，在技术能力层面已**完全超越**论文所描述的 RAG 模式。

然而，Nanobot 存在一个关键 UX 短板：**知识库对用户完全不透明**。L7 Knowledge Graph 的 500 条实体三元组以 JSON 格式存于 `graph.json`，L3 Daily Logs 为纯文本，L5 Deep Consolidation 的产物仅供 Agent 内部使用。用户无法感知 Agent 的"认知状态"，无法以人类可读的方式浏览 Agent 学到了什么。

本 ADR 的目标是**因地制宜地借鉴**论文的 Wiki 可见性理念，而非盲目照搬其"以 Markdown 文件作为后端核心数据库"的实现。Nanobot 的 KG + Vector Store 后端远比平铺文件更具结构性优势，不可降级替换。

---

## 核心决策 (Decision)

实施 **Phase 50: Knowledge Graph Wiki Export (KG-Wiki)**，以**旁路观测式单向投影（Passive Observer Sync）**为核心架构原则：

1. **Markdown Wiki 是 L7 KG 的"只读投影"，绝非数据源**。所有写操作仍走正式 KG/Memory 管道（`/remember`、Knowledge Workflow、Consolidation）。
2. **完全解耦于 AgentLoop 主路径**。WikiSyncer 永远不在 Agent 热路径上执行，不在 `memory_manager.py` 的整编链路内触发，彻底消除对 P50 延迟的影响。
3. **零 LLM 调用**。整个 Export 是纯文本转换，从 `graph.json` 读取并渲染为 Markdown，无需任何 API 调用。
4. **特性开关保护**。默认 `false`，仅在用户显式 opt-in（配置 `features.wiki_export: true`）后生效。
5. **Obsidian 原生兼容**。所有输出文件使用 YAML Frontmatter + `[[WikiLink]]` 格式，直接兼容 Obsidian 的 Graph View 和 Dataview 插件。

---

## 辩证历程摘要 (Dialectic Summary)

### 被否决的 Draft V1 方案

| 设计 | 否决原因 |
|------|--------|
| 在 `knowledge_workflow.py` upsert 时注入 Hook | KG 更新实际在 `memory_manager.py._deep_consolidate_inner()` 中异步 fire-and-forget，Hook 注入点完全错误 |
| 在 `memory_manager.py` 整编完成后写入 Wiki | 会与 `distill_preferences` 和 `kg_extraction` 产生三段异步竞态，所有任务共抢磁盘 IO |
| Phase 46B Worker 触发 WikiExporter | Worker 运行在独立进程中，受 toolset 限制，无法访问主进程的 WikiSyncer 实例 |
| Cron Job 发送 `/wiki lint` 给 AgentLoop | 触发完整 LLM 调用链（key_extraction → knowledge_match → reasoning）处理一个文件扫描任务，成本极高且不合理 |

### 采纳的 Extreme Critic 批判 (Claude Opus)

| 批判 | 采纳的解决方案 |
|------|--------------|
| KG 存储规模有限（MAX=500 Triples），为其构建完整 Wiki 管道 ROI 低 | 正因节点数量精炼，Obsidian Graph View 体验最佳；接受规模有限，但**可见性价值不为零** |
| Hook 注入点全部定位错误 | 完全放弃 inline 触发，改为旁路观测式 Passive Sync |
| 无法阻止用户编辑 Markdown 文件 | 不再禁止——在每次覆盖时重置，头部用 `> [!WARNING]` 明确声明 Agent 为单一数据源 |
| Windows 文件命名非法字符 `\/:*?"<>|` 导致崩溃 | 引入 `sanitize_title()` 管道，替换非法字符为 `_` |
| Alias 在 Markdown 端引发同名文件覆盖 | 利用 YAML Frontmatter 的 `aliases` 字段承接 `graph.json._aliases` 映射，物理文件唯一 |

### 明确拒绝的过度批判

| 批判 | 拒绝理由 |
|------|--------|
| "整个功能不值得实现" | 用户可见性是 Nanobot 的长期 UX 债务。即使 KG 当前规模有限，持续增长的实体库将使此功能愈加有价值 |
| "Dashboard 渲染即可替代 Markdown 文件" | Dashboard 是 Web UI，Obsidian 是本地 Graph IDE；二者解决不同使用场景，不可互相替代 |

### 蓝方评审采纳的微调 (Gemini Pro Low)

1. 增加全局特性开关 `config.features.wiki_export`，默认 `false`，非 Obsidian 用户零成本。

---

## 技术架构规格 (Architecture Spec)

### 数据流向

```
workspace/memory/graph.json       ─────╮
workspace/memory/experiences.json ─────┤──→  WikiSyncer.sync()  ──→  workspace/wiki/
workspace/memory/MEMORY.md        ─────╯    (diff by updated_at)
                                                  ├── entities/<sanitized_name>.md
                                                  ├── concepts/<sanitized_topic>.md
                                                  ├── directives/<date>-auto.md
                                                  ├── _index.md
                                                  └── _log.md

触发方式 (三种旁路触发，互不阻塞 AgentLoop):
  1. CLI:       nanobot wiki sync [--force]
  2. Dashboard: "Sync to Wiki" → POST /api/wiki/sync
  3. Cron:      纯代码时间戳检查 (每 N 秒), features.wiki_export=true 时激活
```

### 受影响文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `nanobot/agent/wiki_syncer.py` | **[NEW]** | WikiSyncer 核心引擎 |
| `nanobot/agent/commands.py` | 修改 | 新增 `/wiki` 命令路由 (sync, status, open) |
| `nanobot/cli/` | 修改 | 新增 `nanobot wiki sync` 终端命令 |
| `nanobot/config/schema.py` | 修改 | `FeaturesConfig` 新增 `wiki_export: bool = False`, `wiki_sync_interval_seconds: int = 3600` |
| `nanobot/cron/service.py` | 修改 | 条件注册 wiki sync 内置任务（不走 AgentLoop） |
| `nanobot/dashboard/` | 修改 | Knowledge Tab 新增 Sync Now 按钮与状态展示 |
| `tests/test_phase50_wiki_syncer.py` | **[NEW]** | 回归测试：文件命名、alias 映射、idempotency、空 KG 边界 |

### WikiSyncer 关键设计

**文件名清洗：**
```python
def sanitize_title(name: str) -> str:
    """Replace Windows-illegal chars with underscore. Preserves CJK Unicode."""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()
```

**实体页 YAML Frontmatter（承接 `_aliases`）：**
```yaml
---
aliases: ["David", "刘总"]
updated: "2026-04-12T12:00:00"
type: "kg_entity"
nanobot_source: "graph.json"
---
```

**防篡改声明（每次覆盖重置）：**
```markdown
> [!WARNING]
> This file is **auto-generated** by Nanobot's Knowledge Graph.
> **Local edits will be OVERWRITTEN** on the next sync.
> To update knowledge, use `/remember` or the standard Knowledge Workflow.
```

**Triples 聚合表（同一实体所有关系汇入同一 Table）：**
```markdown
## Knowledge Graph Connections

| Predicate | Target | Context |
|-----------|--------|---------|
| works for | [[Salesforce]] | Based in Shenzhen AI research team since 2020 |
| uses | [[Python FastAPI]] | Primary backend framework preference |
```

**`_log.md` 追加格式（符合 Karpathy 的 grep-parseable 约定）：**
```
## [2026-04-12 12:10:00] Synced 42 entities, 187 triples, 5 directives
```

### 配置示例

```json
{
  "features": {
    "wiki_export": true,
    "wiki_sync_interval_seconds": 3600
  }
}
```

---

## 边界条件与安全约束

| 约束 | 处理方式 |
|------|--------|
| `graph.json` 不存在或为空 | 优雅退出，不创建任何文件，记录 warning log |
| `updated_at` 未变化 | Cron 触发时 no-op，跳过所有 IO |
| 实体名重复（大小写变体，Windows 不敏感）| sanitize 后增加 `_{hash4}` 后缀去重 |
| `workspace/wiki/` 磁盘空间不足 | 捕获 `OSError`，记录错误，不中断主进程 |
| 用户手动编辑文件 | 下次 sync 时直接覆盖，不 merge，不报错 |

---

## 预估工作量 (Effort Estimate)

**总计**: ~4 工作日

| Phase | 内容 | 工时 |
|-------|------|------|
| 50A | `wiki_syncer.py` 核心引擎（解析、转换、sanitize、Frontmatter 构建） | 2 天 |
| 50B | CLI `nanobot wiki sync` + `/wiki` 命令集成 | 0.5 天 |
| 50C | Cron 时间戳旁路集成（纯代码，不经 AgentLoop） | 0.5 天 |
| 50D | Dashboard Sync 按钮 + Config 开关 + 回归测试 | 1 天 |

---

## 与 Karpathy 论文的明确边界声明

本实施**有意识地偏离**了论文的原始全貌：

| 论文主张 | Nanobot 的处理方式 | 理由 |
|--------|-----------------|------|
| Wiki IS the primary knowledge layer | Wiki 是 KG 的只读投影 | 7 层记忆 + Vector Store 的结构性优势不可降级 |
| LLM incrementally writes wiki on ingest | 纯代码导出，零 LLM 调用 | 遵循 zero-extra-infrastructure 原则 |
| Lint via LLM health check | 纯代码文件扫描 | Lint 不应消耗 LLM Token 预算 |
| Bidirectional exploration via wiki | 单向只读镜像 | Agent 为单一数据源，防止状态分叉 |

---

## 后续注意事项 (Follow-up)

1. **README 学术引用更新**: 实施完成后，`README.md` 的 Academic Papers Referenced 表需新增 Karpathy LLM Wiki 条目（第 13 篇）。
2. **Obsidian 使用指南**: 在 `docs/OPERATIONS.md` 增加"知识图谱可视化"段落，说明如何将 `workspace/wiki/` 添加为 Obsidian Vault。
3. **Phase 51 候选**: 若用户反馈良好，未来可评估在 Dashboard 内嵌 Graph View（使用 `vis.js` / `d3-force` 渲染 KG 三元组），进一步减少对 Obsidian 外部工具的依赖。
