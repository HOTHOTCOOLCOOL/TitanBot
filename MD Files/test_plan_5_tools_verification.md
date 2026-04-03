# 🧪 Manual Test Plan — Part 5: Tools (Part 2) & Verification

> **范围**: Browser / Browser-Use Worker / Screen Capture / RPA / Vision / L0-L1-L3 Verification
> **预计耗时**: 8-10 小时

---

## 41. Browser Tool (`plugins/browser.py`)

### T41.1 — navigate + content
| 项 | 内容 |
|---|---|
| **步骤** | "打开 https://example.com 并提取页面内容" |
| **预期** | Playwright 启动浏览器，导航成功，返回页面文本 |

### T41.2 — screenshot
| 项 | 内容 |
|---|---|
| **步骤** | 导航到页面后 `browser(action="screenshot")` |
| **预期** | 返回 `__IMAGE__:/path/to/screenshot.png` |

### T41.3 — evaluate (JavaScript 执行)
| 项 | 内容 |
|---|---|
| **步骤** | `browser(action="evaluate", script="document.title")` |
| **预期** | 返回页面 title |

### T41.4 — 未导航时操作
| 项 | 内容 |
|---|---|
| **步骤** | 不先 navigate，直接 `browser(action="content")` |
| **预期** | 返回 "Error: No page open" 之类的错误 |

### T41.5 — login (Cookie 保存)
| 项 | 内容 |
|---|---|
| **步骤** | `browser(action="login", url="https://somesite.com")` |
| **预期** | 打开可见浏览器供用户手动登录，30s 后自动关闭并保存 cookies |

### T41.6 — close (资源释放)
| 项 | 内容 |
|---|---|
| **步骤** | `browser(action="close")` |
| **预期** | 浏览器关闭，进程释放，再次操作需重新启动 |

### T41.7 — SSRF 双层防护 (Browser)
| 项 | 内容 |
|---|---|
| **步骤** | `browser(action="navigate", url="http://169.254.169.254/metadata")` |
| **预期** | URL SSRF 检查拦截（RFC1918/link-local/cloud metadata） |

### T41.8 — ensure_visible (headless→headed 切换)
| 项 | 内容 |
|---|---|
| **步骤** | `browser(action="ensure_visible")` |
| **预期** | 浏览器从 headless 切换到可见窗口，窗口最大化 |

### T41.9 — Dynamic CDP Port
| 项 | 内容 |
|---|---|
| **步骤** | 启动浏览器后检查 `_cdp_port` 属性 |
| **预期** | 使用动态分配的端口（非固定 9222） |

---

## 42. Browser Session Store (`plugins/browser_sessions.py`)

### T42.1 — Cookie 加密存储
| 项 | 内容 |
|---|---|
| **步骤** | 执行 login 后检查 `workspace/browser_sessions/` |
| **预期** | 文件存在，内容经 DPAPI/Fernet 加密，无法直接读取 |

### T42.2 — Cookie 自动恢复
| 项 | 内容 |
|---|---|
| **步骤** | login 保存 cookies 后，navigate 到同一域名 |
| **预期** | Cookies 自动加载，保持登录状态 |

---

## 43. Browser Trust Manager (`plugins/browser_trust.py`)

### T43.1 — Progressive Domain Trust
| 项 | 内容 |
|---|---|
| **步骤** | 首次 navigate 到 `https://example.com` 子路径 |
| **预期** | 第一次可能需确认，后续同域导航自动信任 |

### T43.2 — Wildcard 匹配
| 项 | 内容 |
|---|---|
| **步骤** | 配置 trust 中 `*.example.com`，导航到 `sub.example.com` |
| **预期** | 自动信任，无需确认 |

---

## 44. Browser-Use Worker (`agent/tools/browser_use_worker.py`)

### T44.1 — 成功执行任务
| 项 | 内容 |
|---|---|
| **前置** | 浏览器已打开并 navigate 到某页面 |
| **步骤** | `browser_use_worker(task="点击页面上的搜索按钮")` |
| **预期** | browser-use 通过 CDP 连接到已有浏览器，执行任务，返回结果 |

### T44.2 — CDP 连接失败 fallback
| 项 | 内容 |
|---|---|
| **步骤** | 浏览器未启动时调用 browser_use_worker |
| **预期** | 连接失败，返回错误信息（不崩溃） |

### T44.3 — 超时保护 (120s)
| 项 | 内容 |
|---|---|
| **步骤** | 给出一个无法完成的 browser-use 任务 |
| **预期** | 120s 后超时退出 |

### T44.4 — [FALLBACK_RPA] 信号
| 项 | 内容 |
|---|---|
| **步骤** | browser_use_worker 执行失败 |
| **预期** | 返回 `[FALLBACK_RPA]` 信号，Agent 自动切换到 RPA |

### T44.5 — CDP 资源清理
| 项 | 内容 |
|---|---|
| **步骤** | browser_use_worker 执行完成或失败 |
| **预期** | CDP 连接被正确关闭（检查端口释放） |

---

## 45. Screen Capture (`agent/tools/screen_capture.py`)

### T45.1 — 全屏截图
| 项 | 内容 |
|---|---|
| **步骤** | `screen_capture()` |
| **预期** | 返回 `__IMAGE__:/path.png | ANCHORS: [...]` + `monitor_context` |

### T45.2 — Set-of-Marks 标注
| 项 | 内容 |
|---|---|
| **步骤** | 启用 SoM 模式截图 |
| **预期** | 截图中 UI 元素有编号标注 |

### T45.3 — 多显示器 monitor_context
| 项 | 内容 |
|---|---|
| **前置** | 多显示器环境 |
| **步骤** | screen_capture 后检查 monitor_context 字段 |
| **预期** | 包含 offset_x, offset_y, scale_x, scale_y 用于坐标转换 |

---

## 46. RPA Executor (`agent/tools/rpa_executor.py`)

### T46.1 — click 操作
| 项 | 内容 |
|---|---|
| **步骤** | `rpa_executor(action="click", x=500, y=300)` |
| **预期** | 物理鼠标点击指定坐标 |

### T46.2 — type 操作
| 项 | 内容 |
|---|---|
| **步骤** | `rpa_executor(action="type", text="Hello World")` |
| **预期** | 键盘输入文本 |

### T46.3 — 坐标转换 (多显示器)
| 项 | 内容 |
|---|---|
| **前置** | 多显示器 + monitor_context 可用 |
| **步骤** | Agent 提供 VLM 坐标 + monitor_context，RPA 执行 click |
| **预期** | 坐标通过 `_transform_coordinates` 正确转换到物理屏幕位置 |

### T46.4 — UIAutomation 元素查找
| 项 | 内容 |
|---|---|
| **步骤** | `rpa_executor(action="find_element", name="Start")` |
| **预期** | 返回匹配的 UI 元素信息 |

### T46.5 — Headless 浏览器阻止 RPA
| 项 | 内容 |
|---|---|
| **前置** | 浏览器以 headless 模式运行 |
| **步骤** | Agent 尝试 RPA 操作 |
| **预期** | RPA 拒绝执行（浏览器不可见时 RPA 无意义） |

---

## 47. Vision System

### T47.1 — PaddleOCR 文字识别
| 项 | 内容 |
|---|---|
| **前置** | PaddleOCR 已安装 |
| **步骤** | 截图后分析 |
| **预期** | 返回 OCR 识别的文字 |

### T47.2 — YOLO UI 检测
| 项 | 内容 |
|---|---|
| **前置** | YOLO 模型已加载 |
| **步骤** | 截图后 YOLO 检测 |
| **预期** | 检测 UI 元素（按钮、输入框等）并返回坐标 |

### T47.3 — VLM 反馈循环
| 项 | 内容 |
|---|---|
| **步骤** | 截图 → VLM 分析 → 执行操作 → 再截图 → VLM 确认 |
| **预期** | 反馈循环正常工作 |

---

## 48. Verification Layer L0 (`agent/verification.py`)

### T48.1 — Experience 注入
| 项 | 内容 |
|---|---|
| **步骤** | 匹配的经验存在时发送请求 |
| **预期** | L0 层将 experience 注入 system prompt "💡" |

### T48.2 — Reflection 注入
| 项 | 内容 |
|---|---|
| **步骤** | 匹配的反思存在时发送请求 |
| **预期** | System prompt 出现 "⚠️ Avoid Past Mistakes" |

### T48.3 — System Reminder 注入
| 项 | 内容 |
|---|---|
| **步骤** | 检查长对话中 system reminder 是否定期重复 |
| **预期** | 每 N 轮注入核心规则提醒 |

---

## 49. Verification Layer L1 — 硬规则 (`agent/verification.py`)

### T49.1 — R01: 空消息拦截
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 `message(content="")` |
| **预期** | 被 L1 拦截，返回 "message tool was called with empty content" |

### T49.2 — R02: Shell 危险命令
| 项 | 内容 |
|---|---|
| **步骤** | Agent 尝试 `exec(command="rm -rf /")` |
| **预期** | L1 regex 匹配到 destructive pattern → 拦截 |

### T49.3 — R03: IP 泄露防护
| 项 | 内容 |
|---|---|
| **步骤** | Agent 尝试将本机 IP 发送到外部 |
| **预期** | L1 检测 IP 泄露意图 → 拦截 |

### T49.4 — R06: SSRF (web_fetch/browser)
| 项 | 内容 |
|---|---|
| **步骤** | `web_fetch(url="http://10.0.0.1/admin")` |
| **预期** | L1 SSRF 规则拦截 private IP |

### T49.5 — R08: Agent-triggered search 语言一致性
| 项 | 内容 |
|---|---|
| **步骤** | 用户用中文提问，Agent 触发 web_search |
| **预期** | R08 检查 search query 是否与用户 prompt 的语言一致 |

### T49.6 — R09: 重复工具调用检测
| 项 | 内容 |
|---|---|
| **步骤** | Agent 连续调同一工具+同参 3 次 |
| **预期** | R09/L14 检测到并拦截 |

### T49.7 — L1 Bypass（允许列表）
| 项 | 内容 |
|---|---|
| **步骤** | 检查 L1 是否有 bypass 机制 |
| **预期** | L1 **无** bypass，硬编码规则不可绕过 |

---

## 50. Verification Layer L3 (`agent/verification.py`)

### T50.1 — 反模式审计 (post-execution)
| 项 | 内容 |
|---|---|
| **步骤** | Agent 执行完一轮工具调用后，验证 L3 是否运行 |
| **预期** | L3 审计工具调用结果，提取成功/失败模式 |

### T50.2 — 成功模式存档
| 项 | 内容 |
|---|---|
| **步骤** | 工具调用成功后检查 L3 output |
| **预期** | 成功模式被存入 Experience Bank 供未来参考 |
