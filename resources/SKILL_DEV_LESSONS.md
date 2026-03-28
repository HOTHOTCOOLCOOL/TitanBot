# Skill 开发经验教训

## 概述

本文档记录了在开发 nanobot skill 过程中遇到的问题及解决方案，用于指导未来 skill 开发。

---

## 问题 6: Cron Job 的业务逻辑理解

### 问题描述
Cron job "每天早上 8:20 获取昨日销售报告"，但实际的业务含义是：
- 邮件是"今天"收到的
- 邮件内容反映的是"昨天"的数据
- 所以 prompt 应该告诉 agent："检查今天收到的邮件"

### 根本原因
对业务场景的理解不准确：
- 很多定时任务都是"反应前一天状况"的报告
- 早上 8:20 的 job 检查的是"今天"收到的邮件
- 但邮件内容是"昨天"发生的事件

### 解决方案
在 Cron job 的 message/prompt 中明确说明：
```
"检查今天收到的邮件（反映昨日的销售数据）"
```

而不是：
```
"检查昨日的邮件"
```

### 经验教训
> 定时任务的业务逻辑需要仔细理解时间语义：
> - 邮件接收时间 ≠ 邮件内容时间
> - 任务执行时间 ≠ 数据发生时间
> - 需要在 prompt 中明确时间范围

---

## 问题 7: Git 操作导致代码丢失

### 问题描述
使用 `git checkout` 恢复文件后，之前的手动修改全部丢失。

### 解决方案
- 永远不要用 `git checkout` 恢复整个文件
- 用 `git diff` 查看具体改动
- 修改前先备份

### 经验教训
> 修改代码前先用 `git diff > changes.patch` 备份

---

## 问题 8: LLM 执行力不足 - 多步 Workflow 无法自动完成

### 问题描述
用户让 nanobot "分析邮件并发送报告"，但 LLM 只执行了第一步（查找邮件），然后追问用户"需要继续吗？"，而不是自动完成后续步骤。

### 根本原因
- LLM 默认行为是"谨慎"，每步都等用户确认
- 工具和 SKILL.md 没有明确要求自动执行
- LLM 不知道用户期望的是"一气呵成"的完整 workflow

### 解决方案
在两个地方添加明确的"执行力要求"：

**1. 工具 description（outlook.py）:**
```python
IMPORTANT (执行力要求):
1. When user says "analyze emails" or "analyze attachments", you MUST:
   a) Call find_emails to get today's emails
   b) Call get_all_attachments to extract ALL attachments (don't ask user!)
   c) Analyze each attachment
   d) Generate report
   e) Send email if user requested
2. DO NOT ask "do you want me to continue?" after each step
3. Just EXECUTE the full workflow automatically
```

**2. SKILL.md:**
```markdown
### 自动执行要求（重要！）
- 用户说"分析邮件"后，**自动执行**以下所有步骤：
  1. 查找邮件
  2. 提取所有附件（不要问用户！）
  3. 解析附件内容
  4. 生成报告
  5. 发送邮件
- **不要**在每一步后追问用户"需要继续吗"
- **直接执行**完整 workflow
```

### 经验教训
> 对于复杂的多步骤 workflow，必须在**工具 description** 和 **SKILL.md** 中同时添加明确的"自动执行"指令。
> LLM 需要明确的行动指引，而不是模糊的"可选"描述。

---

### 问题描述
邮件有 3 个 PDF 附件，但只能保存最后一个。

### 根本原因
Outlook COM 对象的索引规则不一致：
- **Items 集合**: 1-based 索引（从 1 开始）
- **Attachments 集合**: 0-based 索引（从 0 开始）

### 解决方案
```python
# Items 使用 1-based
item = items[i + 1]

# Attachments 使用 0-based
attachment = item.Attachments[0]  # 正确
attachment = item.Attachments[1]  # 错误：list index out of range
```

### 经验教训
> 在使用 COM 对象时，必须通过实验验证索引规则，不能假设。

---

## 问题 2: HasAttachments 属性不可靠

### 问题描述
`item.HasAttachments` 总是返回 False 或报错。

### 根本原因
某些邮件项目类型（MeetingItem, TaskItem 等）没有 HasAttachments 属性，或者属性访问出错。

### 解决方案
直接访问 Attachments.Count：
```python
# 旧方式（不可靠）
if item.HasAttachments:
    ...

# 新方式（可靠）
if item.Attachments.Count > 0:
    ...
```

### 经验教训
> 对于复杂的 COM 对象，使用最基础的属性（如 .Count）而不是高级属性。

---

## 问题 3: 日期时区比较错误

### 问题描述
日期筛选时出现错误：`can't compare offset-naive and offset-aware datetimes`

### 根本原因
Outlook 返回的 datetime 对象有时区信息（aware），而 Python datetime.strptime 返回的没有时区（naive）。

### 解决方案
```python
def _normalize_datetime(dt):
    """移除时区信息以便比较"""
    if dt and dt.tzinfo is not None:
        try:
            return dt.replace(tzinfo=None)
        except:
            return dt
    return dt

# 使用
received_time_normalized = self._normalize_datetime(received_time)
if received_time_normalized < target_date:
    ...
```

### 经验教训
> 处理外部 API（特别是 COM/Windows）返回的日期时，始终检查时区。

---

## 问题 4: 测试策略不当

### 问题描述
花费大量时间在完整 workflow 测试中，而不是先验证单个组件。

### 解决方案
采用渐进式测试策略：

1. **单元测试**: 先测试单个工具函数
2. **调试脚本**: 创建最小化复现问题的脚本
3. **逐步集成**: 每个组件验证后再集成

### 推荐的调试脚本结构
```python
#!/usr/bin/env python
"""调试脚本 - 验证特定功能"""

import asyncio
import sys
sys.path.insert(0, "路径")

from nanobot.agent.tools.outlook import OutlookTool

async def main():
    tool = OutlookTool()
    
    # 只测试一个功能点
    result = await tool.execute(...)
    print(result)

asyncio.run(main())
```

### 经验教训
> 不要在完整环境中测试新代码。先用最小脚本验证。

---

## 问题 5: 目录路径处理

### 问题描述
用户使用不同的路径格式：`inbox/reporting`、`Inbox/Reporting`、`reporting`

### 解决方案
统一处理：
```python
def _get_folder(self, folder_path: str):
    # 标准化路径
    folder_path = folder_path.replace('\\', '/').lower()
    
    # 支持多种格式
    if folder_path.startswith('inbox/'):
        # 从 Inbox 开始
        ...
    else:
        # 直接匹配根文件夹
        ...
```

### 经验教训
> 用户输入格式多样，需要在工具层面标准化处理。

---

## 开发最佳实践清单

### 开始新 Skill 前
- [ ] 阅读目标系统的 API 文档
- [ ] 了解 COM/外部库的索引规则
- [ ] 创建单元测试框架

### 开发过程中
- [ ] 每实现一个功能就单独测试
- [ ] 使用调试脚本而非完整 workflow
- [ ] 记录所有"意外"发现

### 测试阶段
- [ ] 测试边界条件（空结果、0 索引、超大文件）
- [ ] 测试不同时区/语言环境
- [ ] 测试用户可能输入的各种格式

### 交付前
- [ ] 清理调试文件到 debug/ 目录
- [ ] 创建安装/使用文档
- [ ] 验证所有依赖已声明

---

## 文件结构建议

```
project/
├── nanobot/              # 源代码（不提交）
│   ├── agent/tools/     # 工具实现
│   └── skills/          # Skill 定义
├── resources/           # 发布资源
│   └── skill-name/
│       ├── *.py
│       ├── SKILL.md
│       └── INSTALL.md
├── debug/               # 调试文件（不提交）
│   └── test_*.py
└── tests/              # 单元测试
```

---

## 关键 API 参考

### Outlook COM 对象
| 集合 | 索引方式 | 示例 |
|------|---------|------|
| Items | 1-based | `items[1]` |
| Attachments | 0-based | `attachments[0]` |
| Folders | 1-based | `folders[1]` |

### 日期处理
- 始终使用 `_normalize_datetime()` 处理外部日期
- 存储时使用 ISO 格式字符串
- 比较时确保时区一致

---

# Nanobot 记忆模式：避免 Prompt 臃肿的最佳实践

## Nanobot 的记忆机制

Nanobot 使用**两层记忆系统**来避免 prompt 无限增长：

### 1. 短期记忆 (Memory Window)
- 只保留最近 N 条对话（如 50 条）
- 超过阈值时触发**记忆整合**

### 2. 长期记忆 (Long-term Memory)
- `MEMORY.md`: 关键事实和偏好
- `HISTORY.md`: 可 grep 搜索的历史记录

### 3. 记忆整合 (Consolidation)
当对话超过阈值时：
1. 调用 LLM 总结旧对话
2. 提取关键信息写入 MEMORY.md
3. 写入 HISTORY.md（可搜索）
4. 保留最近的对话

---

## 如何应用到 Skill 开发

### 1. 分离关注点

**不要把所有信息塞进 prompt**：
```
❌ 错误示例：
"你是邮件分析助手，支持以下功能：
- 搜索Outlook邮件（参数：folder, date, sender...）
- 附件解析（支持PDF, DOCX...）
- LLM分析...
记住用户偏好：喜欢详细报告..."
```

**正确做法**：
```
✓ 正确示例：
系统 prompt 只包含：
- 简短的角色定义
- 工具使用说明（引用 SKILL.md）
- 记忆位置提示
```

### 2. 利用外部文档

将详细文档放在外部文件，通过工具引用：

```python
# 在 tool description 中
description = """Mail tool. See skills/mail/SKILL.md for full docs."""
```

### 3. 动态加载上下文

只有需要时才加载额外信息：

```python
async def execute(self, action, **kwargs):
    if action == "complex_analysis":
        # 只有复杂任务才加载额外上下文
        context = self._load_extended_context()
        ...
```

### 4. 分层记忆策略

| 信息类型 | 存储位置 | 何时加载 |
|---------|---------|---------|
| 工具使用说明 | SKILL.md | 按需 |
| 用户偏好 | MEMORY.md | 每次对话 |
| 历史经验 | HISTORY.md | 搜索时 |
| 当前对话 | Session | 最近 50 条 |

---

## Skill 开发的记忆模式建议

### 对于 Skill 开发者

1. **SKILL.md 保持简洁**
   - 只包含触发条件和快速参考
   - 详细文档放外部

2. **利用工具描述**
   - 工具的 `description` 属性应该是快速参考
   - 完整参数列表在代码注释或外部文档

3. **状态外部化**
   - 不要在 prompt 中存储大量状态
   - 使用类属性或外部存储

### 示例：良好的工具描述

```python
@property
def description(self) -> str:
    return """Outlook mail tool.

Quick reference:
- find_emails(folder, date, sender, has_attachments)
- get_attachment(email_index, save_dir)
- Full docs: nanobot/skills/outlook/SKILL.md"""
```

---

## 总结

Nanobot 的记忆模式核心思想：

1. **分层存储**: 短期/长期/外部文档
2. **按需加载**: 不一次性加载所有信息
3. **自动整合**: 定期总结和压缩
4. **可搜索历史**: 快速检索而非全部加载

这种模式可以应用到任何需要长期运行的 AI 系统中，避免 prompt 随时间无限增长。

---

## 问题 9: 第三方框架 (如 Browser-Use) 集成时的“秒退”与配置不兼容

### 问题描述
引入 `browser-use` 库并包装为 `browser_use_worker` 工具后，大模型调用该工具时在日志中显示 `completed in 0.0s` 并直接返回失败提示，没有触发任何框架层的 Exception traceback。系统看似正常工作，实则是死循环报错。

### 根本原因
代码犯了三个致命错误：
1. **配置属性名乱用**：在实例化大模型时，错误使用了 `provider_cfg.base_url`（系统实际定义的属性叫 `api_base`），导致隐式的 `AttributeError`。
2. **大模型名称带有系统级别前缀**：Nanobot 默认把路由前缀附在名字上（如 `volcengine/doubao-seed...`），而 `browser-use` 底层实例化的是 `langchain_openai.ChatOpenAI`，它不认识这种 LiteLLM 专用的路由前缀，预期是一个纯净的名称。
3. **最严重的：用外层 Return 彻底吞噬了异常堆栈 (Swallowed Exceptions)**：在工具捕获初始化错误时写了 `except Exception as e: return f"Error: ... {e}"`。这导致 `AttributeError` 被当成普通的对话文本塞给了 Agent 模型，而系统日志中 **完全没有打印红色的 ERROR**，看起来就像工具光速执行完。

### 解决方案
```python
# 1. 统一获取配置，认准正确的内部属性或 Getter 方法
base_url = cfg.get_api_base(model_name)

# 2. 清洗系统特有前缀，适配外部的 LangChain 框架
bare_model = model_name.split("/", 1)[-1] if "/" in model_name else model_name

try:
    llm = ChatOpenAI(model=bare_model, base_url=base_url, ...)
except Exception as e:
    # 3. 必须先写 Error Log 记录堆栈，再 return 简短报错
    logger.error(f"BrowserUseWorker: LLM init failed: {e}")
    return f"Error: Failed to init LLM: {e}"
```

### 经验教训
> **绝不要在 Tool 的外层用纯字符串 return 吞没底层框架的异常堆栈！**
> 当你集成庞大的第三方库时，外层一定要加上 `logger.error(..., exc_info=True)` 或详尽的 `logger.exception`，然后才返回给 Agent LLM 可以消化的 `Error:` 短文本。没有日志就没有调试线索。
> **跨框架传递模型参数时，务必考虑名与值的映射清洗！** `api_base` vs `base_url`、带前缀 vs 不带前缀的裸名称，强行跨体系透传直接导致全线崩溃。

---

*本文档应持续更新，记录更多经验教训。*
