---
name: outlook-email-analysis
description: 自动分析Outlook邮件附件并发送分析报告
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

## When to use (trigger phrases)

使用这个技能，当用户要求：
- "帮我分析邮件"
- "分析 outlook 附件"
- "分析 inbox/xxx 文件夹的邮件"
- "提取邮件附件"
- "邮件附件分析"
- 任何关于分析 Outlook 邮件附件的请求

## Summary

这个技能允许 nanobot 自动完成以下任务：
1. 根据用户指定的条件（主题、日期，发件人、文件夹）查找 Outlook 邮件
2. 提取邮件中的附件
3. 解析附件内容（支持 PDF、Excel、Word、文本等格式）
4. 使用本地 LLM 分析附件内容
5. 将分析结果发送给用户或指定收件人

## Workflow Steps

### Step 1: 查找邮件
使用 `outlook` 工具的 `find_emails` 操作：
- folder: 文件夹路径（如 "inbox/reporting"）
- subject_contains: 主题关键词
- from_email: 发件人邮箱
- received_after: 起始日期 (YYYY-MM-DD)
- received_before: 结束日期 (YYYY-MM-DD)
- has_attachments: 是否只返回有附件的邮件
- max_results: 返回结果数量限制

### Step 2: 提取附件
使用 `outlook` 工具的 `get_attachment` 或 `get_all_attachments` 操作：
- email_index: 邮件索引（从 find_emails 结果中选择，0-based）
- attachment_index: 附件索引（0-based）
- save_directory: 保存目录（可选，默认临时目录）

### Step 3: 分析附件内容
使用 `attachment_analyzer` 工具的 `parse` 操作：
- file_path: 附件的完整路径
- 工具会自动识别文件类型并解析内容
- 支持 PDF、Excel、Word、文本、CSV 格式

### Step 4: 发送报告（可选）
使用 `outlook` 工具的 `send_email` 操作：
- recipient: 收件人邮箱
- subject: 邮件主题
- body: 邮件内容
- attachment_paths: 要发送的附件路径列表

## Usage Example

用户请求：
> "帮我分析 inbox/reporting 中今天的邮件"

Agent 执行流程：
1. 解析用户请求，确定搜索条件
2. 调用 outlook.find_emails，参数：folder="inbox/reporting", received_after="2026-02-20"
3. 查看返回的邮件列表
4. 调用 outlook.get_all_attachments 提取所有附件
5. 调用 attachment_analyzer.parse 解析每个附件内容
6. 汇总所有内容，使用 LLM 生成分析报告
7. 返回分析结果给用户

## Requirements

### Python 包（需要安装）：
```bash
pip install pywin32 PyPDF2 python-docx pandas openai
```

- pywin32: 用于 Outlook COM 接口
- PyPDF2: 用于 PDF 解析
- python-docx: 用于 Word 文档解析
- pandas: 用于 Excel/CSV 解析
- openai: 用于调用本地 LLM

### 系统要求：
- Windows 操作系统
- 安装并运行 Microsoft Outlook
- 可访问的本地 LLM API

## Notes

- 附件默认保存到系统临时目录
- 对于大型文件，解析可能需要一些时间
- 确保 Outlook 应用程序已启动且未处于脱机状态
- 邮件搜索默认返回最近 100 封邮件中的前 10 封
