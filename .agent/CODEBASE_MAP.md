# Nanobot Total Map — L0 Router

> **唯一 L0 入口点**。任何 Agent 新会话必须首先且仅能首发读取本文件。
> Last updated: 2026-03-26

## 1. Project Mission (项目是什么)

Nanobot 是一套企业级个人 AI Agent 系统，采用“Simple loop, smart tools”的设计哲学（单 Agent Loop 架构，无多智能体编排）。它从简单的聊天机器人演进而来，现已支持多通道消息（Telegram/微信/飞书/Discord等）、7层记忆架构、知识萃取与图谱、Playwright 浏览器自动化与桌面级 RPA。

## 2. Context Routing (去哪里找什么)

> **强制路由指令 (MUST OBEY)**：**绝对禁止**列出文件树后尝试读取全部 `.md` 跟踪文件。你必须且只能根据下方指针，按需读取（`view_file`）解决你当前任务**必需**的对应 L1 层文档。

* **当前开发目标与任务**: 去读 `progress_report.md` （查看当前的 Phase、测试漏洞清单及待办清单）。
* **测试基线与覆盖**: 去读 `TEST_TRACKER.md` （查看当前回归线，确保不破坏系统）。
* **编写核心逻辑与工具**: 去读 `docs/rules/ARCHITECTURE.md` （修改代码前**必须**阅读，包含 5 大类严格的开发戒律）。
* **可用 Agent 工具总览**: 去读 `TOOLS.md`。
* **安全审计与权限**: 去读 `SECURITY.md`。
* **命令行运维与部署**: 去读 `OPERATIONS.md`。

*(注：所有过期的演进流水账、旧日测试细节、架构反思演变史已全部归档至 `docs/archive/`。通常情况下 Agent 在新会话中**永远不需要**去读取该冷库目录。)*

## 3. Current State Vector (目前系统状态切片)

**Phase 30 已完成** (弱模型防护 Weak Model Safety Guards) | 当前基线：回归测试 passed 1209+。
> 下一开发方向请立即路由访问 `progress_report.md`。
