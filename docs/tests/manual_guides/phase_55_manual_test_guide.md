# Phase 55 Manual Test Guide: Excel COM Deadlock Recovery

本手册仅针对 **ADR-55 (Architecture Maintenance)** 中的 `COM 120s 超时触发 HITL 上报` 机制。

由于纯虚拟环境 (Unit Tests / Mock) 无法完全重现 Windows 系统底层的 COM 调用挂起、多进程 `PID` 管理以及跨进程句柄锁死的行为，这一项测试 **强制要求在物理桌面或生产环境中手工进行注入测试**，以确保我们的断路器 (Circuit Breaker) 有效且只会**精准猎杀**挂起的 Excel，绝不误伤用户正常的办公文件。

---

## 🎯 测试目标
1. 验证 `ExcelActuatorTool` 在遇到顽固的桌面模态弹窗（Modal Dialogs，导致 COM 彻底挂起）时，能否在超时后正确切断自己。
2. 验证超时后，底层机制能否通过精确锁定的 `PID` 回收对应的挂起进程 (`taskkill /PID`)。
3. 验证 **非受控 (Unrelated) 的 Excel 进程完全不受影响**，不存在以往的 `.kill()` 波及主进程或其他工作簿的问题。

---

## 🛠️ 前置准备

1. **环境**：确保处于 Windows 桌面环境，安装了正常的 Microsoft Excel。
2. **无关进程预热**：
   - 手动新建一个空白的 Excel 文件，随便输入几个字，**并保持它处于开启状态**（不要关闭）。
   - 这个文件代表"用户正常正在处理的工作簿"，将在整个测试中充当**无辜者对照组**。
3. **测试数据**：使用任何普通的 Excel 工作簿（例如随便新建一个 `test_deadlock.xlsx` 存放在 Nanobot 可以访问的目录下）。

---

## 🚀 执行步骤

### Step 1: 触发自动化流程
在 Nanobot CLI 控制台输入以下指令，强制其调用 `ExcelActuatorTool` 进行刷新操作（请替换实际文件路径）：

```plaintext
/exec excel_actuator(file_path="D:\\你想使用的任意Excel文件路径.xlsx", refresh_mode="full")
```

### Step 2: 实施“故障注入” (Fault Injection)
当屏幕上弹出 Nanobot 自动打开的那个 Excel 窗口（并开始执行某些操作时）：
1. 迅速将鼠标点向这个**由 Nanobot 拉起的 Excel 窗口**。
2. 随意点击某个菜单并故意打开一个**模态框**。
   - *提示：最简单的死锁方式是点击顶部菜单栏的 `数据(Data)` -> `数据验证(Data Validation)`，让那个设置对话框弹出来并停留在屏幕上。或者按下 `Ctrl+O` 停留在打开文件的页面。*
3. **不要关闭那个弹窗**，让它一直显示着。此时，背后的 Python COM 通道调用（`CalculateUntilAsyncQueriesDone` 或其他 API）已被彻底阻塞。

### Step 3: 等待并观察
1. 转到 Nanobot 的终端控制台。此时你应该看到它看似“卡住”了。
2. 耐心等待（由于测试中可能有宽限期，默认的超时 `_COM_HARD_TIMEOUT + 30` 可能会导致你需要等待较长时间。*提示：如果你在本地想快速测试，可以临时将 `excel_actuator.py` 中的 `_COM_HARD_TIMEOUT` 改为 10*）。

---

## ✅ 验收标准 (Definition of Done)

如果架构防御成功，你将观察到以下现象：

- [ ] **日志告警触发**：控制台输出类似 `ERROR - ExcelActuator: Hard timeout...` 或 `WARNING - ExcelActuator: force-killed Excel PID 12345 after timeout` 的日志。
- [ ] **进程精准回收**：之前被你手动用模态框卡住的这个特定的 Excel 窗口**瞬间消失**（被 `taskkill` 杀掉）。
- [ ] **全链路存活（最重要）**：
    - 你事前打开的**另一个无关的纯手工 Excel 文件（对照组）依然安然无恙地存活在屏幕上**。
    - **Nanobot 主进程没有崩溃退出**，而是向大模型优雅地抛出了一个 `Error: ExcelActuator timed out` 的回答。

如果在测试过程中，对照组 Excel 被误杀了，或者 Nanobot 主程序自己挂了，请立即停止并发起修复 Issue。
