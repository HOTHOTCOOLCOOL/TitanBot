# 上游 HKUDS/nanobot vs 自定义复刻版 — 全面功能对比

> 基线版本：HKUDS/nanobot（D:\Python\HKUDS\nanobot）  
> 改良版：TitanBot（D:\Python\nanobot）  
> 对比时间：2026-04-05

---

## 总览对比表

| 维度 | 上游 HKUDS | 你的改良版 | 优势方 |
|------|-----------|-----------|--------|
| 核心 Loop 代码量 | `loop.py` 780行 + `runner.py` 601行 | `loop.py` 1658行（合体） | ⚖️ 各有利弊 |
| Agent 模块文件数 | 8 个 | 30 个 | 改良版 (功能更丰富) |
| 内置工具种类 | 10 个 | 19 个 | 改良版 |
| 通道适配器数 | 15 个（含 Matrix/WeCom/微信） | 9 个 | 上游 |
| LLM Provider 数 | 13+（含 Azure、Ollama、OVMS、Mistral） | 12+（litellm 统一接入） | 各有侧重 |
| 架构可扩展性 | ✅ Hook/Runner 分层 | ❌ 单体嵌入 | **上游** |
| 记忆系统 | 3层（MEMORY/SOUL/USER + Dream + GitStore） | 7层（+向量/KG/反思/经验） | **改良版** |
| 安全机制 | 基础 SSRF + 工具校验 | 4层验证漏斗 + HITL + Sandbox | **改良版** |
| 并发控制 | Semaphore + 会话锁 | 无显式并发保护 | **上游** |
| 测试覆盖 | 10+ 测试子目录 + facade 测试 | 少量散落测试 | **上游** |
| API 服务器 | ✅ OpenAI 兼容 HTTP API | ❌ 无（仅 Dashboard WS） | **上游** |
| 国际化 | 通过模板文件 | 完整 i18n 模块 | **改良版** |

---

## 一、核心架构设计

### 上游优势: Hook/Runner 分层极佳

上游将核心执行循环拆分为三个正交层次：

```
AgentLoop (产品控制层)
  └── AgentRunner (纯执行引擎, 无业务逻辑)
        └── AgentHook (生命周期回调, 可组合)
```

- [hook.py](file:///D:/Python/HKUDS/nanobot/nanobot/agent/hook.py) 定义了 `AgentHook` 抽象基类，含 6 个生命周期钩子: `before_iteration`, `on_stream`, `on_stream_end`, `before_execute_tools`, `after_iteration`, `finalize_content`
- [runner.py](file:///D:/Python/HKUDS/nanobot/nanobot/agent/runner.py) 是一个**纯粹的工具执行循环**，601行，完全不含业务逻辑。它通过 `AgentRunSpec` dataclass 接收所有配置。
- `CompositeHook` 支持将多个 Hook 安全组合，且每个 Hook 的错误被隔离 (`try/except` 包裹)，不会导致主循环崩溃。

> [!IMPORTANT]
> 这正是第二阶段 Critic 指出的核心差距：**上游已经原生支持无侵入扩展**。你要添加自定义行为（如 Verification Layer），只需编写一个 `AgentHook` 子类，而非直接修改 `_run_agent_loop`。

### 改良版现状: 单体 God Method

你的 `loop.py`（1658行）将 Runner、Hook、Product Logic 全部合并在一起：
- `_run_agent_loop` (L492-1002) 包含 VLM 路由、circuit breaker、fuzzy loop detection、HITL、streaming 等
- `_process_message` (L1135-1603) 包含 HITL、Knowledge Matching、Fast Intent Routing、RAG Prefetch、Verification 等

虽然功能更丰富，但可扩展性和可维护性远不如上游的分层设计。

---

## 二、记忆与知识系统

### 改良版优势: 7 层记忆架构远超上游

| 记忆维度 | 上游 | 改良版 |
|----------|------|--------|
| 长期记忆 (MEMORY.md) | ✅ | ✅ |
| 人格 (SOUL.md) | ✅ | ❌ (无独立 SOUL 文件) |
| 用户画像 (USER.md) | ✅ | ✅ (personalization.py) |
| 对话历史 | ✅ history.jsonl (JSONL + cursor) | ✅ session manager |
| 向量检索 (VectorStore) | ❌ | ✅ [vector_store.py](file:///d:/Python/nanobot/nanobot/agent/vector_store.py) (31KB, BM25+Dense hybrid) |
| 知识图谱 (KG) | ❌ | ✅ [knowledge_graph.py](file:///d:/Python/nanobot/nanobot/agent/knowledge_graph.py) (30KB, Entity-Relation) |
| 反思记忆 (Reflection) | ❌ | ✅ [reflection.py](file:///d:/Python/nanobot/nanobot/agent/reflection.py) (7.9KB, 元认知) |
| 经验库 (Experience Bank) | ❌ | ✅ (knowledge_workflow + save_experience) |
| 任务知识 (Task Knowledge) | ❌ | ✅ [task_knowledge.py](file:///d:/Python/nanobot/nanobot/agent/task_knowledge.py) (12.8KB) |

### 上游优势: Dream 系统更加成熟

上游的 `Dream` 类 ([memory.py](file:///D:/Python/HKUDS/nanobot/nanobot/agent/memory.py) L531-707) 实现了一个**两阶段记忆加工管道**：
1. **Phase 1**: LLM 分析对话历史与现有记忆文件的差异
2. **Phase 2**: 通过 `AgentRunner` + `read_file/edit_file` 工具进行**精准增量编辑**（而非全量替换）

配合 [GitStore](file:///D:/Python/HKUDS/nanobot/nanobot/utils/gitstore.py)（基于 dulwich 的纯 Python Git 实现），提供：
- 记忆版本历史 (`/dream-log`)
- 记忆回滚 (`/dream-restore <sha>`)
- cron 调度自动运行

### 上游优势: Token-Budget 驱动的智能巩固

上游的 `Consolidator` 类实现了基于 **token 预算**的自动巩固：
```python
budget = context_window_tokens - max_completion_tokens - safety_buffer
```
当 session 的 prompt token 超过预算时，自动从最旧的消息开始归档。找到合法的 user-turn 边界后进行裁剪。

你的改良版使用消息计数（每 20 条触发），相比之下更粗粒度。

---

## 三、工具生态

### 改良版独有工具

| 工具 | 代码量 | 功能 |
|------|--------|------|
| `OutlookTool` | 34.8KB | Win32 COM 操作 Outlook 收发邮件/日历 |
| `AttachmentAnalyzerTool` | 10.3KB | 邮件附件智能解析 |
| `RPAExecutorTool` | 23KB | UIAutomation 桌面自动化 |
| `ScreenCaptureTool` | 11.6KB | 屏幕截图 + OCR |
| `DrawImageTool` | 3.8KB | AI 图片生成 |
| `SaveSkillTool` | 11KB | 工作流保存为可复用技能 |
| `SaveExperienceTool` | 2.6KB | 经验库写入 |
| `TaskMemoryTool` | 5.6KB | 任务记忆 CRUD |
| `MemorySearchTool` | 9.8KB | 向量+全文统一搜索 |
| `BrowserTool` (plugins/) | 44KB | Playwright 浏览器自动化 |
| `BrowserUseWorker` (plugins/) | 10KB | browser-use 库集成 |

### 上游独有/更强的工具

| 工具 | 差异 |
|------|------|
| `WebSearchTool` | 支持 5 个引擎 (DuckDuckGo/Brave/Tavily/SearXNG/Jina) vs 你的仅 Brave |
| `WebFetchTool` | 16KB vs 你的 10KB，上游含完整 SSRF 防护 + proxy 支持 |
| `Tool` 基类 | 上游多了 `concurrency_safe`、`exclusive`、`cast_params`、`validate_params` 等高级特性 |
| `CronTool` | 上游支持时区感知 (default_timezone) |

---

## 四、安全机制

### 改良版优势: 4 层验证漏斗

你的安全层远比上游成熟：

```
L0: 上下文增强 (Experience+Reflection注入)
    ↓
L1: 刚性规则拦截 (路径审计/命令黑名单) — 预执行
    ↓
L3: 后反思 & 知识提取 — 后执行
    ↓
HITL: 高风险操作审批 (支持远程跨通道审批)
```

- [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py) (25KB) — L0→L1→L3 完整管道
- [sandbox.py](file:///d:/Python/nanobot/nanobot/agent/sandbox.py) (5.8KB) — 路径/命令沙箱
- [hitl_store.py](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py) (4.6KB) — 审批存储
- Phase 37: Execution Trace Archive — 失败任务的 LLM 驱动事后分析

### 上游安全: 基础但清晰

- [network.py](file:///D:/Python/HKUDS/nanobot/nanobot/security/network.py) — 仅 SSRF 防护 (IP 黑名单 + DNS 解析验证)
- Tool 基类的 `validate_params` + `cast_params` — 参数级别校验
- Shell 工具的 `restrict_to_workspace`
- 无 HITL、无路径审计、无命令黑名单

---

## 五、通道适配

### 上游优势: 通道覆盖更广

| 通道 | 上游 | 改良版 |
|------|------|--------|
| Telegram | ✅ (42KB) | ✅ |
| WhatsApp | ✅ | ✅ |
| Discord | ✅ (21KB) | ✅ |
| 飞书/Lark | ✅ (58KB) | ✅ |
| 钉钉 | ✅ (24KB) | ✅ |
| Slack | ✅ (13KB) | ✅ |
| Email | ✅ (20KB) | ✅ |
| QQ | ✅ (23KB) | ✅ |
| **Mochat** | ✅ (39KB) | ✅ |
| **Matrix** | ✅ (36KB) | ❌ |
| **WeCom (企业微信)** | ✅ (14KB) | ❌ |
| **微信 (Weixin)** | ✅ (55KB) | ❌ |
| 通道配置架构 | `extra="allow"` 动态 | 每个通道一个 Config 类 |

> [!NOTE]
> 上游的 `ChannelsConfig` 使用 `extra="allow"`，允许任意通道插件注册自己的配置而不修改 schema.py。你的改良版每增一个通道就要修改 schema。

---

## 六、Provider 系统

### 上游优势: 原生 Provider 更多

上游额外支持（你没有的）：
- **Azure OpenAI** — 独立 provider 实现 (`azure_openai_provider.py`)
- **Ollama** — 本地模型直连
- **OVMS (OpenVINO Model Server)** — 边缘推理
- **Mistral**
- **StepFun (阶跃星辰)**
- **Xiaomi MIMO**
- **BytePlus**

### 改良版优势: 统一的 litellm 路由

你通过 `litellm` 做统一接入，实际上可以路由到上游支持的所有 provider。但上游选择了**直接实现**（如 Anthropic 的原生 SDK 调用 `anthropic_provider.py` 18KB），在错误处理和流式输出上更精细。

### 上游优势: Provider 重试机制

上游 Provider 基类支持 `chat_with_retry` / `chat_stream_with_retry`，带内置重试策略 (`standard` / `persistent` 模式)。你的改良版无此机制。

---

## 七、命令系统

### 上游优势: 正式的 CommandRouter 架构

上游有一个独立的 [command/](file:///D:/Python/HKUDS/nanobot/nanobot/command/) 包：
- `CommandRouter` — 支持 priority (不可中断) 和 exact/prefix 匹配
- `/stop` — 真正取消 asyncio task（你的版本只有 session 清理）
- `/restart` — `os.execv` 热重启
- `/dream` / `/dream-log` / `/dream-restore` — 完整记忆管理三件套

### 改良版命令

你有 `/new`, `/help`, `/tasks`, `/reload`, `/status`, `/kb` 等，但没有 `CommandRouter` 架构，命令路由硬编码在 `commands.py` 的 if-elif 链中。

---

## 八、并发与可靠性

### 上游优势: 并发控制更成熟

```python
# 上游 AgentLoop.__init__
self._concurrency_gate: asyncio.Semaphore | None = (
    asyncio.Semaphore(_max) if _max > 0 else None
)
self._session_locks: dict[str, asyncio.Lock] = {}
```

- **Session 串行化**: 同一 session 的请求通过 `asyncio.Lock` 串行执行
- **跨 session 并发限制**: `Semaphore` 控制最大并发请求数
- **Task 调度**: 每个消息 `asyncio.create_task`，`/stop` 可以精确取消
- **后台任务追踪**: `_background_tasks` 列表 + `_schedule_background`，关机时 drain

你的改良版**完全没有**显式的并发控制——同一 session 的并发请求可能导致竞态。

### 上游优势: Runtime Checkpoint (断点续传)

上游实现了 [runtime checkpoint](file:///D:/Python/HKUDS/nanobot/nanobot/agent/loop.py#L691-L761)：
- 工具执行前将当前状态持久化到 session metadata
- 如果进程崩溃/重启，下次请求时自动恢复未完成的工具调用
- 给未完成的工具注入 "Error: Task interrupted before this tool finished" 提示

你的改良版没有此功能。

---

## 九、消息上下文管理

### 上游优势: 智能 Context Window 管理

上游的 `_snip_history`（runner.py L517-574）实现了基于 token 估算的智能裁剪：
1. 计算当前 prompt + tool definitions 的估计 token 数
2. 如果超过 `context_window_tokens - max_output - safety_buffer`，从旧消息开始丢弃
3. 确保裁剪后的消息序列从 `user` 消息开始（`find_legal_message_start`）

你的改良版使用固定的 `memory_window=50` 条消息窗口，对于 long-context 模型浪费，对于小窗口模型又可能溢出。

### 上游优势: 工具结果大小治理

上游有 `max_tool_result_chars`（默认 16000），对所有工具结果统一截断。还有 `_apply_tool_result_budget` 在每次 LLM 调用前重新检查历史中的工具结果大小。

---

## 十、代码质量与可维护性

### 上游优势: 更清晰的分层与模块化

| 指标 | 上游 | 改良版 |
|------|------|--------|
| loop.py 行数 | 780 | 1658 |
| 最大单方法行数 | ~110 (_process_message) | ~550 (_process_message) |
| 模块耦合度 | 低 (Runner/Hook/Loop 正交) | 高 (所有逻辑内联) |
| 类型注解完整性 | `from __future__ import annotations` 全局启用 | 部分文件无 |
| Dataclass 使用 | `slots=True` 优化 | 无 slots |

### 改良版优势: 更丰富的日志和可观测性

- [metrics.py](file:///d:/Python/nanobot/nanobot/utils/metrics.py) — 性能计时器
- Phase 22D Domain Events — 7 种类型化事件
- [trace_archive.py](file:///d:/Python/nanobot/nanobot/agent/trace_archive.py) — 失败任务完整追踪

---

## 十一、OpenAI 兼容 API

### 上游独有

上游有一个完整的 [api/server.py](file:///D:/Python/HKUDS/nanobot/nanobot/api/server.py)，提供 `/v1/chat/completions` 和 `/v1/models` 端点。这意味着上游可以被当作一个 **OpenAI 兼容 API 网关**使用，比如接入 Cursor、Continue 等 IDE 插件。

你的改良版完全没有此功能。仅有的 REST 入口是 Dashboard WebSocket。

---

## 十二、综合评判

### 上游核心优势 (你应该考虑吸收的)

1. **Hook/Runner 分层** — 最值得学习的架构模式，可以让你的所有 Phase 改造变成可插拔的 Hook
2. **并发控制** — Session 锁 + Semaphore 并发门
3. **Runtime Checkpoint** — 断点续传保障可靠性
4. **Token-budget Context 管理** — 替代你的固定消息窗口
5. **Dream + GitStore** — 记忆的版本控制和回滚能力
6. **OpenAI 兼容 API** — 极大扩展了集成能力
7. **更多通道** — Matrix / WeCom / 微信
8. **Provider 原生重试** — `chat_with_retry` 机制
9. **Tool 并发分批** — `_partition_tool_batches` 基于 `concurrency_safe` 标记

### 你的改良版核心优势 (上游没有的)

1. **7 层记忆架构** — 向量检索 + 知识图谱 + 反思 + 经验库，远超上游的 3 层
2. **4 层安全漏斗** — L0→L1→L3 + HITL + Sandbox，上游仅有基础 SSRF
3. **视觉/RPA 生态** — RPAExecutorTool, ScreenCaptureTool, BrowserTool, VLM 路由
4. **Loop 鲁棒性** — Circuit Breaker + Fuzzy Loop Detection + Trace Postmortem
5. **知识工作流** — 自动提取、匹配、Few-shot 适配、保存提示
6. **Outlook 集成** — Win32 COM 控制办公场景
7. **国际化 (i18n)** — 完整的多语言提示消息系统
8. **快速意图路由** — Phase 39 的 chitchat bypass 减少延迟

---

> [!TIP]
> **最佳策略**: 将上游的 **Hook/Runner 分层架构** 移植到你的项目，随后将你所有的 Phase 改造以 `AgentHook` 子类的形式重新挂载。这样既保留了你的全部功能优势，又获得了上游的架构可维护性和可扩展性——正是第二阶段 Critic 指出的方向。
