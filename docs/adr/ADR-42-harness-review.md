# ADR-42: 核心架构 Harness 辩证审查 — 最终决策记录

> **状态**: Active  
> **日期**: 2026-04-06  
> **审核流程**: Harness 5 阶辩证工作流（Draft V1 → 极端批判 → 反思重构 → 正向校验 → 最终定稿）  
> **参与模型**: Claude Sonnet 4.6 (Planner) → Claude Opus 4.6 (Critic) → Gemini 3.1 Pro High (V2 Planner) → Gemini 3.1 Pro Low (Validator) → Claude Sonnet 4.6 (Final)  
> **审查对象**: `docs/architecture_harness_baseline.md` — Phase 38~41 核心架构基线  
> **决策者**: 首席架构师 + Harness 辩证评审委员会

---

## 背景 (Context)

Phase 41（洋葱中间件架构）完成后，系统进入一个相对稳定的结构基线期。为系统性地发现 Phase 38~41 累积的设计缺陷、技术债务和未来演进方向，启动了一次完整的 Harness 5 阶多模型辩证审查。

审查发现了 **1 个真实 P0 安全漏洞、1 个 P1 技术债、2 个 P2 重构项**，同时也通过辩证过程澄清了几个 Opus 的错误指控，锚定了应当永久保留的核心设计决策。

---

## 决策历程 (Decision Journey)

### 阶段一：Draft V1 (Claude Sonnet — Planner)

识别出 6 个问题域：
- P1: 正则旁路可能绕过 HITL（后被推翻）
- P1: 中间件无热重载
- P2: Token Clipping 与 RAG 的断层
- P2: 协程/进程隔离模型模糊
- P3: KI 污染与收敛性
- P3: 全局可观测性缺失

### 阶段二：极端批判 (Claude Opus — Red Team)

**有效发现（经后续阶段确认）**：
- 🚨 **C2 (真实 P0)**：SubagentManager 的 `_run_subagent` 维护独立裸 `while` 循环，完全脱离洋葱中间件管线，其内置 `ExecTool` 可在绕过 HITL 的情况下执行任意 Shell 命令。
- 🟡 **C6 (真实 P2)**：ReflectionStore（JSON Jaccard）与 Experience Bank（VectorStore embedding）双线并行，双路注入耗尽 `_INJECTION_BUDGET`，加剧幻觉级联。
- 🟡 **C8 (真实 P2)**：`loop.py` 膨胀至 2146 行/103KB，VLM 路由逻辑在两处完全重复。

**被驳回的指控（误判/幻觉）**：
- ❌ **C1 (Draft V1 P1 → 撤销)**：正则旁路含 `^...$` 全量锚点，复合业务请求无法被误触。
- ❌ **C3 (Opus P1 → 撤销)**：`abort()` first-come-first-served 是工业标准短路机制（Feature，非 Bug）。
- ❌ **C4 (Opus P0 → 撤销)**：`state_handler.py` 调用 `_run_agent_loop()`，此函数本身是感知中间件开关的 Facade，不存在绕过风险（代码核实确认）。

### 阶段三：反思重构 (Gemini High — V2 Planner)

- 坚决驳回 C1/C3/C4 三个误判，提供代码级反驳证据。
- 采纳 C2/C6 为真实漏洞。
- 提出 Hybrid Lazy-RAG 折中方案（摘要作语义索引 + `origin_ref` 指针按需深层检索）。

### 阶段四：正向校验 (Gemini Low — Validator)

- 确认 C2/C6 修复方案可落地。
- 建议 Gateway 解耦（C8）的修复优先级适当提前。
- 提出知识库归海合并须补写幂等迁移脚本，保护老用户"人格记忆延续"。

---

## 最终决策 (Final Decisions)

### 决策 1：永久保留的核心护栏

| 设计 | 决策 | 理由 |
|------|------|------|
| `abort()` first-come-first-served 短路机制 | 🔒 **永久保留** | 工业标准漏斗防洪，经三轮模型确认为正确的 Feature |
| `_run_agent_loop()` Facade 门面路由 | 🔒 **永久保留** | 所有外部调用点必须经此，Opus C4 指控经代码核实为幻觉 |
| 正则全量匹配（`^...$` 锚点） | 🔒 **永久保留** | 无安全风险，Opus C1 指控已撤销 |
| Token Clipping 摘要向量化策略 | 🔒 **以 Hybrid 形式演进** | 摘要控制预算，Phase 43 追加 `origin_ref` 指针实现深层检索 |

---

### 决策 2：Phase 42A — SubagentManager 安全补丁 (P0)

**问题**：`subagent.py::_run_subagent` 维护独立裸 `while` 循环，完全脱离洋葱管线。内置 `ExecTool` 可在绕过 HITL / FloodGuard / CircuitBreaker 的情况下执行任意 Shell 命令。

**决策**：
```python
# _run_subagent 改写核心逻辑
async def _run_subagent(self, task_id, task, label, origin):
    # 1. 构造受限 ToolRegistry（移除 spawn, message, coordinator）
    restricted_tools = self._build_restricted_registry()
    
    # 2. 构造沙盒 workspace
    sandbox = self.workspace / "workers" / task_id
    sandbox.mkdir(parents=True, exist_ok=True)
    
    # 3. 废弃独立循环，通过 _run_agent_loop() Facade 复用完整中间件体系
    async with self._tool_context_override(restricted_tools):
        final_content, _, _ = await self._agent_loop_ref._run_agent_loop(
            messages,
            channel="system",
            chat_id=f"worker:{task_id}",
        )
```

**受限 ToolRegistry 包含**：ReadFile, WriteFile（限沙盒目录）, ListDir, WebSearch, WebFetch  
**移除**：ExecTool（需 HITL 才可执行）, spawn, message, coordinator

**过渡策略**：此方案在 ADR-38-01 进程隔离落地前提供协程级安全保障。工期估计 4-6h。

---

### 决策 3：Phase 42B — 双脑知识库统一 (P1)

**问题**：ReflectionStore（reflections.json + Jaccard）与 Experience Bank（VectorStore + BM25/embedding）并行，双路注入 `_INJECTION_BUDGET`，可能产生矛盾的历史建议。

**决策**：
```
Step 1: 幂等迁移脚本（保护老用户历史记忆）
  migrate_reflections_to_experience_bank(
      source=workspace/"memory"/"reflections.json",
      target=knowledge_store,
      conflict_strategy="merge_if_similar_trigger"  # Jaccard > 0.7 则合并
  )

Step 2: 废弃 ReflectionStore 写入路径
  reflection.generate_reflection() → 改为写入 Experience Bank

Step 3: 统一 enrich_context 检索出口
  移除 ReflectionStore 检索，只保留 Experience Bank 一路
```

**关键约束**：迁移脚本必须为幂等（可重复执行不重复插入）。工期估计 6-8h。

---

### 决策 4：Phase 42C — loop.py 解耦首批 (P2)

**问题**：VLM 路由逻辑在 `_run_agent_loop`（L596-661）和 `_call_llm_for_turn`（L1112-1163）中完全重复，意图判定（`_CHITCHAT_REGEX`）被两处独立 `re.match` 计算。

**决策**：提取 `nanobot/agent/routing.py`：
- `ModelRouter`：统一 VLM 路由逻辑（消灭重复）
- `IntentClassifier`：统一意图判定（消灭双重计算）
- `_process_message` 将 `intent` 作为参数传递至 `_execute_with_llm`

工期估计 4h。

---

### 决策 5：Phase 43 — Hybrid Lazy-RAG (P3 · 设计预留)

**问题**：向量库存储 LLM 摘要（粗粒度），高置信命中后无法获取原始上下文细节。

**决策**（折中方案）：
```python
# 保留摘要作为语义索引（控制注入预算）
# 追加 origin_ref 指针元数据
vector_memory.ingest_text(
    history_entry,  # 仍为摘要
    source="history",
    metadata={
        "origin_session_id": session_key,
        "origin_message_range": f"{start}-{end}",
        "created_at": now_str,
    }
)
# 未来实现 deep_fetch(origin_ref) 和 recall_detail(topic) 工具
```

工期估计 8-12h。触发条件：RAG 召回质量收到明确用户投诉或监控数据显示检索命中率下降。

---

## 后果 (Consequences)

**正面**：
- 封堵当前架构中唯一可被主动利用的 P0 运行时安全漏洞
- 消除双脑知识库的注入预算浪费和幻觉级联风险
- 清晰区分"永久保留的核心护栏"与"需要演进的技术债"，为后续贡献者提供决策指南

**负面 / Trade-off**：
- Phase 42A 要求子代理从独立 ExecTool 降级（需用户 HITL 审批），对需要后台执行 Shell 命令的自动化场景有一定影响
- Phase 42B 迁移需要写迁移脚本并保证幂等性，有一定一次性工程开销
- Phase 42C 解耦首批不做全面重写，仅针对重复代码，残余复杂度仍存在

---

## 待实现文件清单

| 文件 | 类型 | 所属阶段 |
|------|------|---------|
| `nanobot/agent/subagent.py` | MODIFY | Phase 42A |
| `tests/test_subagent_security.py` | NEW | Phase 42A |
| `nanobot/agent/migration/migrate_reflections.py` | NEW | Phase 42B |
| `nanobot/agent/reflection.py` | MODIFY | Phase 42B |
| `nanobot/agent/context.py` (enrich_context) | MODIFY | Phase 42B |
| `nanobot/agent/routing.py` | NEW | Phase 42C |
| `nanobot/agent/loop.py` | MODIFY | Phase 42C |
| `nanobot/agent/vector_store.py` | MODIFY | Phase 43 |
| `nanobot/agent/tools/recall.py` | NEW | Phase 43 |

---

*归档时间：2026-04-06 | 辩证流程：Harness V1.0 | 最终定稿：Claude Sonnet 4.6 (Thinking)*
