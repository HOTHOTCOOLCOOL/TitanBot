# Nanobot 功能操作手册 (Operations Manual)

> 每个功能的具体使用方法、参数说明、示例指令。
> 最后更新: 2026-03-25

---

## 1. 启动方式

### CLI 交互模式
```bash
python -m nanobot agent                    # 交互式聊天
python -m nanobot agent -m "你好"          # 单条消息
python -m nanobot agent --logs             # 显示运行日志
```

### Gateway（全功能服务端 + Web Dashboard）
***官方推荐的唯一后台启动方式***
```bash
python -m nanobot gateway                  # 启动核心 Agent + 所有 Channel + Web Dashboard
python -m nanobot gateway -p 18790         # 指定 Web UI 端口 (默认 18790)
```
浏览器访问 Web UI：`http://127.0.0.1:18790?token=<gateway.token>`
*(提示：`nanobot dashboard` 命令现在是一个纯客户端启动器，仅负责在浏览器中打开远程 Gateway 页面，不再启动独立的 Agent。)*

token 来源：`config.json` → `gateway.token` 字段。

---

## 2. 常用斜杠命令

| 命令 | 功能 |
|------|------|
| `/new` | 清空当前 session，开始新对话 |
| `/reload` | 热重载 config + 重新扫描 plugins |
| `/help` | 显示帮助 |
| `/tasks` | 显示最近 10 个任务 |
| `/stats` | 显示系统指标 |
| `/kb list` | 列出知识库条目 |
| `/kb cleanup` | 清理过时知识 |
| `/memory export` | 导出全部记忆为 JSON |
| `/deep_consolidate` | 手动触发深度记忆合并 |

---

## 3. Browser 浏览器自动化

### 前提配置 (`config.json`)
```json
"browser": {
    "enabled": true,
    "headless": true,
    "executablePath": "D:/path/to/chrome.exe"
}
```

### 基本操作

**导航并截图：**
```
> 打开浏览器，导航到 https://www.baidu.com 并截图
```

**登录并保存 Session（A23 关键）：**
```
> 使用 browser 工具，action=login，url=https://example.com，save_session=true
```
或自然语言：
```
> 用浏览器登录 https://example.com，登录后保存 session
```

**Session 恢复：** 重启后再次导航到同一域名，自动恢复已保存的 cookies。

### action 参数一览

| action | 必要参数 | 说明 |
|--------|---------|------|
| `navigate` | `url` | 导航到 URL |
| `click` | `selector` | 点击 CSS 选择器元素 |
| `fill` | `selector`, `value` | 填写表单（清空后填入） |
| `type` | `selector`, `text` | 模拟键盘输入 |
| `select` | `selector`, `value` | 选择下拉选项 |
| `screenshot` | — | 截取当前页面 |
| `content` | `selector`(可选) | 提取页面文本 |
| `evaluate` | `expression` | 执行白名单 JS |
| `wait` | `selector` / `wait_for` | 等待元素或 networkidle |
| `login` | `url`, `save_session`(可选) | 导航 + 可选保存 session |
| `close` | — | 关闭浏览器 |

### Session 存储位置
```
~/.nanobot/browser_sessions/{domain}/
  ├── session.enc          # 加密 cookies
  └── session.meta.json    # TTL 元数据
```

---

## 4. VLM 视觉模型

### 配置 (`config.json`)
```json
"vlm": {
    "enabled": true,
    "model": "dashscope/qwen-vl-max"
}
```

### 使用
```
> 截屏当前桌面，描述你看到了什么
```

### 切换 VLM Provider
1. 修改 `config.json` 中 `agents.vlm.model`
2. 确保对应 provider 的 apiKey 已配置
3. 在聊天中发送 `/reload`

---

## 5. Plugin 管理

### Plugin 目录
`nanobot/plugins/` 下的 `.py` 文件，继承 `Tool` 基类。

### 加载/重载
```
> /reload
```
输出：`🔄 已重新加载插件工具: browser, ...`

### 创建自定义 Plugin
```python
# nanobot/plugins/my_tool.py
from nanobot.agent.tools.base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "描述这个工具做什么"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "输入"}
        },
        "required": ["input"]
    }
    
    async def execute(self, input: str = "", **kwargs) -> str:
        return f"收到: {input}"
```

保存后 `/reload` 即可使用。

### 错误隔离
有语法错误的 plugin 会被跳过，不影响其他 plugin 加载。

---

## 6. Cron 定时任务

### CLI 管理
```bash
python -m nanobot cron list              # 列出任务
python -m nanobot cron add -n "日报" -c "0 9 * * *" -m "生成今日工作日报"
python -m nanobot cron remove <job_id>   # 删除
python -m nanobot cron enable <job_id> --disable  # 禁用
```

### 聊天中使用
```
> 帮我设置一个每天早上 9 点的提醒
```
Agent 会调用 `cron` 工具创建。

---

## 7. 记忆系统

### 显式存储
```
> 记住我喜欢用深色主题
> 帮我记下会议室密码是 1234
```

### 搜索记忆
```
> 我之前说过喜欢什么颜色？
```

### 导入导出
```
> /memory export    # 导出到 memory_export.json
> /memory import memory_export.json
```

---

## 8. Config 关键字段速查

| 字段路径 | 说明 |
|---------|------|
| `agents.defaults.model` | 主 LLM 模型 |
| `agents.vlm.model` | 视觉模型 |
| `agents.browser.enabled` | 启用浏览器 |
| `agents.browser.executablePath` | Chrome 路径 |
| `agents.browser.sessionTtlHours` | Session 有效期(小时) |
| `gateway.token` | Dashboard/Gateway 认证 token |
| `gateway.host` | 绑定地址 |
| `providers.<name>.apiKey` | Provider API Key |
