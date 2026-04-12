# Phase 48 专项人工测试指南 (Dashboard Config Editor UI)

本指南详述了针对 Phase 48 (Dashboard 配置编辑器) 的功能验收方法。通过本手册，你可以模拟实际管理员操作，验证敏感字段脱敏、前端数据合并、乐观锁防冲突以及能力覆盖面具（Capability Overrides）等高阶安全性功能。

## 测试前置条件
1. 确保最新网关服务已重启：`nanobot gateway --verbose`
2. 打开浏览器方位 Dashboard：`http://localhost:18790/?token=你的令牌`（如果配置了 token）
3. 确保目录 `~/.nanobot/` 下（或通过环境变量指定的应用路径中）存在 `config.json` 文件。

---

## Part 1: 数据流转与底层脱敏机制 (Masking & Seamless Sync)

### 验证指标
用户在 Dashboard 可以无缝地查阅包含机密信息的配置源（如 LLM 的 API-Key），但绝对不能将机密文本的散列暴露在网页控制台上。后端深层合并机制应该保证在修改别的一般设置时，并不会误将屏蔽符覆盖进真配置环境。

### 操作步骤

**1. 查验前端脱敏保护 (UI-Level Redaction)**
在浏览器进入 "⚙️ Configuration" 选项卡，点击进入 **Raw JSON** 模式。
向下检索涉及类似 `openai`, `slack`, 或任何包含 `api_key`/`token`/`secret` 对应键的位置。
- **期望结果**：这些敏感字符串均被严格替换为 `__MASKED__`。原始 Key 并未泄露。

**2. 进行安全无关参数调优 (Safe Field Modification)**
在同一个 Raw Textarea 编辑器内，故意去修改一些普通行为选项：
尝试查找 `agents -> defaults -> session_expiry_hours` 并将其随意修改成一个不同的数字（如 `36` ）。

不要触碰任何呈现为 `"__MASKED__"` 的密钥字符串，保持原样。

**3. 触发深层合并写回 (Trigger Deep Merge Save)**
点击底部的 **Save Config**。
- **期望结果**：右下角弹框提示 `✅ Configuration saved & backed up!`。

**4. 后端落盘终态核验 (Backend True Data Verification)**
在 IDE 等独立文本引擎中手工打开服务器本机上的 `config.json` 真实文件：
- **期望结果**：你会看到刚被修改的 `session_expiry_hours` 已更新。而诸如 `api_key` 的原本真实密钥并未被灾难性改写成 `"__MASKED__"`！系统已经完美实现了智能深层合并。

---

## Part 2: 乐观锁防止幽灵覆盖 (Optimistic File Locking `409 Conflict`)

### 验证指标
当两名管理员在两个地方同时试图操控 Agent 的配置内核，或因为某种自动化脚本篡改了基座文件时，系统的 `version_hash` 能精准掐断并拒绝本次变更，以此消除多核状态下的配置迷失。

### 操作步骤

**1. 构造多端争斗快照 (Staging The Concurrency Context)**
在这个浏览器开启 **Tab A**，进入 Config Editor 的 Visual 页面界面，保持界面不动。不要点提交。

**2. 模拟暗箱截胡修改 (Backdoor Manipulation)**
你可以在文本编辑器（或干脆新开启一个独立浏览器 **Tab B** 并 Save Config 一次），在代码外面对 `config.json` 进行任意一种属性修改并主动保存它。这就使得 `config.json` 在 OS 等级的 `mtime` （文件修改时间发生位移）突变了。

**3. 进行灾难覆写的末路发车 (Doomed Save Attempt)**
回到之前驻足在浏览器里的 **Tab A**，尝试点下 **Save Config**。

- **期望结果**：此时界面会弹出红牌敬告语：`❌ Save failed: Config modified externally (Optimistic Lock). Reloading...`，随即你的面板数据自动刷洗成被人刚刚背后更新过的最新文本。修改指令在 `app.py` 中被 `409` 完美强杀阻截。

---

## Part 3: Sandbox 等级标签 Widget 系统整合 (UI Capability Overrides)

### 验证指标
原先仅能以极客形式利用底层比特掩码叠加输入的 Tool Capability Overrides (`{"exec": 128}`) ，现被整合至动态生成的打钩多选项列表里，并具备硬性的危险边界告知能力。

### 操作步骤

**1. 初窥 Sandbox 特效掩码转换**
位于 Visual Editor (可视化) 视图，寻找 `Sandbox Capability Overrides` 卡片卡位。
在下拉菜单中选中工具 `exec` (如果不存在可以自行下拉选择或者手动在 Raw 加入保存后在此处选取)。
- **期望结果**：你能看到 `SHELL_EXECUTION`, `CODE_EVALUATION` 等人类可读属性已展位呈现。你也可以通过底部当前掩码实时读数（如：1）知道目前组合权限。

**2. 引爆 High-Risk 工具权限激活弹窗 (The Confirmation Defense-Line)**
在多选列表中，勾选带有红圈的 `🔴 High Risk! ⚠` 能力（如：**DESTRUCTIVE** 强破坏指令、 **UNTRUSTED_EXTERNAL** 外部不信任输入源指令）。

- **期望结果**：浏览器会弹出严重的阻塞型确认弹窗框：`WARNING: Enabling DESTRUCTIVE is a HIGH RISK operation! ...`。
- 如果点取消：复选框自动重置跳回；点确定则成功点亮。

**3. 落盘数据形态自洽验证**
在此状态下立刻点按 **Save Config**。接着回到 Raw JSON (或者后台看文件)，定格在 `agents -> sandbox -> capability_overrides -> "exec"`，确认此刻该工具已经由一串整型数值绑定了！

---

## 🛑 Lessons Learned (架构测试大坑复盘)

如果在本指南的操作流程中发现任何脱轨或无反应异象，请遵循我们在开发此次新版本踩出的坑：

1. **`__MASKED__`的二次合并陷阱 (Hijacking Blind Spot)*: 在早期实验时，我们曾误将通过 `json.loads()` 拉起的字典盲目通过 Pydantic 推倒重构。导致原厂 `API_KEY` 通通遭灭门！目前的 API 规范要求执行前必须穿越 `app._deep_merge()` 黑屋过滤，将属于 Sentinel （如脱敏词）的值剔出替换队列。
2. **Javascript Fetch 竞态时停 (The Double Fetch)**: 每次遇到 409，或是 Save 成功以后。JS 中的 `fetchConfiguration()` 必须挂载 await。系统将第一时间更新其局部单例级的 `version_hash`。如果不更新（旧的 hash 长驻 JS 内存），你后续点的任何以此都是 `409 失败`，让人产生幻觉“为什么我永远也进不去了”。
3. **不可忽视的重启隔离锁 (Restart Requirement)*: 在修改所有有关大模型基础配置以后，弹窗的黄条会显示：“⚠️ App Restart Required”。目前出于轻量结构考量，系统暂未引入全栈事件总线的订阅热重载机制 (ConfigChangeEvent)，因此所有的架构性修改仅对 `loader.get_config` 读取有实切影响。务必在最后关停控制台再进行 Agent 测试核对。
