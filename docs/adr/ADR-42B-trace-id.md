# ADR-42B: 全链路 Trace-ID / X-Route 染色系统 — 最终架构决策记录

> **状态**: Active
> **日期**: 2026-04-07
> **审核流程**: Harness 5 阶辩证工作流（Draft V1 → 极端批判 → 反思重构 → 正向校验 → 最终定稿）
> **参与模型**: Claude Sonnet 4.6 Thinking (Planner) → Claude Opus 4.6 Thinking (Critic) → Gemini 3.1 Pro High (V2 Planner) → Gemini 3.1 Pro Low (Validator) → Claude Sonnet 4.6 Thinking (Final)
> **审查对象**: `docs/adr/DRAFT-Phase42-Trace-ID-Plan.md`
> **前置依赖**: ADR-42（SubagentManager 安全补丁，P0，优先于本任务）
> **优先级**: Backlog P1 — 待 Phase 42A 完成后启动

---

## 背景 (Context)

Nanobot 的 `loop.py` 中存在 34+ 条无关联散弹日志。多通道并发处理时，日志交织、排障完全靠猜。Phase 42B 目标：**用一个 Trace-ID 将单次请求的完整生命周期（入站→路由决策→中间件拦截→工具执行→出站）串联**，零新依赖，纯内存实现。

---

## Harness 辩证历程摘要

### Draft V1 识别的核心问题
- `_process_message` 有 7+ 个 return 路径，逐一注入 trace 极易断链
- `SubagentManager` 的背景任务需要 trace 血缘传播
- `contextvars` 协程继承需要显式清理，防止协程取消后 ContextVar 悬挂

### Opus 极端批判（已确认的真实漏洞）

| ID | 严重性 | 问题核心 |
|----|--------|---------|
| F1 | 🔴 致命 | `DomainEvent.to_dict()` 内注入 contextvars 违反纯函数语义，Cron/定时任务调用时必崩 |
| F2 | 🔴 致命 | 修改 `TurnContext.__slots__` 语义层级错误（trace 是「请求级」，TurnContext 是「迭代级」）|
| F3 | 🔴 致命 | 7 个 return 路径逐一硬编码注入，必然遗漏导致断链 |
| F4 | 🟠 严重 | SubagentManager 独立 while loop 的 trace 传播完全未设计 |
| F5 | 🟠 严重 | `loguru.bind()` 返回局部对象，已有 34+ 条日志不会自动携带 trace |
| F6 | 🟠 严重 | `route_tags` 用 List 无上限无清理，内存泄漏风险 |
| F7 | 🟡 异味 | 无前缀 8 字符 hex 在日志中易误匹配其他 hex 字符串 |
| F8 | 🟡 异味 | `L3_MAIN_PIPELINE` 是永真条件标记，无排障价值 |
| F9 | 🟡 异味 | `parent_trace_id` 无消费者（Opus 判断为 YAGNI）|

### 辩证决策：采纳与反驳

**采纳（F1→F8）**：
- **Shell Pattern**：`_process_message` 改为外壳，内部逻辑提取为 `_core_process_message`，外壳统一负责 Trace 生命周期，100% 防断链
- **Loguru Patcher**：启动时挂载 `logger.configure(patcher=...)` 替代 `bind()`，零侵入覆盖全部历史日志
- **不修改 TurnContext**：中间件直接调用 `get_current_trace_id()` 读上下文
- **事件边界注入**：在 `MessageBus.publish_event()` 统一注入，不在 `to_dict()` 中污染 dataclass
- **`frozenset` + reset Token**：防重复、防协程取消后泄漏
- **`t-xxxxxxxx` 前缀**：提升日志 grep 精度
- **删除 `L3_MAIN_PIPELINE`**，拆分 `RoutingTag` / `InterceptTag`

**反驳（F9：parent_trace_id）**：
- `parent_trace_id` 的主要消费者是**终端 grep 日志的排障工程师**，不需要 UI
- Subagent 回调主进程时，携带 `parent_trace_id` 是追溯跨协程调用链的唯一手段
- **决策**：保留 parent_trace_id，但 Phase 42B 只做 flat 2-level lineage，不做 span tree

---

## 最终技术实施路径

### Component 1: 核心 Context 模块

**[NEW] `nanobot/utils/trace_context.py`** (~70 行)

```python
"""Phase 42B: Zero-dependency full-chain trace context."""
import contextvars
import uuid
from typing import FrozenSet
from loguru import logger

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="no-trace")
_route_tags_var: contextvars.ContextVar[FrozenSet[str]] = contextvars.ContextVar(
    "route_tags", default=frozenset()
)

def generate_trace_id() -> str:
    """Generate a human-readable trace ID with t- prefix."""
    return f"t-{uuid.uuid4().hex[:8]}"

def get_current_trace_id() -> str:
    return _trace_id_var.get()

def add_route_tag(tag: str) -> None:
    """Add a routing/interception tag to current trace context (idempotent)."""
    current = _route_tags_var.get()
    _route_tags_var.set(current | {tag})  # frozenset union — no mutation bugs

def get_route_tags() -> FrozenSet[str]:
    return _route_tags_var.get()


class RoutingTag:
    """Tags for routing decisions (non-exception paths)."""
    CHITCHAT_FAST    = "CHITCHAT_FAST"       # 正则旁路快速路
    VLM_ROUTE        = "VLM_ROUTE"           # 视觉模型路由
    RAG_ADAPT        = "RAG_ADAPT"           # 知识库部分命中自适应
    SUBAGENT_CALLBACK = "SUBAGENT_CALLBACK"  # Subagent 回调入站


class InterceptTag:
    """Tags for middleware interception events."""
    L1_BLOCK       = "L1_BLOCK"        # L1 验证层规则拦截
    HITL_SUSPEND   = "HITL_SUSPEND"    # HITL 挂起等待人工
    CB_TRIP        = "CB_TRIP"         # 熔断器触发
    FLOOD_BLOCK    = "FLOOD_BLOCK"     # 防洪限流
    CRASH_RECOVERY = "CRASH_RECOVERY"  # 崩溃恢复路径


def trace_log_patcher(record: dict) -> None:
    """Loguru record patcher: prepend [trace_id] to every log message.

    Mount at startup: logger.configure(patcher=trace_log_patcher)
    Defensive: never raises, never silences logs.
    """
    try:
        tid = _trace_id_var.get()
        if tid != "no-trace":
            record["message"] = f"[{tid}] {record['message']}"
    except Exception:
        pass  # Patcher must NEVER break the logging pipeline
```

---

### Component 2: Loguru Patcher 挂载

**[MODIFY] `nanobot/main.py`** (启动入口，+2 行)

```python
from nanobot.utils.trace_context import trace_log_patcher
from loguru import logger
logger.configure(patcher=trace_log_patcher)
```

---

### Component 3: Shell Pattern — loop.py 修改

**[MODIFY] `nanobot/agent/loop.py`** (~20 行净增)

原 `_process_message` 方法体**完整保留、仅重命名**为 `_core_process_message`（内部一字不动）。
新增外壳 `_process_message`：

```python
async def _process_message(
    self, msg: InboundMessage, session_key: str | None = None
) -> OutboundMessage | None:
    from nanobot.utils.trace_context import (
        generate_trace_id, _trace_id_var, _route_tags_var,
        get_current_trace_id, get_route_tags, RoutingTag, add_route_tag,
    )

    # 1. 解析 Subagent 回调携带的 parent trace
    parent_trace_id = (msg.metadata or {}).get("trace_id")

    # 2. 生成本次请求的新 trace
    new_trace = generate_trace_id()
    t_token = _trace_id_var.set(new_trace)
    r_token = _route_tags_var.set(frozenset())

    if parent_trace_id:
        logger.info(f"Subagent callback from parent trace={parent_trace_id}")
        add_route_tag(RoutingTag.SUBAGENT_CALLBACK)

    try:
        out_msg = await self._core_process_message(msg, session_key)

        # 3. 统一出站打标 — 所有 return 路径在此一次性覆盖，零遗漏
        if out_msg is not None:
            if out_msg.metadata is None:
                out_msg.metadata = {}
            out_msg.metadata["trace_id"] = new_trace
            tags = get_route_tags()
            if tags:
                out_msg.metadata["route_tags"] = sorted(tags)
            if parent_trace_id:
                out_msg.metadata["parent_trace_id"] = parent_trace_id

        return out_msg

    finally:
        # 4. 强制重置 — 防止协程取消后 ContextVar 悬挂（内存泄漏）
        _trace_id_var.reset(t_token)
        _route_tags_var.reset(r_token)
```

> **染色点** (在 `_execute_with_llm` 中, +2行):
> ```python
> # chitchat 快速旁路处
> if intent == "chitchat_safe":
>     add_route_tag(RoutingTag.CHITCHAT_FAST)
>
> # VLM 路由处 (_call_llm_for_turn)
> if has_image:
>     add_route_tag(RoutingTag.VLM_ROUTE)
> ```

---

### Component 4: Subagent 血缘传播

**[MODIFY] `nanobot/agent/subagent.py`** (~12 行)

```python
async def spawn(self, task, label, origin_channel, origin_chat_id) -> str:
    from nanobot.utils.trace_context import get_current_trace_id
    parent_trace = get_current_trace_id()  # 在当前主请求 context 中捕获
    task_id = f"t-{uuid.uuid4().hex[:8]}"  # Subagent 自己的 trace（复用 ID 格式）
    # ...创建 bg_task 时传入 parent_trace...

async def _run_subagent(self, task_id, task, label, origin, parent_trace=None):
    from nanobot.utils.trace_context import _trace_id_var, _route_tags_var
    t_token = _trace_id_var.set(task_id)
    r_token = _route_tags_var.set(frozenset())
    logger.info(f"Subagent started. parent_trace={parent_trace}")
    try:
        # ... 原有 while loop 不变 ...
        pass
    finally:
        _trace_id_var.reset(t_token)
        _route_tags_var.reset(r_token)

async def _announce_result(self, task_id, label, task, result, origin, status):
    from nanobot.utils.trace_context import get_current_trace_id
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id=f"{origin['channel']}:{origin['chat_id']}",
        content=announce_content,
        metadata={"trace_id": get_current_trace_id()},  # 供主进程解析血缘
    )
    await self.bus.publish_inbound(msg)
```

---

### Component 5: MessageBus 事件边界注入

**[MODIFY] `nanobot/bus/queue.py`** 的 `publish_event()` (+4 行)

```python
async def publish_event(self, event: DomainEvent) -> None:
    from nanobot.utils.trace_context import get_current_trace_id
    tid = get_current_trace_id()
    if tid != "no-trace":
        event.metadata["trace_id"] = tid
    # ... 原有 publish 逻辑不变 ...
```

> `DomainEvent` 的 dataclass 本身及其 `to_dict()` 方法绝不修改。

---

### Component 6: 中间件轻量染色（各 +1-2 行）

| 文件 | 触发时机 | Tag |
|------|---------|-----|
| `middleware/hitl.py` | `ctx.abort()` HITL 路径 | `InterceptTag.HITL_SUSPEND` |
| `middleware/circuit_breaker.py` | 熔断触发 | `InterceptTag.CB_TRIP` |
| `middleware/verification_mw.py` | L1 规则拦截 | `InterceptTag.L1_BLOCK` |
| `middleware/flood_guard.py` | 限流触发 | `InterceptTag.FLOOD_BLOCK` |
| `middleware/crash_recovery.py` | 崩溃恢复路径 | `InterceptTag.CRASH_RECOVERY` |

---

### Component 7: 测试套件

**[NEW] `tests/test_trace_context.py`** (~130 行，10 个测试用例)

| 测试用例 | 验证内容 |
|---------|---------|
| `test_trace_id_format` | `t-` 前缀 + 8 字符 hex |
| `test_trace_id_uniqueness` | 1000 个 ID 无重复 |
| `test_route_tags_idempotent` | 重复 add_route_tag 不累积 |
| `test_contextvars_coroutine_isolation` | 并发协程 trace 不串扰 |
| `test_shell_pattern_finally_cleanup` | 协程取消后 ContextVar 正确 reset |
| `test_patcher_no_trace_context` | 无 trace 时日志无前缀 |
| `test_patcher_with_trace_context` | 有 trace 时日志自动携带前缀 |
| `test_bus_event_stamping` | `publish_event` 后 event.metadata 含 trace_id |
| `test_subagent_parent_trace_propagation` | Subagent InboundMessage.metadata 含 trace_id |
| `test_outbound_metadata_trace` | 出站消息 metadata 含 trace_id + route_tags |

---

## 文件变更总览

| 文件 | 类型 | 净增量 |
|------|------|--------|
| `nanobot/utils/trace_context.py` | **NEW** | ~70 行 |
| `nanobot/main.py` | MODIFY | +2 行 |
| `nanobot/agent/loop.py` | MODIFY | ~20 行（外壳 + 2 处染色点）|
| `nanobot/agent/subagent.py` | MODIFY | ~12 行 |
| `nanobot/bus/queue.py` | MODIFY | +4 行 |
| `middleware/hitl.py` | MODIFY | +2 行 |
| `middleware/circuit_breaker.py` | MODIFY | +2 行 |
| `middleware/verification_mw.py` | MODIFY | +2 行 |
| `middleware/flood_guard.py` | MODIFY | +2 行 |
| `middleware/crash_recovery.py` | MODIFY | +2 行 |
| `tests/test_trace_context.py` | **NEW** | ~130 行 |

**总净增：~250 行。零新依赖。零配置变更。**

---

## 核心设计护栏（永久保留，不得修改）

| 护栏 | 决策 | 原因 |
|------|------|------|
| Loguru Patcher 机制 | 🔒 永久保留 | 零侵入覆盖所有历史日志，不退化为逐行 bind |
| Shell Pattern 统一出口 | 🔒 永久保留 | 物理防止多 return 路径断链 |
| 事件总线边界注入 | 🔒 永久保留 | DomainEvent dataclass 保持纯洁性 |
| Finally 块 reset Token | 🔒 永久保留 | 防协程取消后 ContextVar 悬挂 |
| flat 2-level lineage | 🔒 Phase 42B 范围 | span tree 留 Phase 42C |

---

## 验证计划

```bash
pytest tests/test_trace_context.py -v
pytest tests/test_middleware_pipeline.py -v  # 回归
pytest tests/ -x --timeout=60               # 全量
```

手动验证：
1. 发送闲聊 → 日志出现 `[t-xxxxxxxx]` + `CHITCHAT_FAST` tag
2. 发送工具任务 → 所有日志 trace_id 贯穿，Dashboard 事件含 trace_id
3. 触发 HITL → 出站 metadata 含 `HITL_SUSPEND` + trace_id

---

*归档时间：2026-04-07 | 辩证流程：Harness V1.0 | 最终定稿：Claude Sonnet 4.6 (Thinking)*
