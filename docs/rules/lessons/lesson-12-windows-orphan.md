# Windows 进程树孤儿灾难 (Windows Process Tree Orphan Disaster)

// Added: Phase 40B

在实现类似 `Coordinator` 模式的跨进程真并发调度时，如果只保留 Python 的 `Popen` 对象而不加以系统级脱离挂载（如 `CREATE_NEW_PROCESS_GROUP`），当主 Agent 意外崩溃或被强杀 (Ctrl+C) 时，会直接导致派生的大量 Worker 进程变为孤儿留守在后台，引发可怕的端口占用和 API 请求泄漏（资源风暴）。

**避坑指南**：在涉及长期进程分离（Daemon-like Subprocess）时：
1. 必须在 `Popen` 唤起时附带系统级的 `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` 控制解绑（限 Windows，Unix 下使用 `start_new_session=True`）；
2. 必须在架构入口硬编码 `atexit.register` 注册全局清理程序；
3. 不能仅仅用 Python 层面的 `process.kill()`，必须彻底用 `taskkill /F /T /PID` (Windows) 或发送 `SIGTERM` 给整个进程组来强制切断子树。
