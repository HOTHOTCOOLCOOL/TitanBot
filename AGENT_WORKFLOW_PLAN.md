# 智能任务执行工作流程规划 v3

## 🎯 核心理念

**Lightweight + Smart**：不是做一个企业级编排引擎，而是让一个轻量 Agent 越用越聪明。

```
用户任务 → 提取Key → 知识库匹配 → 复用/执行 → 用户确认保存 → 隐式反馈 → 自动升级Skill
```

---

## ✅ 已实现

| 模块 | 文件 | 状态 |
|------|------|------|
| 知识库工作流引擎 | `knowledge_workflow.py` | ✅ Key提取→代码级匹配→保存→升级 |
| 知识库质量追踪 | `task_knowledge.py` | ✅ success/fail计数→成功率→Few-shot |
| 隐式反馈 | `loop.py` | ✅ 下一消息自动推断成败 |
| Few-shot 注入 | `loop.py` + `knowledge_workflow.py` | ✅ 重新执行时注入历史成功步骤 |
| Knowledge→Skill 升级 | `loop.py` + `knowledge_workflow.py` | ✅ 成功≥3次自动提示升级 |
| 记忆整合 | `loop.py` + `memory.py` | ✅ 每20条消息自动consolidation |
| 国际化 | `i18n.py` | ✅ zh/en 双语消息 |
| 会话持久化 | `session/manager.py` | ✅ pending_knowledge/save/upgrade + 消息计数器 |
| 语言配置 | `config/schema.py` | ✅ language 字段 |
| 测试覆盖 | `tests/` | ✅ 204 tests passing |

---

## 🏗️ 架构决策

### ❌ 不做：多 Expert 架构

**理由**：LLM 本身就是最好的 Router。把所有工具注册给一个 Agent，LLM 会自己选择正确的工具。
多 Expert 增加一层不必要的 LLM 调用开销，且跨 Expert 任务（如"搜邮件然后发给同事"）无法自然处理。

> 单 Agent + 全工具集 = nanobot 的核心优势

### ❌ 不做：LLM 语义匹配

**理由**：知识库条目通常 ≤100 个。代码级匹配（精确→子串→词频）足够准确，且零 token 消耗。
只在 Key 提取阶段使用一次轻量 LLM 调用（temperature=0.1, max_tokens=100）。

### ❌ 不做：增量更新 / 断点续传

**理由**：nanobot 任务通常在 2-20 个 tool call 内完成。长任务用已有的 SubagentManager 即可。
实现断点续传需要序列化 LLM 上下文，大多数 LLM API 不支持。

### ❌ 不做：自动知识沉淀

**理由**：LLM 判断"质量"标准主观，误判率高。自动保存导致知识库膨胀，匹配精度下降。
用户手动确认保存 = 高质量知识库。等积累足够数据后再考虑自动化。

---

## 🔄 当前工作流程

```
用户: "帮我分析上周发给老板的报表邮件"

1. KnowledgeWorkflow.extract_key()
   → "分析上周报表邮件" (LLM 提取，≤50字)

2. KnowledgeWorkflow.match_knowledge()
   → 精确匹配 / 子串匹配 / jieba 分词相似度
   → 找到: "分析报表邮件"（成功率 100%, 执行 3 次）

3. 用户选择
   → "直接用": 返回保存的结果
   → "重新执行": LLM 重新处理（注入 Few-shot 参考步骤）

4. 执行完成后
   → 有工具调用 → 询问是否保存
   → 用户回复"是" → 保存到知识库
   → 成功≥3次 → 提示升级为 Skill

5. 隐式反馈（下一条消息自动触发）
   → 用户正常继续 → record_outcome(key, True)
   → 用户说"不对/错了" → record_outcome(key, False)
```

---

## 📋 待办事项

### P1: 多用户支持（下一阶段）
- [ ] 每个用户独立的知识库分区
- [ ] 会话隔离与身份绑定
- [ ] 多用户并发安全
- [ ] 用户配置个性化（语言偏好等）

### P2: 进阶优化
- [ ] 知识库过期清理机制
- [ ] 匹配结果置信度评分
- [ ] 工具调用统计与分析
- [ ] 性能指标收集（响应时间、token 用量）
- [ ] Tool 扩展: `SqlQueryTool` → `CreateExcelTool` → `CreateDocxTool` → `PbiTool`
- [ ] 向量搜索: 知识库条目 > 100 时考虑 embedding + FTS 混合检索
