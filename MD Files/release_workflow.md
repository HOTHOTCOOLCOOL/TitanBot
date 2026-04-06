# 📦 Nanobot 绿色整合包·发版与接引手册 (Portable Release Guide)

这份文档旨在梳理由我们的“物理隔离架构 + TUI引导系统”所催生的全新发版工作流。请妥善保存此文档作为您每次发版推广前的 SOP (标准作业程序)。

---

## 一、开发者（您）的发版打包流程 
**场景**：代码写完，准备把它发给群里的普通小白测试。

### 📌 步骤 1：构建独立黑盒环境 (Runtime)
打开项目根目录的终端，执行我们打造的自动化工厂脚本：
```bash
python build_portable_runtime.py
```
* **发生了什么**：系统会在本地瞬间下载一个极简版的绿色 Python，解开官方封印并强力注入清华源，最后将所有依赖安装在根目录的 `runtime` 文件夹里。
* **验收标准**：能在根目录看到 `runtime` 文件夹即可。

### 📌 步骤 2：封装巨大资产 (Models / Browsers) *【可选，但强推】*
为了让用户连网都不用连就能直接用（真纯离线），您需要把大本营搬进来：
1. **浏览器沙盒**：
   在 CMD 依次执行：
   ```cmd
   set PLAYWRIGHT_BROWSERS_PATH=.\browsers
   playwright install chromium
   ```
   随后项目里多出 `browsers` 文件夹。
2. **RAG 向量大模型**：
   在根目录自建 `models/sentence-transformers/bge-m3`，把几十个 G 的模型切进来。

### 📌 步骤 3：扫除隐私，打磨装箱 (Zip)
这步最关键！在发给别人之前：
1. 检查有没有自己上次跑出来的 `user_data` 目录（有的话一定要**删掉**，因为那里有你的 API Key 和私聊数据）。
2. 将包含了代码、`runtime`、`browsers`、`models` 的最外层大文件夹，右键使用 7-Zip 或 WinRAR 打包成 `Nanobot-v1.0.zip`。
3. **完成！这就是最终的“整合包”！你可以扔给网盘分享出去了。**

---

## 二、无技术小白的开箱极爽体验 
**场景**：小白用户从网盘下载了您的几十 G 整合包，他的电脑连 Python 是什么都不知道。

### 🚀 第一步：解压缩
小白随意解压在硬盘某个地方打开，不需要去配置任何什么叫环境变量的鬼东西。

### 🚀 第二步：双击 `start_portable.bat`
这是唯一的指定动作！双击之后：
* 脚本底层识别到存在 `runtime`，立刻物理跨过系统的干涉，用内建的隔离生态起飞。
* 并在自己身边拉出警戒线：`NANOBOT_HOME`。

### 🚀 第三步：遇到“新手指引向导弹窗”
因为大礼包里被您删除了 `user_data`，这是小白第一次启动，系统检测不到配置文件。此时它**不会报错闪退**！而是卡在终端屏幕中间弹出一行优雅的提示：
```text
✨ Welcome to Nanobot Command Center! ✨
It looks like you're starting this for the first time (no API key detected).

[1/2] Please paste your Openai API Key to continue (or press Enter to skip):
```
小白看懂了，把在淘宝买的 Key “啪”地一粘贴，回车。
```text
[2/2] Which model would you like to use? [claude-3-opus-20240229]: 
```
再回车跳过。

然后下面就会瞬间刷过绿色的日志：
`[green]✓ Setup complete! Launching Gateway and services...[/green]`

### 🚀 第四步：随意带走不出血
从此以后，小白每天关机再双击打开，都会毫秒级直通网关。而且有一天他不想要了，右键这个 Nanobot 文件夹一删干干净净，C 盘连 1kb 的残留文件都不会有！
