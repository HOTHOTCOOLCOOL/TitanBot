---
name: outlook-email-search
description: 搜索和阅读Outlook邮件（查找特定邮件、查看邮件内容、查看回复）
homepage: https://github.com/HOTHOTCOOLCOOL/nanobot
metadata:
  nanobot:
    emoji: 🔍
    requires:
      bins: [python]
      env: []
    tags: [email, outlook, search, read]
    always: true
    type: workflow
---

# outlook-email-search

**搜索和阅读Outlook邮件**

## When to use (trigger phrases)

使用这个技能，当用户要求：
- "帮我找XX的邮件"
- "最近一次XX发给我的邮件"
- "XX给我发了什么"
- "我怎么回复的"
- "查看邮件内容"
- "找一下发给XX的邮件"
- 任何关于搜索、查找、阅读邮件内容的请求

## Workflow Steps

### Step 1: 分析用户意图

判断用户在找什么类型的邮件：
- **收到的邮件**: 使用 `folder="inbox"` (默认)
- **发出的邮件**: 使用 `folder="sent"`（当用户说"我发给XX的"、"我怎么回复的"）
- **特定人发来的**: 使用 `from_email` 参数
- **发给特定人的**: 使用 `to_email` 参数 + `folder="sent"`

### Step 2: 搜索邮件

使用 `outlook` 工具的 `find_emails` 操作：

```json
{
  "action": "find_emails",
  "criteria": {
    "folder": "inbox",
    "from_email": "person@example.com",
    "max_results": 10
  }
}
```

**关键提示**：
- `from_email` 支持部分匹配（例如只写 "harvey" 可以匹配 harveychen@company.com）
- 如果第一次没找到，**放宽条件**：去掉日期限制、增大 max_results
- 如果从 inbox 找不到，尝试在 sent 文件夹中搜索

### Step 3: 阅读邮件内容

找到邮件后，使用 `read_email` 操作获取完整内容：

```json
{
  "action": "read_email",
  "email_index": 0
}
```

这会返回邮件的完整正文（不只是预览）。

### Step 4: 查看回复（如需）

如果用户问"我怎么回复的"：
1. 先在 inbox 找到原始邮件
2. 然后在 sent 文件夹中搜索，用 `to_email` 过滤

```json
{
  "action": "find_emails",
  "criteria": {
    "folder": "sent",
    "to_email": "person@example.com",
    "max_results": 10
  }
}
```

## Usage Examples

### 例1: 查找特定人发的邮件
> 用户: "帮我找最近一次 Harvey Chen 发给我的邮件"

```
1. find_emails(criteria: {from_email: "harveychen", max_results: 5})
2. read_email(email_index: 0)  // 读取最近的一封
```

### 例2: 查找我的回复
> 用户: "我怎么回复Harvey的"

```
1. find_emails(criteria: {folder: "sent", to_email: "harveychen", max_results: 5})
2. read_email(email_index: 0)
```

### 例3: 查找特定日期的邮件
> 用户: "2月11日 Harvey 发给我的邮件"

```
1. find_emails(criteria: {from_email: "harveychen", received_after: "2026-02-11", received_before: "2026-02-12"})
2. read_email(email_index: 0)
```

## Important Notes

### 搜索策略
- **先精确后宽泛**: 先用具体条件搜索，没结果再放宽
- **from_email 用部分匹配**: 不需要完整邮箱地址，名字就够
- **日期范围查2天**: 如搜2月11日，用 received_after=2月11日, received_before=2月12日
- **大小写不敏感**: 所有搜索条件都不区分大小写

### 不要做的事
- **不要**在每一步后停下来问用户——直接执行完整流程
- **不要**只返回邮件摘要——如果用户问内容，用 read_email 获取全文
- **不要**在任务未完成时询问是否保存到知识库
- **不要**在找不到邮件时直接放弃——尝试放宽条件重新搜索
