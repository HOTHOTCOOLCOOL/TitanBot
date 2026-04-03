# 🧪 Manual Test Plan — Part 1: Core Infrastructure

> **范围**: Config / Providers / Session / Bus / CLI / Dashboard / Channels / i18n / Metrics / Background Tasks
> **预计耗时**: 4-6 小时

---

## 1. Config & Boot (`config/schema.py`, `config/loader.py`)

### T1.1 — 最小配置启动
| 项 | 内容 |
|---|---|
| **前置** | 只配 `providers.openrouter.apiKey` + `agents.defaults.model` |
| **步骤** | `nanobot agent -m "ping"` |
| **预期** | 正常启动，所有其他字段使用默认值（workspace=~/.nanobot/workspace, temperature=0.7, max_tokens=8192 等） |

### T1.2 — camelCase 与 snake_case 双兼容
| 项 | 内容 |
|---|---|
| **步骤** | 在 config.json 中分别用 `"maxTokens": 4096` 和 `"max_tokens": 4096`，各启动一次 |
| **预期** | 两种写法均正常解析，agent 使用 4096 |

### T1.3 — 未知字段容错 (extra="ignore")
| 项 | 内容 |
|---|---|
| **步骤** | 在 config.json 根层加一个 `"foo": "bar"`，在 verification 层加 `"l2Enabled": true`（已废弃字段） |
| **预期** | 启动不报错，未知字段被忽略 |

### T1.4 — config.json 缺失
| 项 | 内容 |
|---|---|
| **步骤** | 重命名 config.json → config.bak，运行 `nanobot agent` |
| **预期** | 报错提示配置文件未找到，或使用全默认值启动 |

### T1.5 — /reload 热重载
| 项 | 内容 |
|---|---|
| **前置** | 系统已运行 |
| **步骤** | 修改 config.json 中 `temperature` 值，对 Agent 发送 `/reload` |
| **预期** | 返回 reload 成功消息，验证 `_config` 缓存被清除 |

---

## 2. LLM Provider System (`providers/`)

### T2.1 — 精确前缀匹配
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `model: "deepseek/deepseek-chat"`，配置 deepseek provider 的 apiKey |
| **预期** | 请求走 deepseek provider，日志打印对应 provider 名 |

### T2.2 — Custom Provider 优先级
| 项 | 内容 |
|---|---|
| **步骤** | 同时配置 `custom.apiBase` 和 `openrouter.apiKey`，model 名含 "openrouter" |
| **预期** | custom provider 优先（因为 apiBase 非空） |

### T2.3 — Fallback 兜底
| 项 | 内容 |
|---|---|
| **步骤** | model 名设为不含任何 provider keyword 的自定义名，只配一个 provider 的 key |
| **预期** | 自动 fallback 到有 key 的 provider |

### T2.4 — API Key 缺失
| 项 | 内容 |
|---|---|
| **步骤** | 所有 provider 的 apiKey 都留空 |
| **预期** | 报错提示无可用 provider，不崩溃 |

### T2.5 — OAuth Provider 不作 Fallback
| 项 | 内容 |
|---|---|
| **步骤** | 只配 `openai_codex` 的 key，不配其他 |
| **预期** | OAuth provider 不被选为 fallback，报错无可用 provider |

---

## 3. Session Management (`session/manager.py`)

### T3.1 — Session 创建与持久化
| 项 | 内容 |
|---|---|
| **步骤** | 通过 CLI 发送一条消息，检查 `workspace/sessions/` 目录 |
| **预期** | 生成 `.jsonl` 文件，首行为 `_type: metadata`，后续为消息行 |

### T3.2 — Session 过期
| 项 | 内容 |
|---|---|
| **步骤** | 手动修改 .jsonl 中 `updated_at` 为 48 小时前，重启后发消息 |
| **预期** | Session 被判定为过期，`clear()` 后开始新的对话 |

### T3.3 — Append-Only 优化
| 项 | 内容 |
|---|---|
| **步骤** | 连续发 3 条消息，检查 .jsonl 文件大小变化 |
| **预期** | 第 2、3 条消息只追加不重写 metadata（metadata_dirty=False 路径） |

### T3.4 — /new 重置
| 项 | 内容 |
|---|---|
| **步骤** | 发送 `/new` |
| **预期** | Session 清空，旧消息存入 memory consolidation，新消息从空开始 |

### T3.5 — Identity Mapping
| 项 | 内容 |
|---|---|
| **步骤** | 在 config 中配置 `masterIdentities`：`{"telegram:123": "master_user"}` |
| **预期** | Telegram 用户 123 的 session key 解析为 `master_user` |

### T3.6 — 损坏 JSONL 容错
| 项 | 内容 |
|---|---|
| **步骤** | 手动向 .jsonl 追加一行截断的 JSON（如 `{"role":"user","con`） |
| **预期** | 加载时跳过损坏行（R3），日志出现 warning，其余消息正常 |

---

## 4. Message Bus & Events (`bus/`)

### T4.1 — Inbound → Agent → Outbound 全链路
| 项 | 内容 |
|---|---|
| **步骤** | 通过 Dashboard WebSocket 发送一条消息 |
| **预期** | InboundMessage 被 publish，Agent 处理后 OutboundMessage 返回 Dashboard |

### T4.2 — Domain Event 广播
| 项 | 内容 |
|---|---|
| **步骤** | 触发一个工具调用（如 `exec`），在 Dashboard WS 监听 |
| **预期** | 收到 `tool_executed` domain event，含 tool_name, duration_ms, success |

### T4.3 — Whiteboard 状态共享
| 项 | 内容 |
|---|---|
| **步骤** | 检查 `bus/whiteboard.py` 的 get/set 功能 |
| **预期** | 跨组件状态共享正确 |

---

## 5. CLI Interface (`cli/commands.py`)

### T5.1 — `nanobot agent -m "Hello"`
| 项 | 内容 |
|---|---|
| **预期** | 单轮对话，打印回复后退出 |

### T5.2 — `nanobot agent` 交互模式
| 项 | 内容 |
|---|---|
| **步骤** | 进入交互模式，输入多条消息，最后输入 `exit` |
| **预期** | 多轮对话正常，exit 优雅退出 |

### T5.3 — `nanobot gateway`
| 项 | 内容 |
|---|---|
| **步骤** | 启动 gateway，访问 `http://localhost:18790` |
| **预期** | Dashboard 页面加载，WebSocket 连通 |

### T5.4 — `nanobot status`
| 项 | 内容 |
|---|---|
| **预期** | 打印 provider 状态、channel 状态、workspace 路径 |

### T5.5 — `nanobot onboard`
| 项 | 内容 |
|---|---|
| **步骤** | 在全新目录运行 |
| **预期** | 创建 `~/.nanobot/` 目录结构和 config.json 模版 |

---

## 6. Dashboard (`dashboard/app.py`)

### T6.1 — Bearer Token 认证
| 项 | 内容 |
|---|---|
| **步骤** | 不带 Token 请求 `GET /api/memory` |
| **预期** | 返回 401 Unauthorized |

### T6.2 — 带 Token 请求
| 项 | 内容 |
|---|---|
| **步骤** | 从启动日志获取 auto-generated token，带 `Authorization: Bearer <token>` 请求 |
| **预期** | 返回 200 + memory 内容 |

### T6.3 — `/api/status` 无需认证
| 项 | 内容 |
|---|---|
| **步骤** | 不带 Token 请求 `GET /api/status` |
| **预期** | 返回 `{"status": "online"}` |

### T6.4 — Rate Limiting
| 项 | 内容 |
|---|---|
| **步骤** | 快速连续请求 60 次 `/api/memory` |
| **预期** | 超过桶容量后返回 429 Too Many Requests |

### T6.5 — WebSocket Token 验证
| 项 | 内容 |
|---|---|
| **步骤** | 连接 `ws://localhost:18790/ws` 不带 `?token=` |
| **预期** | 连接被拒 (code=1008) |

### T6.6 — WebSocket 消息大小限制
| 项 | 内容 |
|---|---|
| **步骤** | 通过 WS 发送 >10KB 的消息 |
| **预期** | 收到 `{"error":"Message too large (max 10KB)"}` |

### T6.7 — Dashboard API CRUD
| 项 | 内容 |
|---|---|
| **步骤** | POST `/api/memory` 写入内容，GET `/api/memory` 读回 |
| **预期** | 读写一致 |

---

## 7. Channel Manager (`channels/manager.py`)

### T7.1 — Channel 开关
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `telegram.enabled: true` 但不填 token |
| **预期** | Channel 初始化尝试但报错（无 token），其他 channel 不受影响 |

### T7.2 — allowFrom 白名单
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `telegram.allowFrom: ["12345"]`，用非 12345 的用户发消息 |
| **预期** | 消息被拒绝，不进入 Agent |

### T7.3 — 多通道同时运行
| 项 | 内容 |
|---|---|
| **步骤** | 同时启用 Telegram + Dashboard |
| **预期** | 两个通道独立工作，outbound dispatcher 正确路由 |

---

## 8. i18n (`agent/i18n.py`)

### T8.1 — 中文模式
| 项 | 内容 |
|---|---|
| **步骤** | 设置 `agents.defaults.language: "zh"`，发送 `/help` |
| **预期** | 返回中文帮助文本 |

### T8.2 — 英文模式
| 项 | 内容 |
|---|---|
| **步骤** | 设置 `agents.defaults.language: "en"`，发送 `/help` |
| **预期** | 返回英文帮助文本 |

---

## 9. Metrics & Observability (`utils/metrics.py`)

### T9.1 — `/stats` 命令
| 项 | 内容 |
|---|---|
| **步骤** | 发送几条消息后发送 `/stats` |
| **预期** | 返回 token 统计、工具执行次数、计时器数据 |

### T9.2 — Token 计数
| 项 | 内容 |
|---|---|
| **步骤** | 对比 `/stats` 前后的 prompt/completion tokens |
| **预期** | 数字递增，总数 = prompt + completion |

---

## 10. Background Task Manager (`utils/task_manager.py`)

### T10.1 — `/api/background_tasks`
| 项 | 内容 |
|---|---|
| **步骤** | 触发 `/new`（会启动后台 consolidation task），立刻请求 `/api/background_tasks` |
| **预期** | 看到至少一个 task（name=new_session_consolidate），状态为 running 或 done |

### T10.2 — 异常隔离
| 项 | 内容 |
|---|---|
| **步骤** | 检查日志中后台任务异常是否被捕获 |
| **预期** | 异常记录到日志但不影响主 Agent 循环 |
