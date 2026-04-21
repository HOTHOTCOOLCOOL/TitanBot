# 沙箱网络审计钩子的盲目运用（Blind Network Auditing in Sandboxes）

// Added: Phase 45C (参见 ADR-45)

在对 Worker 进程（如 Coordinator Worker）应用防御式的 `sys.addaudithook` 拦截网络套接字（`socket.bind`/`socket.connect`）前，必须彻底厘清目标进程的业务职能。对于单纯执行一段不受信纯计算代码的容器（无 IPC，无三方依赖），严格断网是正确的；但对于需要依靠 HTTP 微服务框架（如 `aiohttp`）等待 IPC 任务派发，且内部包含 Agent 推理大回环（需直直连 LLM API）的调度进程，直接植入 `-I` 并拦截其内核层的 `socket.bind` 将立刻导致初始化死亡（Windows `ProactorEventLoop` 对自组环回的心跳依赖），同时也会让 Agent 因报错不可达变成聋瞎。

**避坑指南**：切忌在架构高层落实「为了安全彻底切断子进程网络」这种不切实际的“一刀切”。真正的防线应该部署在**不受信子动作触发前隙**（如隔离的 `PythonSandbox` 或 `ShellSandbox`），而不是在承担基础设施职责的调度进程顶端自残。对于核心系统 Worker，安全策略必须止步于拦截恶意原生的 `os.system` / `os.exec` 等越权动作，明文豁免 Socket 以保留其生命血脉。
