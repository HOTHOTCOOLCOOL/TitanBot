# ADR-59: Antigravity Pattern Integration
# Phase 59 — Knowledge Infrastructure Hardening (KI Rules + TaskTracker Transparency + Planning Gate)

**Status:** Proposed (ADR 已定稿，待进入编码实施阶段)
**Date:** 2026-04-18
**Deciders:** Harness 5-阶辩证工作流 (Sonnet Planner → Opus Critic → Gemini Pro High → Gemini Pro Low → Sonnet Final)
**Source:** `docs/antigravity_architecture_reference.md` — Antigravity Agent Manager 五大机制对比分析

---

## 1. 背景与动机 (Context)

本 ADR 源自对 Antigravity 引擎五大核心机制的系统性对比分析。通过 Harness 5 阶辩证工作流（规划 → 极端批判 → 反思重构 → 正向校验 → 最终定稿），对初始 Draft V1 中的两处严重失误进行了修正，最终提炼出 3 个可落地的工程特性。

### 1.1 核心对比矩阵（最终确认版）

| Antigravity 机制 | Nanobot 实际状态（经代码审计） | 差距等级 | ADR-59 决策 |
|---|---|---|---|
| Planning Mode（规划锁） | L1 Rules + HITLMiddleware 覆盖终端危险，但无复杂度前置门控 | 🟡 部分 | **Feature C**：借用 HITL 实现轻量 Planning Gate |
| Artifact State Tracking | `TaskTracker`（458 行）已存在，但 LLM 无法感知 | 🟡 部分 | **Feature B**：L0 注入 TaskTracker 状态 |
| Sub-Agent Delegation | `ExcelActuator`/`GroupRAG`/`browser_use_worker` 已覆盖 | 🟢 75% | **不触碰**（边界清晰，各自独立） |
| KI Injection | L3 Experience Bank 存在，但缺乏"确定性硬编码经验"层 | 🟡 35% | **Feature D**：引入 ki_rules 确定性经验池 |
| Concurrent Tool Exec | Legacy + Middleware 两条线均已完整实现 `asyncio.gather` | 🟢 **100%** | **不触碰**（已完全对齐） |

> ⚠️ **重要更正**：Draft V1 对并发工具执行的差距评估（70%）系严重失实。经 Opus 代码审计确认，`loop.py` L827 和 `tool_executor.py` L60 均已完整实现 `asyncio.gather`，此机制为 **100% 对齐**，无需任何修改。

### 1.2 从 Opus 极端批判中吸纳的关键修正

| Opus 批判 | 最终决策 |
|---|---|
| Planning Mode 建议引入隐式 DAG，违反「保持单循环」核心戒律 | **彻底重构**：不引入状态机；改用带 `IS_HIGH_RISK` 标签的 `write_artifact` 工具借道现有 HITLMiddleware 实现阻断 |
| Draft V1 忽视已有 `TaskTracker`（458行），建议新建竞争性 task.md 系统 | **废弃 V1 方案**：复用 `TaskTracker`，仅新增 L0 注入与工具声明 |
| KI 关键词路由精度不可控，预算可能撑爆 WaterfallBudget | **降维到战术短规则**：单条 KI 硬约束 < 500 chars；以关键词初筛（零延迟，无 LLM 调用），强制纳入 Waterfall 总预算计数 |
| 并发工具执行差距评估为 70%，实为已完全实现 | **承认错误，移除重构计划** |
| 统一 TaskRegistry 引入上帝类，违反工具解耦原则 | **放弃大一统注册表**；仅在 Metrics 层补充并发 Worker 总数探针，防止多工具并发 OOM |

---

## 2. 决策 (Decision)

> **本 ADR 不包含 Feature A（Visual Silent Downgrade）**。
> 该特性已在 ADR-57 中完整设计，实施路径清晰，将以最高优先级（Priority 0）作为 Phase 57 编码实施的**第一行代码**。本 ADR 专注于尚未被 ADR 覆盖的新特性。

---

### Feature B：TaskTracker L0 透传注入 (TaskTracker Transparency)

**动机**：`TaskTracker` 已有完整的任务状态持久化能力，但 LLM 在执行过程中对其当前任务的"已完成步骤、进行中步骤"完全无感知，导致在多轮会话中出现重复执行或遗忘前置步骤的现象。

#### B.1 注入规范

在 `context.py::build_messages()` 末尾、`enrich_context()` 之前，追加 Task 状态注入片段：

```python
# ADR-59 Feature B: TaskTracker L0 injection
# 仅当存在活跃任务时注入，且总字符强制截断至 400 chars
def _format_task_status(tracker: "TaskTracker | None") -> str:
    """Format active task progress for L0 injection. Hard cap 400 chars."""
    if tracker is None:
        return ""
    task = tracker.get_active_task()
    if not task:
        return ""

    # 取最近 3 个步骤摘要，防止步骤数量爆炸注入预算
    recent_steps = task.steps[-3:] if len(task.steps) > 3 else task.steps
    steps_text = "; ".join(
        f"{'✅' if s.status == 'completed' else ('🔄' if s.status == 'running' else '⏳')} {s.name}"
        for s in recent_steps
    )
    raw = (
        f"\n\n## 🗂️ Active Task\n"
        f"Task: {task.user_request[:80]}\n"
        f"Status: {task.status.value} | "
        f"Progress: {tracker.get_progress(task.task_id).get('progress_percent', 0)}%\n"
        f"Recent Steps: {steps_text}"
    )
    return raw[:400]  # Hard cap — 蓝方锚定要求
```

注入点（`context.py::build_messages()` 末端，系统 prompt 拼接后）：

```python
# ADR-59 B: Inject active task status (budget-capped)
if task_tracker is not None:
    task_status = _format_task_status(task_tracker)
    if task_status and len(system_prompt) + len(task_status) <= _CONTEXT_BUDGET:
        system_prompt += task_status
```

#### B.2 工具声明

同时新增 `update_task_progress` Tool（轻量声明，15 行），允许 LLM 主动更新步骤状态：

```python
# skills/builtin/update_task_progress.py
def execute(action: str, step_name: str, status: str = "completed") -> str:
    """Update active task step status. action=update_step|complete_task|fail_task"""
    tracker = get_active_tracker()
    task = tracker.get_active_task() if tracker else None
    if not task:
        return "Error: No active task to update."
    # ... route to tracker.update_step / complete_task / fail_task
```

---

### Feature C：轻量 Planning Gate（借道 HITLMiddleware）

**动机**：对于高破坏性的复杂指令（如大规模重构、数据库迁移），Nanobot 当前只能在执行终端危险工具时才被 L1 拦截，缺乏前置的"计划确认"阶段。Antigravity 的 Planning Mode 启发我们引入这一机制，但不能打破 AgentLoop 单循环。

**核心洞察（感谢 Gemini Pro High 防守方的反驳）**：HITLMiddleware 已经是一个完美的"单循环内挂起机制"。只需给 `write_artifact` 工具赋予 `IS_HIGH_RISK` 标签，即可自然复用审批流实现 Planning Gate——无需任何状态机、无需任何新架构层。

#### C.1 新增 `write_artifact` 工具

```python
# nanobot/tools/write_artifact.py

class WriteArtifactTool(BaseTool):
    """
    Write a structured implementation plan artifact to workspace.

    High-Risk: requires HITL approval so the user can review the plan
    before execution begins. This is Nanobot's Planning Mode equivalent.
    """
    # 赋予 IS_HIGH_RISK 标签 → 自动触发 HITLMiddleware 审批流
    static_tags = CapabilityTag.FILE_WRITE | CapabilityTag.IS_HIGH_RISK

    name = "write_artifact"
    description = (
        "Write an implementation plan, ADR, or task breakdown to disk. "
        "ALWAYS use this tool first when the user requests a complex "
        "multi-step operation (refactoring, migration, bulk deletion). "
        "The plan will be reviewed by the user before execution proceeds."
    )

    async def execute(self, path: str, content: str) -> str:
        artifact_path = Path(self.workspace) / path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return f"Artifact written to {path}. Awaiting user approval to proceed."
```

#### C.2 L0 提示词锚点

在 `AGENTS.md` 或 `build_system_prompt()` 中插入一条硬性规范：

```markdown
## ⚙️ Complex Task Protocol
When the user requests a task involving: bulk deletion, system migration,
core module refactoring, or any operation with > 3 irreversible steps —
you MUST use `write_artifact` to produce an implementation plan FIRST.
Do NOT proceed to execution tools until the user approves the plan.
```

---

### Feature D：KI Rules 确定性经验池

**动机**：现有 L3 Experience Bank（基于 LLM 提炼）是"柔性记忆"，匹配准确率依赖向量相似度。ARCHITECTURE.md 的 Lesson 体系是"刚性硬经验"，但目前只有人能读，LLM 无法被自动路由到相关 Lesson。KI Rules 是两者的桥梁：**确定性关键词触发的硬编码战术规则**。

#### D.1 文件格式规范

```
.nanobot/ki_rules/
  excel-com.ki.json       # 关键词：excel, com, actuator, pivot
  async-cancel.ki.json    # 关键词：async, cancellerror, coroutine
  browser-ssrf.ki.json    # 关键词：browser, url, navigate, 127

每个 .ki.json 格式：
{
  "keywords": ["excel", "com", "pivot"],   // 任一命中即触发（OR逻辑）
  "rule": "当操作 Excel COM 时，必须....", // 战术规则正文，强制 < 500 chars
  "lesson_ref": "lesson-12-windows-orphan.md"  // 可选：原始 Lesson 文件引用
}
```

#### D.2 加载与注入规范

```python
# verification.py::enrich_context() 首行前置调用
def _match_ki_rules(request_text: str, ki_dir: Path) -> str:
    """
    Deterministic keyword-match KI rules. Zero LLM calls, zero latency.
    Returns combined injection text, hard-capped at 500 * matched_count chars
    (actual cap enforced by WaterfallBudget upstream).
    """
    if not ki_dir.exists():
        return ""
    matched = []
    req_lower = request_text.lower()
    for ki_file in ki_dir.glob("*.ki.json"):
        try:
            data = json.loads(ki_file.read_text(encoding="utf-8"))
            keywords = [k.lower() for k in data.get("keywords", [])]
            if any(kw in req_lower for kw in keywords):
                rule = data.get("rule", "")[:500]  # Hard cap per rule
                matched.append(f"⚡ KI Rule [{ki_file.stem}]: {rule}")
        except Exception:
            pass  # 单条 KI 解析失败不影响主流程
    return "\n".join(matched)
```

注入时机：在 `verification.py::enrich_context()` 最开头调用，命中内容计入 `injection_used` 字符数，参与 WaterfallBudget 全局预算约束（超出则跳过）。

#### D.3 KI 规则大小强制验证

```python
# tests/test_ki_budget.py — 蓝方锚定要求
def test_ki_rules_size_constraint():
    """All KI rules must be < 500 chars. Enforced at test time, not runtime."""
    ki_dir = Path(".nanobot/ki_rules")
    if not ki_dir.exists():
        return
    for ki_file in ki_dir.glob("*.ki.json"):
        data = json.loads(ki_file.read_text())
        rule_len = len(data.get("rule", ""))
        assert rule_len < 500, (
            f"{ki_file.name}: rule is {rule_len} chars (limit 500). "
            "KI rules must be concise tactical hints, not essays."
        )
```

---

## 3. 架构决策备忘录 (ADR Summary)

### 保留/坚持了初代方案 (Draft V1) 的哪些核心设计

1. ✅ **五机制作为分析框架**：Antigravity 对比分析的整体对照结构完整保留，作为 Nanobot 下一阶段架构演进的参考地图。
2. ✅ **KI 自动注入的方向**：从"靠开发者纪律人工读 Lesson"升级为"程序自动路由 KI 规则"的核心方向正确，保留。
3. ✅ **TaskTracker 状态可视化**：让 LLM 能感知当前任务进度，方向完全正确，保留。

### 采纳了哪些关键的批评与重构建议

1. ✅ **废弃新建 task.md 系统**：改为复用现有的 `TaskTracker`（Opus C2 批判采纳）。
2. ✅ **Planning Mode 不引入状态机**：改用 `write_artifact` + `IS_HIGH_RISK` + HITLMiddleware（Opus C1 批判采纳，Gemini High 创新折中）。
3. ✅ **KI 限制为战术短规则 < 500 chars**（Opus C3 批判采纳，Gemini Low 补充了自动化测试强制约束）。
4. ✅ **取消并发工具执行审计**：代码已 100% 实现，无需任何修改（Opus C4 批判采纳）。
5. ✅ **放弃 TaskRegistry 统一注册表**（Opus C5 批判采纳）。
6. ✅ **Visual Silent Downgrade 提升为全局最高优先级**（Opus C6 批判采纳）。

---

## 4. 受影响文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `nanobot/agent/context.py` | **MODIFY** | 新增 `_format_task_status()` + `task_tracker` 参数注入 |
| `nanobot/tools/write_artifact.py` | **NEW** | Planning Gate 工具，挂载 `IS_HIGH_RISK` |
| `nanobot/agent/verification.py` | **MODIFY** | `enrich_context()` 首行前插 `_match_ki_rules()` 调用 |
| `.nanobot/ki_rules/excel-com.ki.json` | **NEW** | Excel COM 战术规则（种子文件） |
| `.nanobot/ki_rules/async-cancel.ki.json` | **NEW** | Async CancelledError 战术规则（种子文件） |
| `AGENTS.md` | **MODIFY** | 新增「Complex Task Protocol」L0 提示词锚点 |
| `docs/adr/ADR-59-antigravity-pattern-integration.md` | **NEW** | 本文件 |
| `progress_report.md` | **MODIFY** | 添加 Phase 59 条目至 Backlog |
| `tests/test_ki_budget.py` | **NEW** | KI 规则 <500 chars 大小强制验证测试 |

---

## 5. 明确不在本 ADR 范围内的事项

- ❌ **Visual Silent Downgrade**：已在 ADR-57 设计完毕，列为 Phase 57 编码 Priority 0，无需本 ADR 重复设计。
- ❌ **统一 TaskRegistry**：工具解耦原则优先，仅在 Metrics 层补充并发 Worker 探针（作为可观测性改进，不单独立 ADR）。
- ❌ **KI 的 LLM 自动沉淀**：LLM 自动生成 KI 规则不可靠（类比 ADR-56 中废弃 LLM 自动生成 validator），KI 只由人工以已知教训为基础编写。
- ❌ **复杂度评分器**：V1 中提议的关键词启发式复杂度评估，已被 Opus 证明在中文语境下失效，彻底放弃。`write_artifact` + L0 提示词引导 LLM 自判断取代之。

---

## 6. 验证计划

```bash
# Feature B: TaskTracker 注入验证
python -m pytest tests/ -k "task_tracker or context" -v

# Feature C: write_artifact + HITL 流验证（手动冒烟）
# 向 Nanobot 发送："帮我把整个 nanobot/ 目录重构为 monorepo 结构"
# 预期：Agent 调用 write_artifact 生成计划，HITLMiddleware 弹出审批提示
# 确认：未收到 Yes/Always 前，无任何写操作工具被执行

# Feature D: KI Rules 验证
python -m pytest tests/test_ki_budget.py -v
# 手工验证：发送含 "excel com" 关键词的请求，确认 L0 注入包含 ki_rules 内容

# 回归测试
python -m pytest tests/ -k "verification or context or loop" -v
```
