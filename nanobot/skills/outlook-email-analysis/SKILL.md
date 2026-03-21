---
name: outlook-email-analysis
description: >
  Analyze Outlook email attachments and send analysis reports. Use when user asks to:
  analyze emails/attachments, extract and parse email attachments (PDF/Excel/Word/CSV),
  search inbox folders for reports, generate analysis summaries from email data,
  or forward analysis results via email.
  Triggers: "分析邮件", "邮件附件分析", "分析 outlook 附件", "提取附件",
  "今天的销售report", "昨天的业绩数据", "analyze inbox", "email report analysis".
  Requires Outlook desktop app running.
category: business_workflow
homepage: https://github.com/HKUDS/nanobot
metadata:
  nanobot:
    emoji: 📧
    requires:
      bins: [python]
      env: []
    tags: [email, outlook, automation, analysis]
    always: false
    type: workflow
---

# outlook-email-analysis

**自动分析Outlook邮件附件并发送分析报告**

## Summary

这个技能允许 nanobot 自动完成以下任务：
1. 根据用户指定的条件（主题、日期，发件人、文件夹）查找 Outlook 邮件
2. 提取邮件中的附件
3. 解析附件内容（支持 PDF、Excel、Word、文本等格式）
4. 使用本地 LLM 分析附件内容
5. 将分析结果发送给用户或指定收件人

## Workflow Steps

### Step 1: 理解日期意图

**重要业务规则**（参考 KNOWLEDGE.md）：
- 销售日报在**次日**发送
- "昨天的销售数据" → 搜索**今天**收到的报告
- "今天的销售report" → 搜索**今天**收到的报告（反映昨天的业绩）
- "某日的业绩数据" → 搜索**该日期+1天**收到的报告

### Step 2: 查找邮件

使用 `outlook` 工具的 `find_emails` 操作：

```json
{
  "action": "find_emails",
  "criteria": {
    "folder": "inbox/reporting",
    "subject_contains": "Daily",
    "has_attachments": true,
    "received_after": "2026-02-25",
    "max_results": 10
  }
}
```

参数说明：
- `folder`: 文件夹路径（如 "inbox", "inbox/reporting", "sent"）
- `subject_contains`: 主题关键词
- `from_email`: 发件人邮箱（支持部分匹配）
- `to_email`: 收件人邮箱（用于搜索已发送邮件）
- `received_after` / `received_before`: 日期范围 (YYYY-MM-DD)
- `has_attachments`: **分析附件时建议设为 true**
- `max_results`: 返回数量限制

### Step 3: 阅读邮件内容（可选）

如需查看邮件正文，使用 `read_email` 操作：

```json
{
  "action": "read_email",
  "email_index": 0
}
```

### Step 4: 提取附件

使用 `outlook` 工具的 `get_all_attachments` 操作：

```json
{
  "action": "get_all_attachments",
  "email_index": 0
}
```

- email_index: 从 find_emails 结果中选择（0-based）
- 自动过滤图片签名，只保留文档附件（PDF/Excel/Word等）

### Step 5: 分析附件内容

使用 `attachment_analyzer` 工具的 `parse` 操作：
- file_path: 附件的完整路径（从上一步获得）
- 工具会自动识别文件类型并解析内容
- 支持 PDF、Excel、Word、文本、CSV 格式

### Step 6: 发送报告（可选）

使用 `outlook` 工具的 `send_email` 操作：

```json
{
  "action": "send_email",
  "recipient": "user@example.com",
  "subject": "分析报告",
  "body": "报告内容..."
}
```

## Usage Example

用户请求：
> "帮我分析 inbox/reporting 中今天的邮件"

Agent 执行流程：
1. 确定日期：今天 = 2026-02-25
2. 调用 `find_emails`：folder="inbox/reporting", received_after="2026-02-25", has_attachments=true
3. 调用 `get_all_attachments` 提取所有附件
4. 调用 `attachment_analyzer.parse` 解析每个附件
5. 汇总内容，生成分析报告
6. 返回结果（或调用 send_email 发送）

## Important Notes

### 搜索失败策略（重要！）
- 如果第一次搜索没有结果，**必须尝试以下方法**：
  1. 去掉日期限制，扩大搜索范围
  2. 放宽主题关键词（用更短的关键词）
  3. 增大 max_results
  4. 尝试不同的文件夹
- **不要**搜不到就直接告诉用户"没找到"——先放宽条件重试！

### 自动执行要求（重要！）
- 用户说"分析邮件"后，**自动执行**以下所有步骤：
  1. 查找邮件
  2. 提取所有附件（不要问用户！）
  3. 解析附件内容
  4. 生成报告
  5. 发送邮件（如果用户要求）
- **不要**在每一步后追问用户"需要继续吗"
- **直接执行**完整 workflow，用户只需要等待结果

### 执行力要求
- 当用户要求"发邮件给我"或"发送到邮箱"时，**必须**调用 `outlook.send_email`
- 不要只是回复"请检查" — 必须实际执行发送操作

### 附件处理
- 附件默认保存到系统临时目录
- 对于大型文件，解析可能需要一些时间
- 确保 Outlook 应用程序已启动且未处于脱机状态
