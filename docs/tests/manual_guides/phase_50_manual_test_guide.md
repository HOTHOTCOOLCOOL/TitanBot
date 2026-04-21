# Phase 50 人工测试手册 (Knowledge Graph Wiki Export)

本指南旨在指导测试人员（无论技术背景）如何从头到尾进行完整且严谨的系统验证。

## 理论与功能背景
Nanobot 已经具备一种深度的内部知识追踪能力，但所有内容都被存放在无法舒适阅读的 `.json` 后端文件中。本次功能（Wiki Export）提供了一项特性：将底层晦涩复杂的知识记录，在**后台自动**转换为格式优美、可以被 Obsidian 工具直接索引、且人类可以直接阅读的结构化 Markdown (.md) 文件集合，同时保证绝不拖慢系统运行。

---

## 测试步骤一：配置门阀验证 (Configuration Toggle Check)

**目标**：确保开关开启后，系统才会开始转储知识，验证默认关闭时的零影响。

1. 进入 Nanobot 终端执行: `nanobot onboard` (保持刷新默认选项) 或直接打开你的 `~/.nanobot/workspace/config.json` 或由 Dashboard Configuration 面板。
2. 将 `wiki_export: false` 修改为 `wiki_export: true`，保存配置并**重启网关** (Restart Gateway: `nanobot gateway`)。
3. 观察控制台输出，是否有任何报错信息。如果没有报错信息并正常看到 `Web Dashboard` 的字样，证明服务配置验证通过。

## 测试步骤二：API和 Dashboard 互动验证

**目标**：证明用户界面是否成功并入本次新特性，并能被成功调用。

1. 打开浏览器进入: `http://127.0.0.1:18790`，可能需要输入生成的后台 token，进入 Dashboard。
2. 侧边栏点击选取 **"Knowledge Base"** （知识库）面板页面。
3. 查找是否出现了一个新的模块：**Knowledge Graph Wiki Export (Phase 50)**。
4. 验证内容应包括：
   - 当前的状态显示 (如："Status: ...")
   - 一个【Sync to Markdown】按钮。
5. 点击该按钮。
6. **期待结果**：
   - 按钮右侧能弹出浮窗提示 (`✅ Wiki synced! ...`)。
   - 紧靠按钮的文字会立刻转换并显示最近一次更新的时间戳 (如：Status: Synced (Last: XXXX))。

## 测试步骤三：底层静态文件与格式生成检查

**目标**：验证导出的实体与数据格式是否符合极客需求，是否防串改。

1. 打开你的文件管理器，导航至系统的存放主仓： `workspace/wiki/` 目录。（取决于 `nanobot` 文件夹所映射的位置）。
2. 核对此文件夹中应该自动出现四个东西：
   - `_index.md` 索引文件
   - `_log.md` 日志文件
   - `entities/` 文件夹（知识图谱实体）
   - `directives/` 文件夹（经验防范指引）
3. 随便点开 `entities/` 里任意生成的一个文件（例如如果 Agent 之前记忆过任何人物信息，此处名字应该是具体名字如 `Apple.md` 或其他记忆对象）。
4. **期待结果**：
   - 顶部应该有一堆 YAML 的表头：如 `aliases`, `updated`, `type: "kg_entity"`
   - 其中会出现一张规整的 Markdown 表格，如：
   `| Predicate | Target | Context |`
   - 开头存在一个极其明显的 `> [!WARNING]`，表明其是一份只读副本。

## 测试步骤四：终端快捷调用验证

1. 保持 Gateway 服务后台运行状态。
2. 重新开启一个新的 Powershell 终端并切入虚拟环境。
3. 发送 CLI 命令：`nanobot wiki sync` 或是 `nanobot wiki sync --force` 
4. **期待结果**：
   - 屏幕上将打印：
     `Syncing Knowledge to Markdown Wiki...`
     `✓ Sync complete at ...`
     并罗列出导出的 `Entities` 和 `Directives` 的数目字。

如果四大步所有“期待结果”均通过，证明此系统已 100% 被完成并落地成功，准许通过此 Release！
