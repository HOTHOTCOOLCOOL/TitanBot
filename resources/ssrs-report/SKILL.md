---
name: ssrs-report
description: 查询内网SSRS报表系统并分析报告内容
homepage: https://github.com/HOTHOTCOOLCOOL/nanobot
metadata:
  nanobot:
    emoji: 📊
    requires:
      bins: [python]
      env: [SSRS_USER, SSRS_PASSWORD]
    tags: [report, ssrs, intranet, sales, analysis]
    always: false
    type: workflow
---

# ssrs-report

**从内网 SSRS 报表系统获取并分析报告**

## When to use (trigger phrases)

使用这个技能，当用户要求：
- "帮我查 XXX report"
- "查一下购物村排名"
- "看看今天的销售排行"
- "拉一下 Top sales 报告"
- "帮我看 SSRS 里的XXX报表"
- 任何提到 "内网报告"、"SSRS"、"ReportServer" 或特定报告名称的请求

## Summary

这个技能允许 nanobot 自动完成：
1. 根据用户描述匹配 `reports_registry.json` 中的报告（支持中文名或别名）
2. 使用 Windows NTLM 认证（AD 域账号，无需额外输入密码）访问内网 SSRS
3. 优先下载 CSV 格式（结构化数据），不可用时回退 HTML 格式
4. 解析报告内容，交由 LLM 进行分析和总结
5. 根据用户要求，直接返回分析结果或通过邮件发送

## Workflow Steps

### Step 1: 识别报告名称

从用户的描述中提取报告关键词，例如：
- "购物村ranking" → 查找 "购物村排名"
- "Top sales" → 匹配 alias "Top sales"
- "SHV 销售" → 匹配 "SHV日销售"

### Step 2: 执行 fetch_report.py

```bash
cd {skill_dir}
python fetch_report.py "{report_name}"
```

可用参数：
- `--list`：列出所有可用报告及别名
- `--format CSV|HTML4.0`：指定导出格式（默认 auto，使用 registry 配置）
- `--pdf`：在获取报告内容后额外生成 PDF 文件（输出行格式：`PDF_PATH:<path>`）
- `--pdf-output <path>`：自定义 PDF 保存路径（不指定时自动放到系统临时目录）

脚本会：
1. 查找 `reports_registry.json` 匹配报告
2. 自动选择认证方式（优先顺序见下方「认证说明」）
3. 优先尝试 CSV 格式，失败则回退 HTML4.0
4. 返回解析后的可读文本（适合 LLM 分析）

### Step 3: 分析报告内容

将 fetch_report.py 的输出内容提供给 LLM 分析，根据用户需求生成：
- **中文摘要**：关键指标、趋势、异常
- **排名展示**：格式化表格
- **对比分析**：与上期数据对比（如果有历史数据）
- **邮件正文**：如果用户要求发送邮件

LLM 应该主动根据上下文决定输出格式，不需要额外询问用户。

### Step 4: 发送结果（可选）

如果用户要求通过邮件发送，使用 `outlook` 工具：

```json
{
  "action": "send_email",
  "recipient": "user@example.com",
  "subject": "购物村排名报告 - 2026-02-26",
  "body": "LLM 生成的分析内容..."
}
```

## Usage Examples

**查询并直接显示：**
> "帮我查一下购物村ranking的report"

Agent 执行：
1. 匹配报告名 → "购物村排名"
2. 运行 `python fetch_report.py "购物村排名"`
3. LLM 分析 CSV 内容，生成中文排名摘要
4. 直接返回给用户

**查询并发送邮件：**
> "把今天的购物村排名报告发到我邮箱"

Agent 执行：
1. 运行 `python fetch_report.py "购物村排名"` 获取报告内容
2. LLM 生成邮件正文
3. 调用 `outlook.send_email` 发送

**查询并生成 PDF：**
> "把今天的购物村排名报告生成PDF"

Agent 执行：
```bash
python fetch_report.py "购物村排名" --pdf
```
输出最后一行格式为 `PDF_PATH:<路径>`，Agent 解析此路径后可作为邮件附件发送。

**列出所有可用报告：**
> "有哪些SSRS报告可以查？"

Agent 执行：
```bash
python fetch_report.py --list
```

## Configuration

### 认证配置（三层 fallback，无需 .env 配置即可使用）

| 层级 | 方式 | 配置 |
|------|------|------|
| 🥇 SSPI（**默认**） | 直接用当前 Windows 登录态透传，**无需任何配置** | 无（自动） |
| 🥈 Windows Credential Manager | 加密存储，一次配置永久生效 | `python fetch_report.py --setup-credentials` |
| 🥉 .env 明文 | 最后手段，不推荐 | `SSRS_USER` / `SSRS_PASSWORD` / `SSRS_DOMAIN` |

> **绝大多数情况下，运行在域内机器上时 SSPI 会自动工作，无需任何配置。**

### 添加新报告

只需编辑 `reports_registry.json`，无需修改代码：

```json
{
  "reports": {
    "新报告中文名": {
      "aliases": ["English Alias", "另一个别名"],
      "url": "http://vcgkpb04/ReportServer?%2FPath%2FTo%2FReport",
      "params": {"rs:ParameterLanguage": "en-US"},
      "preferred_format": "CSV",
      "fallback_format": "HTML4.0",
      "description": "报告功能描述",
      "auth": "ntlm",
      "category": "sales"
    }
  }
}
```

## Important Notes

### ⚠️ 重发邮件时的正确做法（重要！）

> **当用户说「邮件没收到」、「再发一次」、「重发」时：**
> - ✅ **正确**：直接重新获取报告（`fetch_report.py`）+ 重新调用 `outlook.send_email`
> - ❌ **错误**：调用 `find_emails` 搜索收件箱 — 这只会搜到已发送的历史邮件，不是在帮用户重发
>
> **原则：重发 = 重新走一遍「获取→分析→发送」流程，不是去搜索收件箱。**

### 认证说明
- 三层 fallback（见上方 Configuration 章节）
- **SSPI（默认）**：零配置，直接用当前 Windows 登录态，完全不需要密码
- 脚本启动时会在 stderr 打印使用了哪种认证方式（`[SSRS Auth] Using ...`）

### 格式选择策略
- **CSV**：首选，结构化数字数据，LLM 分析效果最好
- **HTML4.0**：备选，适合复杂布局的报告
- **PDF（`--pdf`）**：用于生成可分发的 PDF 文件；内容用 Courier 字体等宽排版，中文字符会被 `?` 替代（fpdf2 默认字体不含中文），建议报告以英文/数字为主时使用
- **避免 Excel**：SSRS 导出 Excel 格式混乱，不推荐

### 网络要求
- 必须在内网或 VPN 环境下运行
- 报告服务器：`http://vcgkpb04/ReportServer`
- 如果连接超时，确认已连接内网

### 错误处理
- 认证失败 → 检查认证层级；SSPI 失败时尝试 `--setup-credentials`
- 报告不存在 → 运行 `--list` 查看可用报告
- 连接超时 → 检查内网连接状态
- PDF 失败 → 运行 `pip install fpdf2` 安装依赖
