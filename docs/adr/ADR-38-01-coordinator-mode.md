# ADR-38-01: Coordinator Mode — Worker 子进程并发

> **状态**: Architecture Reserved (P3)  
> **日期**: 2026-04-06  
> **审核流程**: Harness 5 阶辩证工作流（Draft V1 → 极端批判 → 反思重构 → 正向校验 → 最终定稿）  
> **决策者**: 首席架构师 + Harness 辩证评审委员会

---

## 背景 (Context)

Nanobot 现已具备 `SubagentManager`（`subagent.py`）+ `SpawnTool`（`tools/spawn.py`），允许 LLM 通过 `spawn(task=...)` 工具在**同一 Python 进程的同一 asyncio 事件循环**中创建后台协程（`asyncio.create_task()`）。

这种"协程级并发"在绝大多数场景下工作良好，但存在以下固有上限：

| 限制 | 描述 |
|---|---|
| 共享 GIL / 事件循环 | 无法利用多核 CPU 并行计算密集型任务 |
| 无进程隔离 | Worker 崩溃或内存泄漏会直接影响主进程 |
| 共享内存 | 线程安全边界模糊，多写竞争不可避免 |
| 无法独立重启 | Worker 不可单独扩缩，只能随主进程重启 |

Phase 38 的目标是**探索真正的进程级隔离**，赋予 Agent 衍生独立 Worker 子进程的能力，实现不阻塞主会话的高并发异步任务委派。

---

## 决策历程 (Decision Journey)

### Draft V1 方案 (Planner)
- 提议：`asyncio.create_subprocess_exec()` + **stdout/stdin Pipe IPC**
- 缺陷：Worker 运行裸 `while` 循环（绕过 Onion Middleware），共享 workspace 文件存在多写竞争，LLM 可调用 `cancel` 越权停止进程，Windows 64KB Pipe 缓冲死锁。

### 极端批判 (Red Team)
- 核心攻击点：
  1. Pipe 在 Windows 的 64KB stdout 缓冲区死锁（无界输出时必现）
  2. Worker 绕过 Phase 41 Onion Middleware，成为安全逃逸后门
  3. 多进程并发写 JSON 文件，导致 Knowledge Store 数据损坏
  4. LLM 可无限 `spawn`，也可越权 `cancel` 任意 Worker
  5. 工期低估（Draft V1 估 10h，实际 40-50h）

### 最终架构决定 (Final Architecture)

经过 Harness 完整四轮辩证评审，最终采纳以下设计决策。

---

## 决策内容 (Decisions)

### 决策 1：IPC 协议 — HTTP JSON-RPC（替代 Pipe）

**问题**：Pipe IPC 在 Windows 上因缓冲区大小死锁，且 `SIGTERM` 不可用。

**决策**：Worker 子进程启动时绑定一个随机空闲端口，启动轻量 HTTP 服务（aiohttp）。主进程通过 `localhost:PORT` + Secret Token 鉴权与 Worker 通信。

```
Master → POST /task   (下发任务)
Master → GET  /status (心跳轮询)
Master → GET  /result (拉取结果)
Master → POST /shutdown (优雅退出)

Worker → POST /register (启动后上报端口给 Master)
```

**Trade-off**：引入 HTTP 服务有 ~5ms 的延迟开销，但彻底消除了 Windows Pipe 死锁风险，且允许未来扩展为真正的分布式 Worker（跨机器）。

---

### 决策 2：Worker 必须完整加载 Onion Middleware V2

**问题**：裸 `while` 循环 Worker 绕过了 Phase 41 建立的所有安全中间件（CircuitBreaker、HITL、FloodGuard、L1 规则）。

**决策**：Worker 子进程内部必须调用 `_run_agent_loop_v2()`（洋葱管线），不允许使用裸循环。

Worker 与主 Agent 的区别仅在于：
- System Prompt 更聚焦（专注于单一子任务）
- 工具集受限（无 `spawn`、无 `message`、无 `coordinator`）
- 文件系统操作强制在沙箱目录内

---

### 决策 3：沙箱隔离法则 (Sandbox Rules)

**问题**：多进程并发写 `workspace/knowledge/` 和 `workspace/memory/` 下的 JSON 文件，导致数据损坏。

**决策**：

```
全局状态（只读）:
  - TaskKnowledgeStore  →  ReadOnlyKnowledgeStore 适配器（拦截所有 add_/update_ 方法）
  - VectorMemory (Chroma) →  只读查询，禁止 ingest_text()
  - ReflectionStore     →  只读

沙箱目录（读写）:
  workspace/workers/<worker_uuid>/
    ├── output.json     # Worker 最终结果
    ├── scratch/        # 临时文件
    └── logs/           # Worker 内部日志
```

Worker 完成后，主 Agent 读取 `output.json` 并决定是否将结果同步回全局状态。

---

### 决策 4：LLM 权限约束

**问题**：LLM 可无限 `spawn` Worker，也可越权 `cancel` 进程。

**决策**：
- **移除 `cancel` 操作**：LLM 无法取消 Worker。只有人类用户通过 `/cancel <worker_id>` 命令下达取消指令。
- **`spawn` 强制 HITL**：`CoordinatorTool` 实现 `get_risk_tier() → RiskTier.MUTATE_EXTERNAL`，任何 spawn 操作必须经人类审批。
- **`max_workers` 上限**：配置驱动（默认 4），超限时排队或返回错误。

---

### 决策 5：优先级降级 P2 → P3

**问题**：Draft V1 估计 10h 工期，实际由于 Windows IPC 调试、安全中间件同步、沙箱隔离实现，真实工期为 40-50h。当前协程并发（`subagent.py`）尚未出现实测瓶颈。

**决策**：降级为 **P3 Architecture Reserved**。

**触发条件**（满足任意一条时启动实际编码）：
1. 协程并发实测导致主会话 P75 延迟增加 >2 秒
2. 出现需要真正并行（非串行）多任务的用户场景
3. Phase 41 Onion Pipeline 稳定运行 30 天无重大 Bug（稳定性背书）

---

## 最终架构蓝图 (Architecture Blueprint)

```text
┌─────────────────────────────────────────────────────────┐
│              Master Agent (Main Process)                │
│                                                         │
│  ┌──────────────┐    ┌────────────────────────────────┐ │
│  │ CoordinatorTool │   │  CoordinatorManager            │ │
│  │  (HITL触发)   │──▶│  ├── spawn_worker()            │ │
│  └──────────────┘   │  ├── WorkerRegistry             │ │
│                      │  └── ResultCollector            │ │
│                      └────────────┬───────────────────-┘ │
│                                   │ HTTP JSON-RPC         │
│                           localhost + Secret Token        │
└───────────────────────────────────┼─────────────────────-┘
                                    │
              ┌─────────────────────▼──────────────────────┐
              │         Worker Process (独立子进程)          │
              │                                             │
              │  python -m nanobot.worker                   │
              │    --port 0                                 │
              │    --token <secret>                         │
              │    --trace-id <conversation_id>             │
              │                                             │
              │  ┌──────────────────────────────────────┐  │
              │  │  _run_agent_loop_v2() (完整洋葱管线)  │  │
              │  │  + ReadOnlyKnowledgeStore             │  │
              │  │  + 受限 ToolRegistry (无 spawn)        │  │
              │  │  + 沙箱 workspace/workers/<uuid>/      │  │
              │  └──────────────────────────────────────┘  │
              └─────────────────────────────────────────────┘
```

---

## 待实现文件清单 (When Triggered)

| 文件 | 类型 | 说明 |
|---|---|---|
| `nanobot/agent/worker_process.py` | NEW | Worker 子进程入口点 + HTTP 服务 |
| `nanobot/agent/coordinator.py` | NEW | `CoordinatorManager`（进程池 + 注册中心） |
| `nanobot/agent/tools/coordinator.py` | NEW | `CoordinatorTool`（HITL + spawn/list） |
| `nanobot/agent/knowledge/readonly_store.py` | NEW | `ReadOnlyKnowledgeStore` 适配器 |
| `nanobot/config/schema.py` | MODIFY | 新增 `CoordinatorConfig` |
| `config.sample.json` | MODIFY | 新增 `coordinator` 配置块 |
| `nanobot/agent/loop.py` | MODIFY | 条件注册 `CoordinatorTool` |
| `tests/test_coordinator.py` | NEW | 进程启动 + IPC + 沙箱隔离集成测试 |

---

## 配置模板 (Config Schema)

```jsonc
{
  "agents": {
    "coordinator": {
      "enabled": false,           // 灰度开关，默认关闭
      "max_workers": 4,           // 并发 Worker 上限
      "worker_timeout": 300,      // 单 Worker 超时（秒）
      "heartbeat_interval": 10,   // 主进程轮询间隔（秒）
      "sandbox_root": "workspace/workers",  // 沙箱根目录（相对 workspace）
      "ipc_mode": "http"          // 未来可扩展为 "grpc"
    }
  }
}
```

---

## 后果 (Consequences)

**正面**：
- 真正的进程隔离，Worker 崩溃不影响主进程
- 多核 CPU 可并行利用
- 完整的安全中间件保护
- 清晰的沙箱边界，零数据竞争

**负面 / Trade-off**：
- 引入进程启动开销（~0.5-1s）
- HTTP IPC 有轻微延迟（~5ms，可忽略）
- Worker 初始化需要重新加载配置和工具（内存换安全）
- 实现复杂度显著高于协程方案

---

*归档时间：2026-04-06 | 辩证流程：Harness V1.0 | 最终定稿：Claude Sonnet 4.6 (Thinking)*
