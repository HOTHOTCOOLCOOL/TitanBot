# Outlook Email Analysis Skill 安装指南

## 概述

这个技能可以让 nanobot 自动分析 Outlook 邮件附件并生成分析报告。

## 功能

1. 搜索 Outlook 邮件（支持文件夹、日期、发件人等条件）
2. 下载邮件附件（PDF、Word、Excel等）
3. 解析附件内容
4. 使用本地 LLM 生成分析报告

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install pywin32 PyPDF2 python-docx pandas openai
```

- `pywin32`: 用于 Outlook COM 接口（Windows 必须）
- `PyPDF2`: PDF 解析
- `python-docx`: Word 文档解析
- `pandas`: Excel/CSV 解析
- `openai`: 调用本地 LLM

### 2. 复制工具文件

将以下文件复制到 nanobot 工具目录：

```
resources/outlook-email-analysis/
├── outlook.py              -> nanobot/agent/tools/outlook.py
├── attachment_analyzer.py  -> nanobot/agent/tools/attachment_analyzer.py
└── SKILL.md               -> nanobot/skills/outlook-email-analysis/SKILL.md
```

或者直接运行：
```bash
copy resources\outlook-email-analysis\outlook.py nanobot\agent\tools\
copy resources\outlook-email-analysis\attachment_analyzer.py nanobot\agent\tools\
copy resources\outlook-email-analysis\SKILL.md nanobot\skills\outlook-email-analysis\
```

### 3. 确保 Outlook 工具已注册

在 `nanobot/agent/loop.py` 中，确保已添加以下代码：

```python
from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool

# 在 _register_default_tools() 方法中添加：
self.tools.register(OutlookTool())
self.tools.register(AttachmentAnalyzerTool())
```

### 4. 运行 nanobot

```bash
# 方式1：从源码安装
cd nanobot
pip install -e .
nanobot agent

# 方式2：直接运行
python -m nanobot agent
```

## 使用方法

启动 nanobot 后，直接说：

> "帮我分析 inbox/reporting 中今天的邮件"

或者：

> "分析 outlook 附件"

## 配置

### LLM 配置

在 `~/.nanobot/config.json` 中添加本地 LLM：

```json
{
  "providers": {
    "custom": {
      "apiKey": "your-api-key",
      "apiBase": "http://localhost:5888/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "your-model-name"
    }
  }
}
```

## 依赖要求

- Windows 操作系统
- Microsoft Outlook（需保持运行）
- Python 3.11+
- 本地 LLM API（如 MiniMax、Ollama 等）

## 常见问题

### Q: 为什么找不到附件？
A: 请确保 Outlook 应用程序正在运行，且邮箱不是脱机状态。

### Q: 为什么日期筛选不生效？
A: 检查日期格式是否正确，应为 YYYY-MM-DD（如 2026-02-20）。

### Q: 如何修改搜索的文件夹？
A: 在请求中指定，如 "inbox/Reporting" 或 "Inbox/Village_Tenant"。

## 文件说明

| 文件 | 说明 |
|------|------|
| outlook.py | Outlook 邮件处理工具 |
| attachment_analyzer.py | 附件解析工具 |
| SKILL.md | Skill 定义文档 |
| INSTALL.md | 本安装指南 |

## 技术细节

- Outlook 附件使用 0-based 索引
- 邮件搜索默认返回最近 100 封中的前 10 封
- 自动过滤图片附件（签名等）
- 支持的文档格式：PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV
