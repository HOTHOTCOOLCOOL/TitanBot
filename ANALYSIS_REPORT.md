# 代码问题分析与修复方案

## 一、需求回顾

### 用户原始需求：
1. **Outlook 邮件处理 Skill**：根据条件（日期/目录/发件人）查找邮件 → 提取附件 → 用本地 LLM 分析 → 发送报告
2. **技能自动保存**：Agent 完成复杂任务后，在用户确认满意时自动保存为可重用技能
3. **通用性**：Skill 应该能被其他 Agent 或未来复用，不需要大幅修改

---

## 二、问题清单（已修复）

### ✅ 问题 1：Outlook Tool 状态管理问题 - 已修复

**修复内容**：
- 添加 `_current_folder_name` 跟踪当前搜索的文件夹
- 添加 `_last_search_results` 存储搜索结果及其原始索引
- 修复 `get_attachment` 使用正确的文件夹和邮件索引
- 在搜索结果中明确告知用户使用的文件夹和索引
- 添加错误验证防止无效索引

---

### ✅ 问题 2：LOOP.PY 未注册新工具 - 已修复

**修复内容**：
- 在 `loop.py` 中导入 `OutlookTool` 和 `AttachmentAnalyzerTool`
- 在 `_register_default_tools()` 中注册两个新工具

---

## 三、待修复问题

### 问题 3：Skill 无法真正复用 🔴 严重

**现状**：
- SKILL.md 只是一个 Markdown 说明文档
- Agent 读取 SKILL.md 后，仍然需要理解自然语言描述
- 每次使用都需要重新规划步骤

**修复方案**（后续）：
- 创建结构化的 Skill 执行器
- 或在系统提示中增加"强制确认"机制

---

### 问题 4：用户确认机制缺失 🟡 中等

**现状**：
- SaveSkillTool 需要用户手动调用
- 没有自动触发"是否保存技能"的流程

**修复方案**（后续）：
- 在系统提示中增加"任务完成后的反思步骤"
- 或添加"ask_confirmation"工具

---

### 问题 5：Skill 中的 LLM 调用缺失 🟡 中等

**现状**：
- attachment_analyzer 只做文件解析
- 没有调用 LLM 进行智能分析

**修复方案**（后续）：
- 创建 llm_analyzer 工具，调用本地 LLM
- 或增强 attachment_analyzer，添加 "analyze" action

---

## 四、当前可测试的功能

### 已完成的功能：
1. ✅ `outlook.find_emails` - 根据条件查找邮件（支持：主题/发件人/日期/文件夹/附件）
2. ✅ `outlook.get_attachment` - 提取附件（自动使用上次搜索的文件夹和索引）
3. ✅ `outlook.send_email` - 发送邮件
4. ✅ `outlook.list_folders` - 列出邮件文件夹
5. ✅ `attachment_analyzer.parse` - 解析附件内容（PDF/Excel/Word/文本/CSV）
6. ✅ `save_skill` - 保存工作流为可重用技能

### 需要安装的 Python 包：
```bash
pip install pywin32 PyPDF2 python-docx pandas
```

### 需要配置的 LLM：
在 `~/.nanobot/config.json` 中配置：
```json
{
  "providers": {
    "custom": {
      "apiKey": "none",
      "apiBase": "http://10.18.34.60:5888/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "minimax-m2.5-mlx",
      "maxTokens": 190000
    }
  }
}
```

---

## 五、测试步骤

1. 确保已安装必要的 Python 包
2. 确保 Outlook 应用程序正在运行
3. 启动 nanobot：`nanobot agent`
4. 测试查找邮件：`请帮我查找上周从 report@example.com 发来的带有附件的邮件`
5. 测试提取附件：使用返回的索引获取附件
6. 测试解析附件：使用 attachment_analyzer 解析文件
7. 测试保存技能：如果结果满意，使用 save_skill 工具保存

---

*分析时间：2026-02-20*
*最后更新：2026-02-20 修复完成*
