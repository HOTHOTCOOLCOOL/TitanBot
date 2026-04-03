# 🧪 Manual Test Plan — Part 4: Tools (Part 1)

> **范围**: Filesystem / Shell / Web / Outlook / Attachment / Memory Search / Message / Cron / Save Skill / Save Experience
> **预计耗时**: 6-8 小时（Outlook 部分依赖 Windows + Outlook 桌面应用）

---

## 31. Filesystem Tools (`agent/tools/filesystem.py`)

### T31.1 — ReadFileTool
| 项 | 内容 |
|---|---|
| **步骤** | "读取 d:\Python\nanobot\README.md 的前 10 行" |
| **预期** | 返回文件头部内容 |

### T31.2 — ReadFile 不存在的文件
| 项 | 内容 |
|---|---|
| **步骤** | "读取 /nonexistent/file.txt" |
| **预期** | 返回 `Error: File not found` |

### T31.3 — WriteFileTool
| 项 | 内容 |
|---|---|
| **步骤** | "在 workspace 下创建 test_write.txt 内容为 hello" |
| **预期** | 文件被创建，内容正确 |

### T31.4 — EditFileTool (精确替换)
| 项 | 内容 |
|---|---|
| **步骤** | "将 test_write.txt 中的 hello 替换为 world" |
| **预期** | 精确替换成功 |

### T31.5 — ListDirTool
| 项 | 内容 |
|---|---|
| **步骤** | "列出 workspace 目录" |
| **预期** | 返回目录内容和文件元信息 |

### T31.6 — Workspace 限制 (restrict_to_workspace=true)
| 项 | 内容 |
|---|---|
| **前置** | 配置 `tools.restrictToWorkspace: true` |
| **步骤** | 尝试读取 workspace 外的文件 |
| **预期** | 被拒绝，返回错误 |

---

## 32. Shell/Exec Tool (`agent/tools/shell.py`)

### T32.1 — 基本命令执行
| 项 | 内容 |
|---|---|
| **步骤** | "运行 echo hello" |
| **预期** | 返回 "hello" |

### T32.2 — 超时 (默认 60s)
| 项 | 内容 |
|---|---|
| **步骤** | "运行 ping -n 100 localhost" (会超时) |
| **预期** | 60s 后返回超时错误 |

### T32.3 — 14 个 Deny 模式
| 项 | 内容 |
|---|---|
| **步骤** | 尝试 `rm -rf /`, `del /f`, `format`, `remove-item -recurse` |
| **预期** | 全部被拒绝，返回安全错误消息 |

### T32.4 — Workspace 限制 CWD
| 项 | 内容 |
|---|---|
| **前置** | restrict_to_workspace=true |
| **步骤** | 检查 exec 工具的 working_dir |
| **预期** | 工作目录为 workspace |

---

## 33. Web Tools (`agent/tools/web.py`)

### T33.1 — WebSearchTool (Brave Search)
| 项 | 内容 |
|---|---|
| **前置** | 配置 Brave Search API key |
| **步骤** | "搜索 Python 3.12 新特性" |
| **预期** | 返回搜索结果摘要 |

### T33.2 — WebSearchTool 无 API Key
| 项 | 内容 |
|---|---|
| **步骤** | Brave API key 留空，使用 web_search |
| **预期** | 返回友好错误提示 |

### T33.3 — WebFetchTool
| 项 | 内容 |
|---|---|
| **步骤** | "获取 https://example.com 的内容" |
| **预期** | 返回页面文本内容（HTML 转文本） |

### T33.4 — SSRF 防护
| 项 | 内容 |
|---|---|
| **步骤** | 尝试 fetch `http://127.0.0.1:8080` 或 `http://192.168.1.1` |
| **预期** | 被 RFC1918/SSRF 防护拦截 |

### T33.5 — PDF 自动检测
| 项 | 内容 |
|---|---|
| **步骤** | Fetch 一个 PDF URL |
| **预期** | 自动检测 PDF 类型并提取文本 |

---

## 34. Outlook Tool (`agent/tools/outlook.py`) ⚠️ Windows Only

> **⚠️ 前置条件**: Windows 系统 + Outlook 桌面应用已打开 + pywin32 已安装

### T34.1 — find_emails (收件箱)
| 项 | 内容 |
|---|---|
| **步骤** | "查看今天的邮件" |
| **预期** | 返回今天收到的邮件列表（index, subject, sender, attachments） |

### T34.2 — find_emails (子文件夹)
| 项 | 内容 |
|---|---|
| **步骤** | `outlook(action="find_emails", criteria={"folder": "inbox/Reporting"})` |
| **预期** | 正确导航到嵌套文件夹并返回结果 |

### T34.3 — find_emails (已发送文件夹)
| 项 | 内容 |
|---|---|
| **步骤** | `outlook(action="find_emails", criteria={"folder": "sent"})` |
| **预期** | 返回 Sent Items 中的邮件 |

### T34.4 — read_email
| 项 | 内容 |
|---|---|
| **步骤** | 先 find_emails，再 `read_email(email_index=0)` |
| **预期** | 返回完整邮件正文（Subject, From, To, CC, Body） |

### T34.5 — get_attachment
| 项 | 内容 |
|---|---|
| **前置** | 有附件的邮件 |
| **步骤** | find_emails → get_attachment(email_index=X, attachment_index=0) |
| **预期** | 附件保存到 temp 目录，返回路径和文件大小 |

### T34.6 — get_all_attachments
| 项 | 内容 |
|---|---|
| **步骤** | `get_all_attachments(email_index=X)` |
| **预期** | 所有文档附件被提取，跳过图片类型(.jpg, .png) |

### T34.7 — send_email ⚠️ 高危
| 项 | 内容 |
|---|---|
| **步骤** | "发送邮件给 test@test.com，主题 Test，内容 Hello" |
| **预期** | 邮件发送成功，日志记录 |
| **注意** | 此操作真实发送邮件！使用测试邮箱 |

### T34.8 — send_email 空收件人拦截
| 项 | 内容 |
|---|---|
| **步骤** | `send_email(recipient="", subject="test", body="test")` |
| **预期** | 返回 `Error: recipient is empty` |

### T34.9 — list_folders
| 项 | 内容 |
|---|---|
| **步骤** | `outlook(action="list_folders")` |
| **预期** | 返回 Inbox 下所有文件夹及子文件夹层级 |

### T34.10 — COM 线程安全 (asyncio.Lock)
| 项 | 内容 |
|---|---|
| **步骤** | 快速连续触发两次 outlook 操作 |
| **预期** | `_lock` 确保串行执行，不出现 COM 并发错误 |

### T34.11 — ⚠️ Outlook DLL/COM 初始化失败
| 项 | 内容 |
|---|---|
| **步骤** | 在 Outlook 未运行或 pywin32 未安装时调用 |
| **预期** | 返回 `Error: Failed to connect to Outlook:` 而非崩溃 |
| **注意** | **这是你提到的已知问题区域，重点验证！** |

---

## 35. Attachment Analyzer (`agent/tools/attachment_analyzer.py`)

### T35.1 — PDF 解析
| 项 | 内容 |
|---|---|
| **步骤** | 提供一个 PDF 文件路径进行分析 |
| **预期** | 返回 PDF 文本内容 |

### T35.2 — Word/Excel 解析
| 项 | 内容 |
|---|---|
| **步骤** | 分别提供 .docx 和 .xlsx 文件 |
| **预期** | 各自返回正确提取的文本 |

### T35.3 — 缺失依赖提示
| 项 | 内容 |
|---|---|
| **步骤** | 在缺少 `python-docx` 时分析 .docx |
| **预期** | 返回 `pip install python-docx` 安装指引 |

---

## 36. Memory Search Tool (`agent/tools/memory_search_tool.py`)

### T36.1 — store 操作
| 项 | 内容 |
|---|---|
| **步骤** | `memory(action="store", content="我的生日是1月1日", memory_type="fact")` |
| **预期** | 存储成功，返回确认消息 |

### T36.2 — search 操作
| 项 | 内容 |
|---|---|
| **步骤** | `memory(action="search", query="生日")` |
| **预期** | 返回包含 "1月1日" 的搜索结果，带相似度分数 |

### T36.3 — delete 操作
| 项 | 内容 |
|---|---|
| **步骤** | `memory(action="delete", key="<id>")` |
| **预期** | 删除成功 |

### T36.4 — 缺少 query 参数
| 项 | 内容 |
|---|---|
| **步骤** | `memory(action="search")` 不传 query |
| **预期** | 返回 `Error: query parameter is required.` |

---

## 37. Message Tool (`agent/tools/message.py`)

### T37.1 — 正常发送
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 message 工具发送回复 |
| **预期** | OutboundMessage 被 publish 到 Bus |

### T37.2 — 空内容拦截 (R01)
| 项 | 内容 |
|---|---|
| **步骤** | `message(content="")` |
| **预期** | L1 规则 R01 拦截："message tool was called with empty content" |

### T37.3 — 自动通道路由
| 项 | 内容 |
|---|---|
| **步骤** | 从 Telegram 发来的消息，Agent 用 message 回复 |
| **预期** | 回复自动路由到 Telegram 通道 |

---

## 38. Cron Tool (`agent/tools/cron.py`)

### T38.1 — 添加定时任务
| 项 | 内容 |
|---|---|
| **步骤** | "每天早上9点提醒我喝水" |
| **预期** | 创建 cron job，返回确认和 job_id |

### T38.2 — 列出定时任务
| 项 | 内容 |
|---|---|
| **步骤** | "列出我的定时任务" |
| **预期** | 返回 JSON 格式的任务列表 |

### T38.3 — 删除定时任务
| 项 | 内容 |
|---|---|
| **步骤** | "删除定时任务 <job_id>" |
| **预期** | 任务删除成功 |

### T38.4 — 缺少 message 参数
| 项 | 内容 |
|---|---|
| **步骤** | `cron(action="add")` 不传 message |
| **预期** | 返回 `Error: message is required` |

---

## 39. Save Skill Tool (`agent/tools/save_skill.py`)

### T39.1 — 保存新 Skill
| 项 | 内容 |
|---|---|
| **步骤** | Agent 保存一个工作流为 skill |
| **预期** | 在 `workspace/skills/<name>/SKILL.md` 创建文件，含 frontmatter |

### T39.2 — 版本化 (Phase 22B)
| 项 | 内容 |
|---|---|
| **步骤** | 更新同名 skill |
| **预期** | 版本号递增 |

### T39.3 — Schema 校验
| 项 | 内容 |
|---|---|
| **步骤** | 缺少 required 参数调用 save_skill |
| **预期** | 返回 schema validation 错误 |

---

## 40. Save Experience Tool (`agent/tools/save_experience.py`)

### T40.1 — 保存经验
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 `save_experience(context_trigger="...", tactical_prompt="...")` |
| **预期** | 经验存入 Experience Bank |

### T40.2 — 最小参数要求
| 项 | 内容 |
|---|---|
| **步骤** | 只传 context_trigger 不传 tactical_prompt |
| **预期** | Schema validation 报错 |
