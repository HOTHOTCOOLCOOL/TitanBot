# Epoch 42 Evolution History (Phase 42)

## Phase 42A: SubagentManager 安全补丁 (P0)

### 诊断报告
**Harness 审查发现的真实 P0 漏洞**：`subagent.py` 的 `_run_subagent` 维护独立裸 `while` 循环，完全脱离洋葱中间件管线。内置 `ExecTool` 可在**彻底绕过 HITL 审批、FloodGuard、CircuitBreaker** 的情况下执行任意 Shell 命令，是当前架构中最高危的运行时漏洞。

### 修复细节
**修复方案**：废弃独立循环，通过 `_run_agent_loop()` Facade 复用完整中间件体系，配合受限 ToolRegistry（移除 `spawn/message/coordinator` 及 `exec`）+ 沙盒目录 `workspace/workers/<task_id>/` 进行隔离执行。

* 漏洞拦截机制升级：全面改写了 `TurnContext` 和各中间件节点，使之支持 `tool_registry_override` 下传机制，保障并发环境下的安全性。
* 添加了子代理专用的防御测试 (`tests/test_subagent_security.py`) 保证严格的访问控制。

## Phase 38: Coordinator Mode (Worker 子进程并发探索)

### 诊断报告
**单进程事件循环瓶颈**：原本基于 `asyncio` 的 `SubagentManager` 无法实现真正的多核解偶。当涉及到分析大文件、运行 RAG 构建或执行长效 RPA 时，容易发生事件循环阻塞，并在意外崩溃时导致 `main` 进程一起退出挂掉。同时写竞争风险加剧了知识库的损坏可能。

### 修复细节
**修复方案**：基于 `subprocess` 拉起隔离的 Popen Python 子进程，跑起极简 HTTP 引擎 (`aiohttp`) 提供 `/task` 和 `/result` 的 JSON-RPC 请求服务。

* **进程树挂载防孤儿**：在 `subprocess.Popen` 中使用了 `CREATE_NEW_PROCESS_GROUP` 并在主程序中挂载 `atexit` 进行系统级的 `taskkill /F` 防御，避免了 Windows 子进程后台逃逸引发的端口风暴。
* **数据沙箱拦截**：创建了 `ReadOnlyKnowledgeStore` 将所有写意图阻断并在主进程收束归档，保证 Worker 不会在并发期间破坏 Global Experience Store 的完整性文件。
* **强管控隔离**：子进程仍然强制流经包含 `HITLMiddleware` 和 `CircuitBreaker` 的 `_run_agent_loop_v2` 洋葱管道，并从工具库中完全剔除 `spawn/exec/message`。

## Phase 44: Cron Retry Engine & SSRS Hallucination Defense (ADR-44)

### 诊断报告
**状态机风暴与不可靠检测**：Cron 定时任务失败后发生无上限重试风暴，且 `AgentLoop` 只返回最终成功态，CronService 以单纯字符串匹配作为 Side-effect 依据，造成发完邮件 SSRS 报错后认为 "全体失败"，进而重复疯狂发信。其次，LLM (Sonnet) 会因 SSRS 失效进而疯狂产生找平幻觉用其他报表替代。

### 修复细节
**防线升级体系**：
* **结构化日志断言 (副作用核实)**：摒弃字符串推测机制，利用 `TraceArchive.dump_tool_calls` 为 `AgentLoop` 收口强制输出执行工具流，并在下一次 Cron retry 前强制扫描历史记录，探测是否成功打过真正的副作用工具 (`outlook.send_email`)，若是则挂入 `partial_success`。
* **重试熔断器 (`MAX_RETRIES=1`)**：引入强状态机管理 `retry_count` 与 `error_fatal` 状态标记，严防水滴式穿刺。
* **L1 Context-Aware 兜底防线 (`R-SSRS-001`)**：突破原有 L1 中间件盲区，通过向 L1 下发 `ctx.messages` 会话树，在检测到 SSRS 返回 `DependencyFatal` 时物理拦截任何 `outlook` 和替代数据的探测请求，勒令模型必须停机认输，从防线层剿灭幻觉。
