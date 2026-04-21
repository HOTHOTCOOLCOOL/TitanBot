# ADR-57: Context Intelligence Upgrade
# Phase 57 — Waterfall Budget Allocation + Zero-Cost Visual Silent Downgrade

**Status:** Proposed (ADR 已定稿，待进入编码实施阶段)
**Date:** 2026-04-17
**Deciders:** Harness 5-阶辩证工作流 (Planner → Opus Critic → Gemini Pro High → Gemini Pro Low Validator → Sonnet Final)
**Source Papers:** HyperRAG (arXiv 2602.14470), VimRAG (arXiv 2602.12735), PlugMem (arXiv 2603.03296), Graph-based Agent Memory Survey (arXiv 2602.05665), AgenticRAGTracer (arXiv 2602.19127)

---

## 1. 背景与动机 (Context)

### 论文来源

本 ADR 源自对 5 篇前沿论文的系统性分析（见 `paper_analysis_report.md`）：

- **HyperRAG** (2602.14470): 提出 N-ary 超图聚合技术和 `50%:30%:20%` 预算分配比例，实验证明在多跳 QA 中为各类信息分层限额可显著降低 token 浪费并提升答案质量。
- **VimRAG** (2602.12735): 提出基于拓扑位置的视觉记忆能量衰减机制，越旧的视觉状态越不需要高分辨率保留，可剔除为轻量语义摘要。

### 现状痛点

1. **上下文注入无统一收口**：`context.py::build_messages()` 中 RAG 和 KG 的信息以裸字符串追加方式注入，完全不受 `_INJECTION_BUDGET` 约束。而 `verification.py::enrich_context()` 中的 Experience/Reminder 层有独立的 8000 字符预算。两条管道互不感知，实际总注入量无可控上限。
2. **视觉 token 在长 RPA 任务中爆炸性膨胀**：每次截图均作为 Base64 `image_url` 条目永久写入 `messages[]`，一个 8 步任务可积累 8×（数万字符）的视觉荷载，严重挤压有效上下文窗口。

---

## 2. 辩证修正历史 (Dialectic Record)

### Draft V1 核心假设被证伪

| V1 的错误假设 | 代码中的真实情况 |
|---|---|
| `_INJECTION_BUDGET` 统一管辖所有记忆注入 | RAG/KG 注入完全绕过预算约束，在 `build_messages()` 中裸追加 |
| 截图以 "Base64 列表" 驻留在 `vlm_feedback.py` | 截图作为 `user` 消息条目写入 `messages[]`，入口在 `add_tool_result()` |
| HyperRAG 固定比例可直接搬用 | 空层（如全新用户 KG 为空）会造成大量配额浪费 |

### 采纳的关键修正

| Opus 批判 | 最终决策 |
|---|---|
| 预算路径分裂，`_INJECTION_BUDGET` 实际只管 L0 层 | 重构 `build_messages()` 统一收口所有注入 |
| 固定比例在稀疏场景退化为浪费 | 改为动态瀑布流（Waterfall）——空层释放额度顺延下流 |
| 视觉衰减需要 VLM caption，额外 API 成本大 | 改为零成本 Silent Downgrade，转文本 block |
| 视觉衰减靶点错误 | 在 `_trim_history()` 中拦截，不新建 Manager 类 |
| 不应向用户暴露配额配置 | 所有常量锁定为 `context.py` 内部常量 |

---

## 3. 决策 (Decision)

### Feature A: 瀑布流上下文预算 (Waterfall Context Budgeting)

在 `context.py` 内新增 `_WaterfallBudget` 内部私有类，按**优先级顺序**分配上下文字符配额，未消费额度自动顺延至下级。

#### 优先级与层级上限

```
总预算: _CONTEXT_BUDGET = 8000 字符

层级 ① KG 实体摘要       上限 2400 字符 (30%)  最高语义密度
层级 ② Experience Bank   上限 1600 字符 (20%)  战术提示
层级 ③ Action History    上限 1200 字符 (15%)  UI 动作感知
层级 ④ System Reminder   上限  400 字符 ( 5%)  长会话提醒
层级 ⑤ RAG 向量检索      无硬上限 (兜底)       吃掉所有剩余额度
```

#### 核心设计原则

- **瀑布流**：高层级用不完的额度"流"向低层级，RAG 永远吃完所有剩余
- **软截断 (Soft Trim)**：在层级上限处按句子边界截断，不硬切单词
- **零配置暴露**：所有常量封装在 `context.py`，不渗透到 `config.json`

#### `_WaterfallBudget` 实现规范

```python
class _WaterfallBudget:
    """Priority-ordered cascading context budget allocator."""

    def __init__(self, total: int = _CONTEXT_BUDGET) -> None:
        self._remaining = total
        self._parts: list[str] = []

    def add(self, content: str, cap: int | None = None) -> int:
        """Add content within optional cap. Returns characters consumed."""
        if not content or self._remaining <= 0:
            return 0
        budget = min(self._remaining, cap) if cap else self._remaining
        chunk = content[:budget]
        # Soft trim: preserve sentence boundaries
        if len(content) > budget:
            last_break = max(
                chunk.rfind("。"), chunk.rfind("\n"), chunk.rfind(". ")
            )
            if last_break > budget * 0.7:
                chunk = chunk[:last_break + 1]
        self._parts.append(chunk)
        consumed = len(chunk)
        self._remaining -= consumed
        return consumed

    def build(self) -> str:
        return "\n\n".join(p for p in self._parts if p)
```

#### `build_messages()` 改造后的注入流

```python
# context.py::build_messages() 重构后伪代码
waterfall = _WaterfallBudget(total=_CONTEXT_BUDGET)

waterfall.add(kg_context,          cap=_KG_ENTITY_CAP)    # 层①
waterfall.add(experience_hint,     cap=_EXPERIENCE_CAP)   # 层②
waterfall.add(action_history,      cap=_ACTION_HIST_CAP)  # 层③
waterfall.add(reminder_text,       cap=_REMINDER_CAP)     # 层④ (条件性)
waterfall.add(rag_context,         cap=None)              # 层⑤ 兜底无上限

system_prompt += "\n\n" + waterfall.build()
```

#### `verification.py::enrich_context()` 角色重构

- **旧职责**：检索 + 字符串追加到 system_prompt
- **新职责**：仅检索，返回字符串给调用者（`build_messages()`），由后者统一注入

---

### Feature B: 零成本视觉静默降级 (Visual Silent Downgrade)

在 `context.py::_trim_history()` 首行调用新增的 `_downgrade_old_images()` 预处理。

#### 设计原理

```
messages 历史:
[step1: user+image][step2: user+image]...[stepN-2: user+image][stepN-1: user+image][stepN: user+image]
 ←————————————————————— 降级为纯文本 ——————————————————————→ ←—— HOT WINDOW 保留完整 ——→
```

#### 实现规范

```python
_VISUAL_HOT_STEPS = 3  # 最近 N 条含图消息保留完整 Base64

def _downgrade_old_images(
    self, history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Zero-cost visual context compression.

    Processes messages outside the HOT_WINDOW: replaces image_url blocks
    with standard text blocks, preserving ANCHORS diagnostic text.
    No extra LLM/VLM API calls.
    """
    if len(history) <= _VISUAL_HOT_STEPS:
        return history

    cold_messages = history[:-_VISUAL_HOT_STEPS]
    hot_messages  = history[-_VISUAL_HOT_STEPS:]
    result_cold   = []

    for msg in cold_messages:
        content = msg.get("content")
        if not isinstance(content, list):
            result_cold.append(msg)
            continue

        has_image = any(
            isinstance(c, dict) and c.get("type") == "image_url"
            for c in content
        )
        if not has_image:
            result_cold.append(msg)
            continue

        # Strip image_url blocks, preserve text (ANCHORS, task prompts)
        text_parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        placeholder = "[视觉快照已折叠，保留锚点信息]"
        combined = placeholder + "\n" + "\n".join(text_parts) if text_parts else placeholder

        # Convert to standard text-only content block (compatible with all providers)
        result_cold.append({
            **{k: v for k, v in msg.items() if k != "content"},
            "content": [{"type": "text", "text": combined}],
        })

    return result_cold + hot_messages


def _trim_history(self, history, system_prompt, current_message, context_limit):
    # NEW: Pre-process old visual messages first (zero API cost)
    history = self._downgrade_old_images(history)
    # ... existing trim logic unchanged ...
```

---

## 4. 受影响文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `nanobot/agent/context.py` | **MODIFY** | 新增 `_WaterfallBudget` 类、5 层常量、`_downgrade_old_images()`；重构 `build_messages()` 注入段；`_trim_history()` 前插预处理 |
| `nanobot/agent/verification.py` | **MODIFY** | `enrich_context()` 重构为返回字符串而非直接追加；移除 `_INJECTION_BUDGET` 硬限制逻辑 |
| `nanobot/agent/middleware/action_history.py` | **MODIFY** | 移除对 `verification._INJECTION_BUDGET` 的 import；预算管控权上移至 `ContextBuilder` |
| `docs/adr/ADR-57-context-intelligence-upgrade.md` | **NEW** | 本文件 |
| `progress_report.md` | **MODIFY** | 添加 Phase 57 条目至 Backlog |
| `tests/agent/test_waterfall_context.py` | **NEW** | 覆盖 7 个测试场景 |

---

## 5. 测试计划

```python
# tests/agent/test_waterfall_context.py

# Test 1: KG 为空时 RAG 占满全部 8000 字符预算
# Test 2: KG 饱和时 RAG 只拿剩余份额
# Test 3: 所有层均为空时 system_prompt 无额外内容
# Test 4: 所有层均满时按优先级顺序截断，总量不超过 _CONTEXT_BUDGET
# Test 5: _downgrade_old_images - HOT_STEPS 内消息原样保留 Base64
# Test 6: _downgrade_old_images - 第 4+ 步之前图片转为纯文本 block
# Test 7: 转换后 content 结构符合 OpenAI/Anthropic schema (list[{"type": "text", ...}])
```

```bash
# 单元测试
python -m pytest tests/agent/test_waterfall_context.py -v

# 核心回归
python -m pytest tests/ -k "context or memory or verification" -v
```

---

## 6. 明确不在本 ADR 范围内的事项

- ❌ VLM caption 回顾机制（额外 API 调用，成本不可控）
- ❌ 向用户暴露 `MemoryBudgetConfig`（过度配置化，伪需求）
- ❌ HyperRAG 固定 50/30/20 比例（实验数据不适用于 Nanobot 场景）
- ❌ 超图（Hypergraph）数据结构引入（违背零额外依赖约束）
- ❌ AgenticRAGTracer 多跳评测基准集（学术工具，与 Nanobot 应用方向冲突）
