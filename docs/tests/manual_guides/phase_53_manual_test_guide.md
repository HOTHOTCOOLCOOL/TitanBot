# Phase 53 手工自测与验收指南 (Manual Test Guide)

本指南用于完全不懂技术的非开发人员或项目协作者对 **Excel OLAP 周报自动化 (ExcelActuatorTool)** 进行端到端的人工测试。
因涉及微软 OAuth 授权弹窗的自动处理及 OneDrive 排他锁问题，必须执行人工现场验收。

---

## 预置条件 (Prerequisites)

1. **环境准备**：确认你的机器处于 Windows 系统下。
2. **账号权限**：你拥有目标 Excel 文件的查看权限，并且当前运行 Nanobot 的设备上，系统或 Excel 已登录了 `dliu@valueretail.com` 的账户（这样才能有单点登录或快捷验证弹出）。
3. **目标文件**：文件必须存在且路径没有被重命名，即：文件应位于 `D:\OneDrive - VR Management (Shanghai) Co., Ltd\Projects\European Data Validation\EURO DATA CUBE CONNECTION Sales & FF.xlsm`。

---

## 测试场景 1：完全端到端自动化流程验证

本测试验证 Agent 是否能无感控制 Excel 刷新 Pivot 数据并自行吃掉弹窗。

### 操作步骤

1. 打开一个与 Nanobot 交互的聊天窗口（可为命令行、网页或微信）。
2. 让 Nanobot 执行数据抓取请求，你可以发送：
   > “帮我打开并刷新 `D:\OneDrive - VR Management (Shanghai) Co., Ltd\Projects\European Data Validation\EURO DATA CUBE CONNECTION Sales & FF.xlsm` 文件，然后返回 `Occupancy Details` Sheet 里的前 15 行营业数据。”
3. **观察行为**：
   - 系统应该会在后台自动打开 Excel。如果你没切到别的全屏，你应能短暂看到 Excel 窗口或其加载项刷新数据的画面。
   - 期间，如果由于 Azure OLAP Cube 触发了微软的**“权限/Account/登录”认证弹窗**。
   - **注意不要去点鼠标！** 请死死盯住弹窗，看看在 1~3 秒内，系统是否如鬼影般自动**点击了 `dliu@valueretail.com` 的账户**，并让弹窗自己消失。
   - 若弹窗未出现说明缓存尚在，如果出现并自己消失说明 Watchdog 生效。

### 预期结果 (Expected Results)

✅ Agent 不会报错 `PermissionError` (这意味着我们在 `SaveAs` 过程中规避了 OneDrive 冲突)。
✅ Agent 输出回复，包含提取出的 `Occupancy Details` 里的真实数据（通常是 CSV 格式的摘要，或由子代理处理后的一份漂亮的总结陈述）。

---

## 测试场景 2：副本生成检查 (OneDrive 避坑验证)

本测试验证工具是否确实绕开了对源文件的覆盖保存，确保 OneDrive 不因锁住而导致同步罢工。

### 操作步骤

1. 打开 Windows 文件资源管理器 (File Explorer)。
2. 导航进入你 Nanobot 的工作区下 `tmp` 目录，例如 `D:\Python\nanobot\workspace\tmp\` (如果你没有 workspace 可以在项目根目录下找找 `tmp` 文件夹)。

### 预期结果 (Expected Results)

✅ 里面应该存在一个新鲜生成（修改时间是此时此刻）的 `euro_cube_refreshed.xlsx` 文件。
✅ 打开该文件应当能看到它包含了刚才刷新后的最新数字，且原 OneDrive 里的 `.xlsm` 原文件的修改时间没有激进变动或报红叉。

---

## 如果遇到问题怎么排查 (Troubleshooting)

- 如果 Agent 报错 **`ModuleNotFoundError`** `pywinauto` 或 `pywin32`：确保你运行了 `pip install -e .[excel]` 装依赖。
- 若提示 **Hard timeout after 630s**：这说明 OLAP 请求网络严重卡住，或者出现了系统预期标题 `_POPUP_TITLE_PATTERNS` 以外的其他完全未知的异常弹窗。请将弹窗截图反馈以丰富我们特征黑名单。
- 如果发生找不到文件报错：请检查 OneDrive 同步客户端是否健康或文件路径是否更新。
