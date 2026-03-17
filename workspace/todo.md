# Nanobot 演进 TODO

> 本文件是项目持续演进的唯一入口。新对话时先阅读此文件，无需重读已完成的代码。
> 最后更新: 2026-03-15 (Phase 12-14 计划新增)

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

**测试总计: 351 passed, 2 failed (pre-existing) (34.89s)**

### Phase 9: 知识持续进化（Skill Evolution） — 受 AutoSkill 论文启发

核心理念：将 AutoSkill (ECNU/上海AI Lab, 2026) 的"版本化技能迭代 + 智能合并"融入 Nanobot。
参考分析详见 `autoskill_analysis.md`。

- [x] **P0: 知识条目版本化 + 自动合并** — `version` 字段，`merge_task()`, `find_similar_task()`, `tokenize_key()` 共享分词, 保存时自动合并
- [x] **P1: 静默步骤更新** — 成功时自动更新 `steps_detail`，`session.last_tool_calls` 传递工具调用数据
- [x] **P2: `/kb` 知识库管理命令** — `/kb list`, `/kb cleanup` (去重合并), `/kb delete`
- [x] **P3: ChromaDB 语义匹配** — 条目>100时启用向量搜索 fallback (cosine ≥ 0.7)
- [x] `tests/test_knowledge_versioning.py` — 40 测试全部通过

### RPA 混合架构路线图
- [x] **短期: 文本匹配** — `ui_name` 参数按名称匹配 `anchors.json`，跳过 VLM（已实施）
- [x] **中期: PaddleOCR 集成** — UI Automation 失效时用 OCR 读取屏幕文字
- [x] **长期: YOLO UI 检测** — 无 Accessibility API 时用视觉检测 UI 元素（`yolo_detector.py` + GPA-GUI-Detector 模型）
- [x] **多显示器支持** — 支持跨屏幕 RPA 操作

### 记忆系统增强（mem9 启发）
- [x] **Session End Hook** — `/new` 时自动保存会话摘要到 daily log
- [x] **统一 Memory CRUD** — `memory` 工具支持 store/search/delete，替代只读的 MemorySearchTool
- [x] **记忆意图检测** — 识别"记住"/"remember" 等触发词，自动提示 LLM 保存记忆
- [x] **标签系统** — 记忆条目支持 tags，搜索时可按 tag 过滤
- [x] **记忆导入/导出** — `/memory export` 和 `/memory import` 命令
- [x] **记忆策略注入** — system prompt 中注入存储策略指导
- [x] `tests/test_memory_tool.py` — 33 测试全部通过

### Phase 11: 深度优化
- [x] **P0: 死代码清理 + `loop.py` 瘦身** — 删除 2 个未引用方法，提取内联常量到模块级，减少 ~90 行
- [x] **P1: Token 用量追踪** — `metrics.py` 新增 `record_tokens()`/`get_tokens()`，`/stats` 展示 token 汇总
- [x] **P2: LLM 调用重试** — `litellm_provider.py` 指数退避重试（最多 2 次），仅对超时/5xx/连接错误重试
- [x] **P3: 新增测试** — `test_loop_cleanup.py` (7), `test_metrics_tokens.py` (10), `test_provider_retry.py` (12)
## 🔲 待完成

### Phase 12: 知识系统升级 — 受 AutoSkill (ECNU) & XSKILL (HKUST) 论文启发

核心理念：
- **AutoSkill**: 结构化 SKILL.md 表示(triggers/tags/description) + Dense+BM25 混合检索 + add/merge/discard 管理判定 + 版本合并
- **XSKILL**: Skill(任务级工作流) + Experience(动作级战术提示) 双流设计 + 检索后适配

- [ ] **P0: 结构化知识表示增强** — task_knowledge.py 扩展 TaskEntry 新增 triggers, tags, description, nti_patterns, confidence 字段；knowledge_workflow.py 适配新字段
- [ ] **P1: 混合检索 (Dense + BM25)** — knowledge_workflow.py 新增 hybrid_match()，复用现有 ChromaDB 做 dense matching + jieba+Jaccard 做 BM25 近似，λ=0.6 加权，阈值过滤
- [ ] **P2: Experience 层引入** — 新建 experience_bank.py，实现轻量 Experience CRUD (condition→action 对)，与 LLM 执行后的工具调用序列集成，失败路径自动提取 Experience
- [ ] **P3: Knowledge Management Judge** — knowledge_workflow.py 新增 _judge_management() add/merge/discard 三分决策（先规则驱动，可选 LLM 增强）
- [ ] **新增测试** — test_hybrid_retrieval.py (~12), test_experience_bank.py (~10), test_knowledge_judge.py (~8), test_knowledge_schema.py (~6)

### Phase 13: 检索增强

- [x] **P0: Query Rewriting** — 增强 knowledge_workflow.py 的 extract_key()，复杂/多轮对话时生成检索友好的独立查询（指代消解）
- [x] **P1: 检索后适配 (Retrieval-time Adaptation)** — knowledge_workflow.py 新增 _adapt_knowledge()，检索到知识后根据当前上下文裁剪/改写再注入

### Phase 14: 工程卫生

- [ ] **P0: 根目录清理** — 移除/归档 90+ 个 llm_payload_*.json，散落的 test_*.py 统一移入 tests/，旧分析报告归档到 docs/
- [ ] **P1: loop.py 进一步模块化** — 提取知识库交互逻辑到 knowledge_handler.py，提取 pending 状态机处理到独立方法，目标降至 700 行以下
- [ ] **P2: 类型提示完善** — 核心模块 (loop.py, knowledge_workflow.py, context.py) 添加完整 type hints，配置 mypy 基础检查

### 未来方向（讨论过但未规划）
- [ ] **多用户系统**: 会话隔离、权限模型
- [ ] **Web Dashboard**: Agent 活动可视化

---

## 📝 关键知识点（供新对话参考）

### 架构决策
- **不做 Router/Expert 分离** — 单 Agent 够用，LLM 自选 tool，省 token
- **知识匹配策略演进** — Phase 9 前用 jieba+Jaccard 精确匹配（零 LLM cost）；Phase 12 将引入 Dense+BM25 混合检索作为增强路径，保留 jieba+trigger 快速匹配为默认
- **不做 incremental checkpointing** — 任务短小，SubagentManager 足够
- **双流知识设计 (Phase 12)** — Skill = 宏观工作流(steps)；Experience = 微观战术提示(condition→action)。受 XSKILL 论文启发

### 论文参考
- **AutoSkill** (ECNU/上海AI Lab, 2026): `2603.01145v2.pdf` — 显式 SKILL.md 工件、版本化技能迭代、混合检索、Management Judge
- **XSKILL** (HKUST/浙大/华科, 2026): `2603.12056v1.pdf` — Skill+Experience 双流、跨路径对比、层次化合并、检索后适配

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
# 运行所有核心测试（排除需要 API key 的 skill 测试和 gemini 测试）
cd d:\Python\nanobot
$env:NO_PROXY="*"; $env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
.venv311\Scripts\python.exe -m pytest tests/ --ignore=tests/skill --ignore=tests/test_gemini.py -q
```
