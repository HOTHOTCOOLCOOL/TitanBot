# Phantom Bugs in Background Sandboxes (完美逻辑却抓不到断点的玄学事件：幽灵崩溃与沙箱陷阱)

// Added: Phase 40B

人工测试 Crash Recovery 往往需要 Mock 长时阻塞任务（例如使用 `ping -n 55` 或 `python -c "sleep(100)"`）。**千万不要想当然地认为目标命令在 Agent 底层 subprocess 调用中的表现，等同于在你控制台 CMD 中的表现！**
这是因为：在沙箱隔离机制中，很多环境变量与 PATH 被剔除，甚至剥离了基础 TTY 与标准输入流。这就导致许多在你的 CMD 中能原生挂起阻塞 50 秒的命令，一旦进入沙箱就因缺少重定向对象或转义剥离瞬间报错并 **极速退出**（如 `python -c "sleep(100)"` 会因为外层 Shell 把内部双引号拿掉，抛出 `SyntaxError`）。
造成的直观后果是：系统认为命令立刻“成功执行结束了” -> 然后顺便非常完美地清除了 Checkpoint WAL 断点文件 -> 当你干掉进程重新启动以后，根本没有断点引发恢复，并让你产生“逻辑完美但就是抓不出来的玄学 Bug”的错觉！

**避坑指南**：当遇到恢复逻辑执行不到位的情况，首要原则是：**先去验证你的 Mock 阻塞是否真的在剥离环境的沙箱中成功挂起了！**建议使用能够免疫 IO 或权限特性的绝对命令，比如 `powershell -Command "Start-Sleep -Seconds 60"`，排除 Mock 进程光速自杀的干扰。
