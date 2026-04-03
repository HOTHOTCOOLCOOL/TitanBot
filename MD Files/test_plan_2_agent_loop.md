# 🧪 Manual Test Plan — Part 2: Agent Loop & Intelligence

> **范围**: Agent Loop / Tool Execution / Context / Commands / Detection / Circuit Breaker / Loop / VLM / Streaming / Subagent
> **预计耗时**: 6-8 小时

---

## 11. Agent Loop Core (`agent/loop.py`)

### T11.1 — 基本工具调用+回复
*注：单纯问几号，模型可能会凭借自带的知识甚至编造直接回答（不调用工具）。为了强制测试工具调用链路，我们需要增加具体的指令。*
| 项 | 内容 |
|---|---|
| **步骤** | 发送提示词：`"请务必使用系统命令行工具（如 exec 执行 date 或 Get-Date 命令）来获取当前系统的精确日期，然后根据返回结果告诉我。"` |
| **预期** | Agent 成功调用 `exec` 获取日期，然后返回自然语言回复 |

### T11.2 — Max Iterations 上限
| 项 | 内容 |
|---|---|
| **前置** | 默认 `max_tool_iterations: 20` |
| **步骤** | **测试示例（规避各种审批和拦截机制）：**<br>发送提示词：`"为了测试上限机制：请使用 list_dir 随意查看一个源码目录，然后使用 read_file 工具独自、每次只读取里面一个不同的文件。不要重复读相同文件，否则会被循环检测拦截。你必须连续多次单步调用只读取这个文件，直到完成 25 轮对话（即25次 read_file）。绝对不可以使用并行或批处理！"` |
| **预期** | Agent 在执行到第 20 轮迭代后退出，并触发 max iterations 上限警告提示 |

### T11.3 — LLM 超时 (120s)
| 项 | 内容 |
|---|---|
| **步骤** | **手动触发超时测试示例：**<br>1. 停掉当前的 Agent。<br>2. 打开配置文件（如 `config.yaml` / `.env`），将当前的 LLM  `base_url` 或端点临时修改为一个无法访问的黑洞内网 IP，例如：`http://10.255.1.1:8123` <br>3. 启动并发送一条简单的消息（如 `"hello"`） |
| **预期** | 120s 后触发超时机制，明确返回 `⚠️ LLM call timed out after 120s`（或相关日志错误/熔断机制提示） |

### T11.4 — Message Flood Guard
| 项 | 内容 |
|---|---|
| **步骤** | **测试示例（尝试触发消息风暴）：**<br>发送提示词：`"请分别独立发送 5 条消息给我（如果是通过工具发消息，请连续独立调用 5 次发消息工具，每次告诉我'这是第N条'）"` |
| **预期** | 调用 3 次后 loop 自动 break（触发了 `_MAX_MESSAGE_CALLS=3` 的拦截逻辑） |

### T11.5 — 多工具并发执行 (asyncio.gather)
| 项 | 内容 |
|---|---|
| **步骤** | LLM 一次提出 2 个工具调用（如同时 read_file + exec） |
| **预期** | 两个工具并发执行，结果按序返回 |

---

## 12. Tool Registry & Execution (`agent/tools/registry.py`, `agent/tools/base.py`)

### T12.1 — 输出截断 (50K)
| 项 | 内容 |
|---|---|
| **步骤** | `exec` 一个输出超过 50K 字符的命令（如 `dir /s C:\Windows`） |
| **预期** | 输出被截断到 50,000 字符，末尾有 `[OUTPUT TRUNCATED]` |

### T12.2 — 参数校验
| 项 | 内容 |
|---|---|
| **步骤** | 让 LLM 尝试调用工具但缺少 required 参数 |
| **预期** | `validate_params()` 返回错误消息，不执行 |

### T12.3 — 错误前缀统一性
| 项 | 内容 |
|---|---|
| **步骤** | 触发各种工具错误（文件不存在、无效命令等） |
| **预期** | 所有工具的错误消息都以 `"Error: "` 开头 |

### T12.4 — RiskTier 分级
| 项 | 内容 |
|---|---|
| **步骤** | 检查 `outlook.get_risk_tier({"action":"find_emails"})` vs `{"action":"send_email"}` |
| **预期** | find_emails = READ_ONLY, send_email = MUTATE_EXTERNAL |

---

## 13. Context Builder (`agent/context.py`)

### T13.1 — System Prompt 完整性
| 项 | 内容 |
|---|---|
| **步骤** | 开启日志 debug 模式，发送一条消息 |
| **预期** | System prompt 中包含：角色描述、工具列表、skills 摘要 |

### T13.2 — 历史消息滑动窗口
| 项 | 内容 |
|---|---|
| **前置** | 在一个 session 中积累 60+ 条消息 |
| **步骤** | 发送新消息 |
| **预期** | 只取最近 `memory_window`(50) 条消息构建 context |

### T13.3 — __IMAGE__ 协议处理
| 项 | 内容 |
|---|---|
| **步骤** | 工具返回 `__IMAGE__:/path/to/file.png | ANCHORS:...` |
| **预期** | ContextBuilder 将其转为 `image_url` 块注入 messages |

### T13.4 — 知识注入
| 项 | 内容 |
|---|---|
| **前置** | 知识库中有相关条目 |
| **步骤** | 发送与知识库匹配的问题 |
| **预期** | 日志显示 knowledge matched，context 中注入知识内容 |

---

## 14. Slash Commands (`agent/commands.py`)

### T14.1 — /help
| 项 | 内容 |
|---|---|
| **预期** | 返回完整帮助文本（中/英文取决于 language 设置） |

### T14.2 — /new
| 项 | 内容 |
|---|---|
| **步骤** | 对话数条后发送 `/new` |
| **预期** | Session 清空，返回"新会话已开始"，后台触发 consolidation |

### T14.3 — /tasks
| 项 | 内容 |
|---|---|
| **预期** | 列出最近 10 个 task，含状态图标（✅/❌/⏳） |

### T14.4 — /kb list / /kb cleanup / /kb delete
| 项 | 内容 |
|---|---|
| **步骤** | 分别执行三个子命令 |
| **预期** | list 列出知识条目，cleanup 清理过时条目，delete 删除指定条目 |

### T14.5 — /memory export / /memory import
| 项 | 内容 |
|---|---|
| **步骤** | `/memory export` → 修改导出 JSON → `/memory import <path>` |
| **预期** | 导出成功生成 workspace/memory_export.json；导入校验路径在 workspace 内（S4） |

### T14.6 — /memory import 路径穿越防御
| 项 | 内容 |
|---|---|
| **步骤** | `/memory import ../../etc/passwd` |
| **预期** | 返回 "Access denied: import file must be within the workspace directory" |

### T14.7 — /deep_consolidate
| 项 | 内容 |
|---|---|
| **预期** | 返回"深度整合已启动"，后台异步执行 |

### T14.8 — /stats
| 项 | 内容 |
|---|---|
| **预期** | 返回格式化的 metrics 报告 |

### T14.9 — Memory Intent 检测
| 项 | 内容 |
|---|---|
| **步骤** | 发送 `"记住我的邮箱是 test@test.com"` |
| **预期** | Agent 自动调用 `memory` 工具 store 存储该信息 |

---

## 15. Wait-phrase & Fake-completion Detection

### T15.1 — Wait-phrase 检测
| 项 | 内容 |
|---|---|
| **步骤** | 如果 LLM 返回"稍等，我来处理"但不调用工具 |
| **预期** | Agent 自动追加 nudge prompt 要求调用工具，不终止循环 |

### T15.2 — Fake-completion 检测
| 项 | 内容 |
|---|---|
| **步骤** | 如果 LLM 返回"已发送邮件"但实际没调用 outlook 工具 |
| **预期** | Agent 自动追加 nudge prompt "你似乎没有实际执行工具" |

---

## 16. Circuit Breaker

### T16.1 — 连续 3 次工具全部失败
| 项 | 内容 |
|---|---|
| **步骤** | 构造场景使工具连续失败 3 次（如反复访问不存在的文件） |
| **预期** | 第 3 次后触发 circuit breaker，返回 "⚠️ Multiple consecutive tool failures" |

### T16.2 — P29-5 自动经验生成
| 项 | 内容 |
|---|---|
| **前置** | experience_enabled: true |
| **步骤** | 触发 circuit breaker |
| **预期** | 检查 experience bank 中新增了一条 `error_recovery` 类型的经验 |

### T16.3 — 非连续失败不触发
| 项 | 内容 |
|---|---|
| **步骤** | 工具失败-成功-失败交替 |
| **预期** | 计数器被重置（consecutive_all_exceptions=0），不触发 breaker |

---

## 17. Loop Detection

### T17.1 — 精确重复检测 (L14)
| 项 | 内容 |
|---|---|
| **步骤** | 构造场景使 LLM 连续 3 次调用完全相同的工具+参数 |
| **预期** | 返回 "⚠️ I appear to be stuck in a loop" |

### T17.2 — 模糊循环检测 (Phase 33)
| 项 | 内容 |
|---|---|
| **步骤** | LLM 反复用略微不同但实质相同的参数调用同一工具 |
| **预期** | `_detect_fuzzy_loop()` 检测到频率支配或循环子序列，跳出循环 |

### T17.3 — 正常多次调用不误报
| 项 | 内容 |
|---|---|
| **步骤** | 请求"读取 3 个不同的文件"，Agent 调用 3 次 read_file 但参数不同 |
| **预期** | 不触发循环检测 |

---

## 18. VLM Routing

### T18.1 — 图片触发 VLM 切换
| 项 | 内容 |
|---|---|
| **前置** | 配置 `vlm.model: "dashscope/qwen-vl-max"` |
| **步骤** | 调用 screen_capture，截图返回 `__IMAGE__` |
| **预期** | 下一轮 LLM 调用路由到 VLM 模型 |

### T18.2 — 最近 N 消息窗口 (recency=2)
| 项 | 内容 |
|---|---|
| **步骤** | VLM 处理完截图并回复后，继续对话 |
| **预期** | 图片不在最近 2 条消息中后，自动切回主模型 |

### T18.3 — VLM Provider 未配置 fallback
| 项 | 内容 |
|---|---|
| **步骤** | 配置 vlm.model 但不配对应 provider 的 apiKey |
| **预期** | Fallback 到主模型，日志 warning "VLM provider config missing" |

---

## 19. Streaming (`dashboard/app.py: /ws/stream`)

### T19.1 — 实时 Token 流
| 项 | 内容 |
|---|---|
| **前置** | `streaming.enabled: true`, 连接到 Dashboard |
| **步骤** | 通过 Dashboard 发送消息 |
| **预期** | `/ws/stream` 收到多个 `{"delta": "...", "done": false}` 帧，最后一帧 `done: true` |

### T19.2 — Streaming 关闭
| 项 | 内容 |
|---|---|
| **步骤** | `streaming.enabled: false` |
| **预期** | 不发送 stream 帧，直接一次性返回完整回复 |

---

## 20. Subagent System (`agent/subagent.py`)

### T20.1 — Spawn 工具
| 项 | 内容 |
|---|---|
| **步骤** | 给 Agent 一个可能触发 spawn 工具的请求（后台任务） |
| **预期** | 子 Agent 在后台运行，主 Agent 报告已提交任务 |

### T20.2 — Subagent 错误隔离
| 项 | 内容 |
|---|---|
| **步骤** | 子 Agent 遇到错误 |
| **预期** | 错误不影响主 Agent，spawn 返回错误信息 |
