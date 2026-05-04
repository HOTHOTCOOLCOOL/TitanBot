# ADR-67: KnowledgeMapTool — KG 拓扑导航工具

**状态**: Accepted  
**来源**: CORPUS2SKILL 论文分析（arXiv 2604.14572v1）→ Harness 5 阶辩证工作流  
**日期**: 2026-04-25  
**影响模块**: `nanobot/agent/tools/`, `nanobot/agent/tool_setup.py`, `TOOLS.md`

---

## 背景

CORPUS2SKILL 论文揭示了 RAG 系统的根本盲点：**LLM 只能看到检索结果，永远不知道语料库里还有哪些话题区域**。Nanobot 的 5 层混合检索在召回精度上已优于论文基线，但面对跨越 2 个以上主题域的复杂组合查询时，LLM 缺少一张"知识地图"。

---

## 架构决策

### 采纳

| 决策 | 理由 |
|---|---|
| 实现 `KnowledgeMapTool` 作为**工具（Tool）**，而非技能（Skill） | `build_skills_summary()` 是全量系统提示词注入；工具只在 LLM 主动调用时消耗 Token，零基础开销 |
| 基于 **KG Degree Centrality** 识别域枢纽（非 K-Means） | 无需 sklearn 等外部 ML 依赖；复用现有 `graph.json`；O(N) 扫描零基建成本 |
| **Lazy mtime 缓存**：仅在 `graph.json` 变更时重算 | 启动无额外延迟；调用方 O(1) 响应 |
| **Search-First 永远是 P0**，本工具仅作 Fallback | 避免多余 Tool Call 造成延迟爆炸；保护现有 P95 <2s 查询性能 |
| 输出严控 ≤ 3,000 chars，错误返回标准 `"Error: ..."` 前缀 | Phase 22B TOOLS.md 审计契约 |

### 拒绝

| 拒绝项 | 理由 |
|---|---|
| 完全废除向量检索，改为纯树形导航 | 多轮导航延迟不可接受 |
| 将 `corpus_navigator` 注册为 Skill | 系统提示词全量注入污染，每轮 +800 token |
| `MemorySearchTool` 新增 `action: "preview"` | 现有 snippet 截断已满足需求 |
| 引入 sklearn / K-Means | 无必要依赖膨胀 |

---

## 实现细节

**文件**: `nanobot/agent/tools/knowledge_map.py`  
**注册**: `nanobot/agent/tool_setup.py` — `_register_default_tools()` 末尾  

### 核心算法
1. 读取 `workspace/memory/graph.json`，遍历所有 triples
2. 统计每个 Entity 的连接数（Degree）
3. 取 Top 15 Hub 节点，列出各自 Top 5 关联子节点
4. 生成文本树，硬截断至 3,000 chars

### 缓存机制
- 首次调用或 `graph.json` mtime 变更时重建
- 其他情况直接返回缓存字符串，无 I/O

---

## 验收标准

| # | 验收项 | 验证方式 |
|---|---|---|
| A1 | `knowledge_map` 工具正确注册 | `nanobot status` 输出中可见 |
| A2 | `graph.json` 为空时返回标准 Error 前缀 | `tests/unit/test_knowledge_map.py::test_empty_graph` |
| A3 | 输出字符数严格 ≤ 3,000 chars | `tests/unit/test_knowledge_map.py::test_output_cap` |
| A4 | mtime 不变时命中缓存（`json.loads` 只调用一次） | `tests/unit/test_knowledge_map.py::test_cache_hit` |
| A5 | 全量回归通过 | `pytest` ≥ 1324 passed, 0 failed |

---

## 影响范围

| 文件 | 变更类型 |
|---|---|
| `nanobot/agent/tools/knowledge_map.py` | NEW |
| `nanobot/agent/tool_setup.py` | 追加 2 行注册代码 |
| `TOOLS.md` | 追加第 20 条审计条目 |
| `tests/unit/test_knowledge_map.py` | NEW |
| `progress_report.md` | ADR-67 落入已完成列表，并补充人工验收结论 |
| `docs/archive/phase_67_knowledge_map_tool.md` | 追加人工验收记录 |
| `docs/tests/manual_guides/phase_67_manual_test_guide.md` | 补充现场验收备注 |

---

## Manual Acceptance (2026-05-04)

- **Scenario 1**: PASS. The agent invoked `knowledge_map` and summarized the top hubs from `workspace/memory/graph.json` correctly.
- **Scenario 2**: PASS WITH NOTE. The accepted runtime path used `knowledge_map` together with broad and refined `memory` searches in the same tool round, so the fallback intent was satisfied via parallel fan-out rather than a strictly serial `memory -> knowledge_map -> memory` chain.
- **Regression Target 1**: PASS. `exec("echo hello")` was still resolved through the normal tool registry and returned `hello`.
- **Regression Target 2**: PASS. Reading a large `tasks_tracking.json` payload produced `[OUTPUT TRUNCATED — original length: 52,183 chars]` in the dashboard without crashing the loop.
- **Operator note**: For truncation verification, the dashboard response is the source of truth. The backend `Response to dashboard:web:` log line may only show a head preview and may not include the visible truncation footer.
- See `docs/archive/phase_67_knowledge_map_tool.md` for the acceptance record and test-environment notes.
