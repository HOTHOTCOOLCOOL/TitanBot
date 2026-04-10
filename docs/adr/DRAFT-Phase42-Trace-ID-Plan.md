> **[Agentic Note 2026-04-06]**: 本文档为窗口并发执行时产生的 "Phase 42A: 全链路 Trace-ID" 架构实现方案备份。
> 当前项目主线的 Phase 42A 已根据最新的 Harness 审查调整为 `SubagentManager 安全补丁 [P0]`。全链路 Trace-ID 计划已移至 Backlog (Wait List)。
> 保留此草案文档以供后续 Harness 分析和重启该任务时参考，从而避免浪费先前消耗的 Token 算力。

# Phase 42-Draft: 全链路 Trace-ID / X-Route-Header 染色系统

> **Backlog P1** — 构建针对 Agent Loop 复杂路由机制的追踪标识。在入站/出站消息中注入唯一 Trace-ID，并在 Metadata 中携带流转路径，从根本上解决排障盲区。

## 背景

当前 Nanobot 拥有 34+ 条 `logger.info/warning` 散落在 `loop.py` 中，但所有日志都是 **无关联散弹**：无法将一条入站消息与它触发的所有 LLM 调用、工具执行、中间件拦截串成一条完整的链路。当多个通道的消息并发处理时，日志交织，排障完全靠猜。

Phase 42A 的目标是：**单个请求的完整生命周期，从入站到出站，用一个 Trace-ID 串联所有日志、事件和 Metrics，并在 Metadata 中染色标记路由路径。**

## User Review Required

> [!IMPORTANT]
> **零新依赖约束**：本方案不引入 OpenTelemetry/Jaeger/Zipkin 等外部 tracing 基础设施。纯 Python 内存生成 Trace-ID + loguru 结构化绑定 + 现有 DomainEvent / Dashboard WebSocket 通道透传。符合项目 zero-extra-infrastructure 原则。

> [!WARNING]
> **日志格式变更**：所有 `logger.*` 输出将在消息前自动附加 `[trace_id]` 前缀。如果您有外部日志解析管道（ELK/Splunk 等），需要更新解析规则。当前判断：您未使用外部日志系统，影响为零。

---

## Proposed Changes

### Component 1: Trace Context 核心数据结构

#### [NEW] [trace_context.py](file:///d:/Python/nanobot/nanobot/utils/trace_context.py)

新建轻量级 Trace Context 模块：

```python
# 核心能力:
# 1. generate_trace_id() → 8 字符短 ID (hex)，人工可读可复制
# 2. RouteTag enum — 所有可能的路由染色标记
# 3. TraceContext dataclass — 可变聚合体，跟随请求完整生命周期
# 4. contextvars 绑定 — 供 loguru 自动提取 trace_id
```

- `trace_id`: 基于 `uuid4().hex[:8]` 的短 ID（碰撞概率极低，8 字符足够排障）
- `RouteTag`: 枚举所有路由节点标记：
  - `L0_CHITCHAT_BYPASS` — 正则闪电旁路
  - `L0_FAST_MODEL` — 快速模型降级
  - `STATE_HITL_SUSPEND` — HITL 挂起等待人工
  - `STATE_KNOWLEDGE_MATCH` — 知识库精确命中
  - `STATE_KNOWLEDGE_ADAPT` — 知识库部分命中自适应
  - `L1_RULE_BLOCK` — L1 验证层规则拦截
  - `L3_MAIN_PIPELINE` — 完整 Agent 主管道
  - `MW_CIRCUIT_BREAK` — 熔断器触发
  - `MW_FLOOD_GUARD` — 防洪限流
  - `MW_CRASH_RECOVERY` — 崩溃恢复
  - `VLM_ROUTED` — 视觉模型路由
- `TraceContext`: 包含 `trace_id`, `route_tags: list[str]`, `start_time`, `model_used`, `channel`, `session_key`
- 使用 `contextvars.ContextVar` 存放当前请求的 `TraceContext`，loguru 的 `logger.bind()` 以此自动注入

---

### Component 2: TurnContext 扩展

#### [MODIFY] [base.py](file:///d:/Python/nanobot/nanobot/agent/middleware/base.py)

- 在 `TurnContext.__slots__` 中新增 `trace_id` 字段（`str`）
- 在 `__init__` 中新增 `trace_id` 参数（从 while loop 透传）
- **影响范围**：所有 middleware 的 `pre_process` / `post_process` 可通过 `ctx.trace_id` 读取当前链路 ID

---

### Component 3: 入站注入点

#### [MODIFY] [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py)

**3a. `_process_message()` — Trace 生命周期起点**（约 L1591）：
- 在方法入口处 `generate_trace_id()`，创建 `TraceContext`
- 使用 `contextvars` 绑定到当前协程
- 使用 `logger.bind(trace_id=trace_id)` 确保后续所有日志自动携带
- 在方法的每个 return 路径（HITL/知识库命中/LLM执行等），给 `OutboundMessage.metadata` 注入 `trace_id` + `route_tags`

**3b. `_execute_with_llm()` — 意图分类染色**（约 L1837）：
- 在 `intent = "chitchat_safe"` 分支打上 `L0_CHITCHAT_BYPASS` + `L0_FAST_MODEL` tag
- 在 VLM 路由时打上 `VLM_ROUTED` tag
- `trace_id` 透传到 `_run_agent_loop()` / `_run_agent_loop_v2()`

**3c. `_run_agent_loop_v2()` — TurnContext 注入**（约 L1307）：
- 在构建 `TurnContext(...)` 时传入 `trace_id`
- 在 while 循环的关键决策点（wait-phrase / fake-completion / ABORT / FINISH）记录 route tag

**3d. `_get_middleware_pipeline()` — 无变化**：
- Pipeline 本身不变，trace_id 通过 TurnContext 自然穿透

---

### Component 4: 中间件自动染色

#### [MODIFY] 各中间件（仅 `post_process` 补染色，约 1-3 行/文件）

| 中间件 | 染色时机 | Route Tag |
|--------|---------|-----------|
| `circuit_breaker.py` | `ctx.abort()` 被调用时 | `MW_CIRCUIT_BREAK` |
| `hitl.py` | HITL 挂起时 | `STATE_HITL_SUSPEND` |
| `verification_mw.py` | L1 拦截时 | `L1_RULE_BLOCK` |
| `flood_guard.py` | 防洪触发时 | `MW_FLOOD_GUARD` |
| `crash_recovery.py` | 恢复路径时 | `MW_CRASH_RECOVERY` |

实现方式：在各中间件的 `pre_process` 或 abort 逻辑中，调用 `trace_context.add_route_tag(ctx.trace_id, tag)`。**无新文件、无结构变更**，仅追加 1-3 行代码。

---

### Component 5: 出站透传

#### [MODIFY] [events.py](file:///d:/Python/nanobot/nanobot/bus/events.py)

- `DomainEvent.to_dict()` 自动从 `contextvars` 读取 `trace_id` 并注入到输出 dict
- 这样 Dashboard WebSocket 收到的所有 `tool_executed` / `knowledge_matched` 事件天然携带 trace_id，前端可做链路聚合

#### [MODIFY] `OutboundMessage` 无结构变更
- 已有 `metadata: dict` 字段，`_process_message` 出口处将 `trace_id` + `route_tags` 写入 `metadata["trace"]`

---

### Component 6: Loguru 结构化绑定

#### [MODIFY] [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py) (`_process_message` 入口)

```python
from nanobot.utils.trace_context import generate_trace_id, set_current_trace

trace_id = generate_trace_id()
trace_ctx = set_current_trace(trace_id, channel=msg.channel, session_key=key)
_logger = logger.bind(trace_id=trace_id)
```

所有后续 `logger.info(...)` 自动输出 `[abc12def] Processing message...` 格式。
使用 loguru 的 `bind()` 机制，不修改全局 logger format，仅在请求作用域内生效。

---

### Component 7: 测试

#### [NEW] [test_trace_context.py](file:///d:/Python/nanobot/tests/test_trace_context.py)

- `test_generate_trace_id_uniqueness` — 生成 1000 个 ID 确保无重复
- `test_generate_trace_id_format` — 8 字符 hex
- `test_route_tag_accumulation` — 模拟完整请求路径，验证 tag 正确累积
- `test_contextvars_isolation` — 模拟并发协程，验证 trace 上下文不串扰
- `test_domain_event_trace_injection` — 验证 `DomainEvent.to_dict()` 自动携带 trace_id
- `test_outbound_metadata_trace` — 验证出站消息 metadata 包含 trace 信息

---

## 潜在雷区与防御

| 风险 | 分析 | 对策 |
|------|------|------|
| `contextvars` 协程隔离 | `asyncio.create_task()` 会继承父 context，SubagentManager 的后台任务可能继承主请求的 trace_id | SubagentManager spawn 时显式 `copy_context()` 并重设 trace_id，或者让 subagent 共享主 trace（可溯源——更好方案）|
| Legacy path (v1 loop) | `_run_agent_loop` 的 legacy 代码路径也需要透传 trace_id | 在 legacy path 入口处同样绑定 trace_id |
| 性能影响 | `uuid4()[:8]` + `contextvars.get()` 均为纳秒级操作 | 零可感知影响 |
| 日志体积增长 | 每行日志增加 10 字符前缀 | 可忽略 |

---

## 文件变更总览

| 文件 | 类型 | 变更量 |
|------|------|--------|
| `nanobot/utils/trace_context.py` | **NEW** | ~80 行 |
| `nanobot/agent/middleware/base.py` | MODIFY | +3 行（`__slots__` + `__init__`）|
| `nanobot/agent/loop.py` | MODIFY | ~30 行（3 个方法注入 trace）|
| `nanobot/agent/middleware/circuit_breaker.py` | MODIFY | +2 行 |
| `nanobot/agent/middleware/hitl.py` | MODIFY | +2 行 |
| `nanobot/agent/middleware/verification_mw.py` | MODIFY | +2 行 |
| `nanobot/agent/middleware/flood_guard.py` | MODIFY | +2 行 |
| `nanobot/bus/events.py` | MODIFY | +5 行 |
| `tests/test_trace_context.py` | **NEW** | ~120 行 |

**总新增代码：~250 行。零新依赖。零配置变更。**

---

## Verification Plan

### Automated Tests
```bash
pytest tests/test_trace_context.py -v
pytest tests/test_middleware_pipeline.py -v   # 回归
pytest tests/ -x --timeout=60                 # 全量回归
```

### Manual Verification
1. 启动 Nanobot，发送一条闲聊消息 → 检查日志出现 `[trace_id]` 前缀 + `L0_CHITCHAT_BYPASS` tag
2. 发送一条需要工具执行的任务 → 检查日志 trace_id 一致贯穿、Dashboard 事件携带 trace_id
3. 触发 HITL → 检查 `STATE_HITL_SUSPEND` tag 出现在出站 metadata

## Open Questions

> [!IMPORTANT]
> **Subagent trace 继承策略**：当主请求 spawn 子代理时，子代理是否应该继承主请求的 trace_id（形成 parent-child 链路），还是生成独立 trace_id？
> 建议：继承主 trace_id，额外附加 `span_id` 区分子代理。但 Phase 42A 暂不实现 span_id，先做 flat trace。

> [!NOTE]
> 本 Phase 只做"染色注入"，不做"UI 展示"。Phase 42B 可以在 Dashboard 前端增加 Trace 搜索/聚合面板。
