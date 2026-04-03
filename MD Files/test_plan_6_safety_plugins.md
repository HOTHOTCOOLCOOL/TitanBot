# 🧪 Manual Test Plan — Part 6: Safety, Skills, Plugins & Integration

> **范围**: HITL / Sandbox / Skills / Plugins / MCP / Heartbeat / Task Tracker
> **预计耗时**: 4-6 小时

---

## 51. Smart HITL (`agent/hitl.py`)

### T51.1 — MUTATE_EXTERNAL 触发审批
| 项 | 内容 |
|---|---|
| **前置** | `hitl.enabled: true` |
| **步骤** | Agent 尝试 `outlook(action="send_email", ...)` |
| **预期** | HITL 暂停，发送审批请求到用户，显示 "🔒 High-Risk Action" |

### T51.2 — 用户 Approve
| 项 | 内容 |
|---|---|
| **步骤** | 对审批请求回复 "✅" / "approve" / "yes" |
| **预期** | 操作继续执行，audit trail 记录审批 |

### T51.3 — 用户 Reject
| 项 | 内容 |
|---|---|
| **步骤** | 对审批请求回复 "❌" / "reject" / "no" |
| **预期** | 操作取消，Agent 收到 "Operation cancelled by human reviewer" |

### T51.4 — 超时自动拒绝
| 项 | 内容 |
|---|---|
| **步骤** | 审批请求发出后不回复，等待超时 |
| **预期** | 超时后自动拒绝 |

### T51.5 — Approval Store 持久化
| 项 | 内容 |
|---|---|
| **步骤** | 检查 `workspace/memory/approvals.json` |
| **预期** | 历史审批记录被持久化 |

### T51.6 — READ_ONLY 不触发
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 `outlook(action="find_emails")` |
| **预期** | 不触发 HITL（READ_ONLY tier） |

---

## 52. Sandbox (`agent/sandbox.py`)

### T52.1 — Python AST Sandbox
| 项 | 内容 |
|---|---|
| **步骤** | Skill 包含 `import os; os.remove("file")` |
| **预期** | AST 扫描器检测到危险 import/call，阻止执行 |

### T52.2 — Shell 命令沙盒
| 项 | 内容 |
|---|---|
| **步骤** | exec 工具执行含 `curl` 向外部 POST 数据 |
| **预期** | L1 检测到 exfiltration pattern → 拦截 |

---

## 53. Skills Loader (`agent/skills.py`)

### T53.1 — Skills 自动发现
| 项 | 内容 |
|---|---|
| **步骤** | 检查 `workspace/skills/` 目录中有 SKILL.md 的文件夹 |
| **预期** | Agent 启动时自动发现并注册所有 skills |

### T53.2 — Skills 渐进式加载
| 项 | 内容 |
|---|---|
| **步骤** | Context builder 中 skills 部分 |
| **预期** | 只注入 skill 名称和摘要，不注入完整内容（节省 tokens） |

### T53.3 — Skill 执行日志
| 项 | 内容 |
|---|---|
| **步骤** | Agent 使用 skill 完成任务 |
| **预期** | `workspace/memory/skill_executions.json` 记录执行信息 |

### T53.4 — Skill Categories
| 项 | 内容 |
|---|---|
| **步骤** | Skills 是否按 category 分组（system, user, bundled） |
| **预期** | 不同 category 的 skill 有不同加载优先级 |

---

## 54. Skill Config & Hooks

### T54.1 — Skill Config (config.json 覆盖)
| 项 | 内容 |
|---|---|
| **步骤** | Skill 有 `config.json`，用户在全局 config 中覆盖 |
| **预期** | 用户值覆盖 skill 默认值 |

### T54.2 — Pre/Post Hooks
| 项 | 内容 |
|---|---|
| **前置** | Skill 有 `hooks.py` with `pre_execute` / `post_execute` |
| **步骤** | 执行该 skill |
| **预期** | Pre-hook 在执行前运行，Post-hook 在执行后运行 |

### T54.3 — Hooks AST 安全扫描 (P24)
| 项 | 内容 |
|---|---|
| **步骤** | hooks.py 中有 `import subprocess` |
| **预期** | AST 扫描器检测到并警告 |

---

## 55. Plugin Loader (`agent/plugin_loader.py`)

### T55.1 — MCP Server 注册
| 项 | 内容 |
|---|---|
| **前置** | config.json 中 `tools.mcpServers` 有配置 |
| **步骤** | 启动 Agent |
| **预期** | MCP 工具出现在工具列表中 |

### T55.2 — Hot Reload (/reload)
| 项 | 内容 |
|---|---|
| **步骤** | 添加新 MCP server 到 config → `/reload` |
| **预期** | 新工具注册，旧工具保持不变 |

### T55.3 — Plugin 错误隔离
| 项 | 内容 |
|---|---|
| **步骤** | MCP server 无法启动（如 command 路径错误） |
| **预期** | 只影响该 plugin，Agent 正常运行 |

---

## 56. SSRF Protection (总结)

### T56.1 — web.py 层
| 项 | 内容 |
|---|---|
| **步骤** | 列举被阻止的 URL 类型 |
| **预期** | 127.0.0.1, 10.x, 172.16-31.x, 192.168.x, 169.254.x, ::1, metadata endpoints |

### T56.2 — browser.py 层
| 项 | 内容 |
|---|---|
| **步骤** | browser(action="navigate", url="http://[::1]/") |
| **预期** | IPv6 loopback 也被拦截 |

### T56.3 — DNS Rebinding 防护
| 项 | 内容 |
|---|---|
| **步骤** | 使用域名解析到 127.0.0.1 的 URL |
| **预期** | Resolved IP 检查拦截 |

---

## 57. MCP Integration

### T57.1 — Stdio 模式 MCP
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `npx -y @modelcontextprotocol/server-filesystem` |
| **预期** | Agent 可以使用 filesystem MCP 工具 |

### T57.2 — HTTP 模式 MCP
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `url: "https://mcp-server.example.com/sse"` |
| **预期** | 通过 SSE 连接远程 MCP server |

### T57.3 — MCP 工具调用参数映射
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 MCP 工具 |
| **预期** | 参数正确映射为 MCP 协议格式 |

---

## 58. Heartbeat & Proactive (`heartbeat/`)

### T58.1 — Cron 定时执行
| 项 | 内容 |
|---|---|
| **步骤** | 添加一个每 60 秒执行的 cron 任务 |
| **预期** | 60 秒后自动触发 |

### T58.2 — 主动唤醒
| 项 | 内容 |
|---|---|
| **步骤** | 检查 heartbeat 配置 |
| **预期** | Agent 按配置的间隔主动检查任务队列 |

---

## 59. Task Tracker

### T59.1 — /tasks 命令
| 项 | 内容 |
|---|---|
| **步骤** | 发送 `/tasks` |
| **预期** | 列出当前 task queue，含状态和最近执行结果 |

### T59.2 — 任务状态生命周期
| 项 | 内容 |
|---|---|
| **步骤** | 观察一个任务从 `pending → running → done` 的全过程 |
| **预期** | 状态正确转换 |

### T59.3 — Silent Steps (Phase 22D)
| 项 | 内容 |
|---|---|
| **步骤** | Agent 在任务中执行多步工具调用 |
| **预期** | 中间步骤被记录为 silent steps（`last_tool_calls`），不打扰用户 |

---

## 60. End-to-End 集成场景

### E2E-1 — 邮件处理全链路
| 项 | 内容 |
|---|---|
| **步骤** | "查看今天的邮件，下载第一封的附件，分析内容后把摘要发给我" |
| **预期** | `outlook.find_emails → outlook.get_attachment → attachment_analyzer → message` 链式调用 |

### E2E-2 — 浏览器降级全链路
| 项 | 内容 |
|---|---|
| **步骤** | "打开 XXX 网站，点击登录按钮"（选择器可能失败的场景） |
| **预期** | `browser → browser_use_worker → [FALLBACK_RPA] → screen_capture → rpa_executor` 降级链 |

### E2E-3 — 知识学习+召回
| 项 | 内容 |
|---|---|
| **步骤** | Session 1: "记住 XXX 的 API endpoint 是 https://api.xxx.com"。Session 2 (/new): "XXX 的 API 是什么？" |
| **预期** | 新 Session 中自动从知识库召回答案 |

### E2E-4 — HITL 审批链
| 项 | 内容 |
|---|---|
| **步骤** | "帮我把今天的报告发邮件给 boss@company.com" |
| **预期** | Agent 找到报告 → 准备邮件 → HITL 审批 → 用户 approve → 发送 → 确认 |

---

# 📋 全部测试区域索引

| 文件 | 范围 | 测试区域 | 用例数 |
|------|------|----------|--------|
| **Part 1** | Core Infrastructure | T1-T10 (Config, Provider, Session, Bus, CLI, Dashboard, Channel, i18n, Metrics, Background Tasks) | ~35 |
| **Part 2** | Agent Loop & Intelligence | T11-T20 (Loop, Tool Registry, Context, Commands, Wait/Fake, Circuit Breaker, Loop Detection, VLM, Streaming, Subagent) | ~40 |
| **Part 3** | Memory & Knowledge | T21-T30 (Memory, Vector, MemoryMgr, Knowledge, KG, Reflection, Experience, Hybrid Retriever, Outcome, TaskKnowledge) | ~30 |
| **Part 4** | Tools Part 1 | T31-T40 (Filesystem, Shell, Web, Outlook, Attachment, MemSearch, Message, Cron, SaveSkill, SaveExperience) | ~40 |
| **Part 5** | Tools Part 2 & Verification | T41-T50 (Browser, Sessions, Trust, BrowserUse, ScreenCapture, RPA, Vision, L0, L1, L3) | ~40 |
| **Part 6** | Safety, Skills, Plugins | T51-T60 (HITL, Sandbox, Skills, SkillConfig, Plugin, SSRF, MCP, Heartbeat, TaskTracker, E2E) | ~35 |
| | | **总计** | **~220 用例** |

> **建议执行顺序**: Part 1 → Part 5 (L1 rules) → Part 4 (Outlook ⚠️) → Part 2 → Part 3 → Part 6
>
> **优先关注**:
> - 🔴 T34 (Outlook COM/DLL) — 你提到的已知问题
> - 🔴 T49 (L1 硬规则) — 安全关键
> - 🟡 T24.6 (Experience 阈值) — 已知隐患
> - 🟡 T44 (Browser-Use Worker CDP) — 最近多次调试的区域
