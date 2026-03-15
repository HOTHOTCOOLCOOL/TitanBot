# Nanobot 演进 TODO

> 本文件是项目持续演进的唯一入口。新对话时先阅读此文件，无需重读已完成的代码。
> 最后更新: 2026-03-14

---

## 项目概况

Nanobot 是一个轻量级 AI Agent 框架，当前架构核心：
- **单 Agent + 多 Tool** — LLM 自选工具，不需要 Router
- **KnowledgeWorkflow** — 代码级匹配（exact → substring → jieba 分词），零 LLM token
- **MemoryStore** — 文件即真相（`MEMORY.md` + `memory/YYYY-MM-DD.md` 每日日志）
- **TaskTracker** — 任务生命周期管理
- **SessionManager** — 会话持久化 + pending 状态机（pending_knowledge / pending_save / pending_upgrade）
- **本地模型优先** — 通过知识库最佳实践记录 + Few-shot 注入补偿本地模型精度
- **隐式反馈** — 下一条消息自动推断上一任务成败，无需打扰用户
- **自动升级** — 成功≥3次的知识库条目可升级为永久 Skill

---

## ✅ 已完成

### Phase 7: 轻量化重构
- [x] 重写 `AGENT_WORKFLOW_PLAN.md`，明确「不做什么」
- [x] 移除 `SimpleRouter` / `PreAnalyzer` / `KnowledgeDistiller` 及其 import
- [x] 移除死代码 `_save_to_knowledge_base`（引用已删除的 `pre_analyzer`）
- [x] 安装 `jieba`，`_tokenize()` 使用 jieba 分词（fallback 到字符级）
- [x] 添加 `/tasks` 命令 + `_format_tasks_list()` + i18n 消息
- [x] `loop.py` 瘦身 916→783 行 (-14.5%)

### Phase 8 P0-A: 知识库质量追踪
- [x] `task_knowledge.py` — `success_count`, `fail_count`, `last_steps_detail` 字段
- [x] `task_knowledge.py` — `record_success()`, `record_failure()`, `get_success_rate()`, `update_steps_detail()`
- [x] `knowledge_workflow.py` — `record_outcome()`, `is_negative_feedback()`, `format_few_shot_prompt()`, `get_match_stats()`, `should_suggest_skill_upgrade()`, `format_skill_upgrade_prompt()`
- [x] `i18n.py` — `skill_upgrade_prompt`, `skill_upgrade_confirmed`, `knowledge_match_with_stats`
- [x] `session/manager.py` — `Session.last_task_key` 用于隐式反馈追踪
- [x] `tests/test_success_tracking.py` — 20+ 测试全部通过

### Phase 8 P0-B: 记忆系统改进
- [x] `memory.py` — `append_daily_log()`, `read_recent_daily()`, `get_memory_context()`
- [x] `tests/test_memory_daily.py` — 9 测试全部通过

### Phase 8 P1-A: Knowledge → Skill 自动升级
- [x] `loop.py` — save 确认后检查 `should_suggest_skill_upgrade()`，提示升级
- [x] `loop.py` — 用户回复"升级"后自动调用 `SaveSkillTool.execute()`
- [x] `knowledge_workflow.py` — `_UPGRADE_COMMANDS` + `is_upgrade_command()`
- [x] `session/manager.py` — `Session.pending_upgrade` 字段 + 完整序列化

### Phase 8 P1-B: 记忆整合触发优化
- [x] `session/manager.py` — `Session.message_count_since_consolidation` 计数器
- [x] `loop.py` — 每 20 条消息自动触发 consolidation（约束：无 pending 状态时才执行）
- [x] `loop.py` — `_consolidate_memory` 提示词改进：事实→MEMORY.md, 事件→daily log

### Phase 8 延伸: loop.py 集成
- [x] 隐式反馈：`_process_message` 入口检查 `session.last_task_key` + `is_negative_feedback()`
- [x] Few-shot 注入：用户"重新执行"时 `format_few_shot_prompt()` 追加到 system prompt
- [x] 知识匹配显示改用 `knowledge_match_with_stats`（带成功率和执行次数）
- [x] 任务完成后设置 `session.last_task_key = key`
- [x] `tests/test_loop_integration.py` — 28 测试全部通过

**测试总计: 204 passed, 0 failures (8.67s)**

---

## 🔲 待完成

### RPA 混合架构路线图
- [x] **短期: 文本匹配** — `ui_name` 参数按名称匹配 `anchors.json`，跳过 VLM（已实施）
- [x] **中期: PaddleOCR 集成** — UI Automation 失效时用 OCR 读取屏幕文字
- [x] **长期: YOLO UI 检测** — 无 Accessibility API 时用视觉检测 UI 元素（`yolo_detector.py` + GPA-GUI-Detector 模型）
- [x] **多显示器支持** — 支持跨屏幕 RPA 操作

### 未来方向（讨论过但未规划）
- [ ] **Tool 扩展**: `SqlQueryTool` → `CreateExcelTool` → `CreateDocxTool` → `PbiTool`
- [ ] **多用户系统**: 会话隔离、权限模型
- [ ] **向量搜索**: 当知识库条目 > 100 时考虑 embedding + FTS 混合检索

---

## 📝 关键知识点（供新对话参考）

### 架构决策
- **不做 Router/Expert 分离** — 单 Agent 够用，LLM 自选 tool，省 token
- **不做 LLM 相似度匹配** — 用 jieba + Jaccard 代码级匹配，零成本
- **不做 incremental checkpointing** — 任务短小，SubagentManager 足够
- **不做 tagging 记忆** — 参考 OpenClaw，用文件即真相（Markdown 源文件 + 可选索引）

### OpenClaw 记忆系统（参考 d:\python\openclaw）
- 核心理念：**Markdown 文件是唯一真相**
- `MEMORY.md` = 持久事实（偏好、配置、决策），始终注入 prompt
- `memory/YYYY-MM-DD.md` = 每日日志，只读最近 2 天
- Compaction = LLM 把旧对话压缩成摘要
- Pre-compaction flush = 压缩前静默让 LLM 先保存重要信息
- Retain/Recall/Reflect 循环（来自 Letta/MemGPT + Hindsight 研究）
- 混合搜索：BM25 + vector + temporal decay + MMR diversity
- 详见 `d:\python\openclaw\docs\concepts\memory.md` 和 `experiments\research\memory.md`

### 本地模型策略
- 知识库 `success_count/fail_count` 追踪最佳实践
- Few-shot prompt 注入历史成功步骤 → 大幅提升一次成功率
- 隐式反馈（下一条消息推断上一任务成败）避免打扰用户
- 成功≥3次自动建议升级为永久 Skill

### Session 状态机
- `pending_knowledge` — 等待用户选择"直接用"或"重新执行"
- `pending_save` — 等待用户确认保存到知识库
- `pending_upgrade` — 等待用户确认升级为 Skill
- `last_task_key` — 上一个完成的任务 key（用于隐式反馈）
- `message_count_since_consolidation` — 消息计数器（每 20 条自动整合记忆）

### Pyre2 Lint 说明
- 所有 `Could not find import of xxx` 错误是 IDE/Pyre2 venv 配置问题，**不影响运行**
- `pytest` 全量通过是唯一可靠的验证手段

### 测试命令
```bash
# 运行所有核心测试（排除需要 API key 的 skill 测试）
cd d:\Python\nanobot
$env:NO_PROXY="*"; $env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
.venv311\Scripts\python.exe -m pytest tests/ --ignore=tests/skill -q
```
