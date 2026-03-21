# Nanobot 演进 TODO

> 本文件是项目持续演进的唯一入口。新对话时先阅读此文件，无需重读已完成的代码。
> 最后更新: 2026-03-19

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

### Phase 12: 知识系统升级 — 受 AutoSkill (ECNU) & XSKILL (HKUST) 论文启发
- [x] **P0: 结构化知识表示增强** — TaskEntry 新增 triggers, tags, description, anti_patterns, confidence 字段
- [x] **P1: 混合检索 (Dense + BM25)** — hybrid_match() 复用 ChromaDB + jieba+Jaccard, λ=0.6 加权
- [x] **P2: Experience 层引入** — experience_bank.py，轻量 Experience CRUD (condition→action)
- [x] **P3: Knowledge Management Judge** — add/merge/discard 三分决策（规则驱动）
- [x] 新增测试 — `test_hybrid_retrieval.py`, `test_experience_bank.py`, `test_knowledge_judge.py`

### Phase 13: 检索增强
- [x] **P0: Query Rewriting** — 多轮对话指代消解
- [x] **P1: 检索后适配 (Retrieval-time Adaptation)** — 检索到知识后根据当前上下文裁剪/改写再注入

### Phase 14: 工程卫生
- [x] **P0: 根目录清理** — 归档 90+ 个 llm_payload_*.json，散落 test_*.py 统一移入 tests/
- [x] **P1: loop.py 进一步模块化** — 提取工具注册到 `tool_setup.py`，提取状态机到 `state_handler.py`，提取命令到 `commands.py`，loop.py 降至 671 行
- [x] **P2: 类型提示完善** — 核心模块添加完整 type hints

### Phase 15: Web Dashboard & Unified Identity
- [x] **Web Dashboard** — FastAPI + HTML/JS，实时 WebSocket 日志，知识库/记忆编辑，系统指标
- [x] **Unified Master Identity** — 跨渠道身份映射，严格 `allowFrom` 白名单

### Phase 16: Bug Fixes & Modularization
- [x] **P0:** `match_experience()` 未定义变量崩溃修复、`context.py` `asyncio.run()` 修复
- [x] **P1:** `hybrid_retriever.py` 提取、`mochat_utils.py` 提取、embedding model 配置化、i18n 中文 prompt

### Phase 17: Root Cleanup & Architecture Enhancement
- [x] 根目录文件归档 (23 files)
- [x] `get_metrics()` Dashboard API 修复
- [x] 错误恢复 metrics 计数器
- [x] Experience Bank 边界测试扩展

### Phase 18: 安全审计修复
- [x] **Phase 18A (P0 Critical):** API Key 泄露、Dashboard 认证、Shell 加固、路径遍历修复、Gateway 默认 127.0.0.1
- [x] **Phase 18B (P1 Medium):** 空 allowFrom 警告、master_identities 缓存、错误消息清理、SSRF 防护
- [x] **Phase 18C (P2 Code Quality):** `/reload` 命令修复、内存意图检测常量提升、`__all__` 导出、import 修复
- [x] **Phase 18D (P3 Architecture):** Channel Manager DRY 重构、duck-typed Tool Context、Uptime 指标

**回归基线: 613 passed, 0 failed**

---

## 🔲 待完成

### Phase 19: 文档修复 + 残余问题清理
- [x] `SECURITY.md` 更新 Last Updated 日期，反映 Phase 18 安全修复
- [x] `SECURITY.md` Known Limitations 更新
- [x] `TOOLS.md` 修复 "Adding Custom Tools" 引用旧方法
- [x] `PROJECT_STATUS.md` 第 112 行行数更新
- [x] `test_word_similarity_match` 持续失败修复
- [x] `test_memory_daily.py` 2 个间歇性失败修复
- [x] `_get_config()` 缓存不失效修复
- [x] Session Expiry 机制
- [x] Rate Limiting

### Phase 19+: Performance & Optimization
- [x] Async parallel tool execution
- [x] Context window optimization
- [x] Dashboard v2 Mobile UI
- [x] Cron notifications

**Phase 19+ (已完成)**
- [x] `knowledge_workflow.py` 进一步分解 — 提取 `key_extractor.py` (85 行) + `knowledge_judge.py` (273 行)，主文件从 595→350 行。新增 `test_knowledge_decomposition.py` (18 测试)

### Phase 20: AI Memory Architecture Enhancement (Next)
- [x] 20A: Evicted Context Buffer (MemGPT-style Virtual Paging)
- [x] 20B: CLS Slow-Path Memory Consolidation
- [x] 20C: Time-Decay Retrieval Scoring
- [x] 20D: Metacognitive Reflection Memory
- [x] 20E: Lightweight Entity-Relation Graph
- [x] 20F: Multi-Agent Shared Memory (Architecture placeholder ready)
- [x] 20G: Visual Memory Text Persistence
- [x] 20H: web_fetch PDF Support

### Phase 21A: P0 Security & Critical Fixes
- [x] S1: Shell `cd ..` / `%2e` traversal bypass — deny patterns + workspace guard hardening
- [x] S2: Shell interpreter bypass (`python -c`, `node -e`, `ruby -e`, `perl -e`) — deny patterns
- [x] B1: Concurrent tool exception circuit breaker — break after 3 consecutive all-fail turns
- [x] L1: Implicit feedback false-positive fix — regex word boundaries + negated-positive phrases
- [x] L2: Pending state mutual exclusion — `Session.clear_pending()` + pre-set clearing
- [x] D1: Memory feature on/off switches — `MemoryFeaturesConfig` with 4 flags

**回归基线: 647 passed, 0 failed**

### Phase 21B: P1 Security & Bug Fixes
- [x] S3: WebSocket input validation — 10KB message limit + 30 msgs/min per-connection rate limit
- [x] S4: Memory import path traversal — workspace `is_relative_to()` check
- [x] B2: Fire-and-forget task error logging — `_safe_create_task()` with error callback
- [x] B3: SubagentManager `Config()` per-iteration — cached before loop
- [x] B4: VLM routing fallback — graceful fall-through to default model on missing provider
- [x] L3: `_workflow_succeeded` false negative — removed overly generic `"no results"` from fail indicators
- [x] L4: Consolidation async race condition — `asyncio.Lock` on MemoryManager
- [x] D2: ReflectionStore / KG re-instantiated per call — lazy-cached at AgentLoop level
- [x] D3: System prompt unbounded injection — 8000-char injection budget cap
- [x] C1: Memory store vs consolidation race — shared lock between regular and deep consolidation

**回归基线: 666 passed, 0 failed**

### Phase 21C: P2 Quality & Robustness
- [x] S5: 原子 JSON 写入 — temp file + `os.replace()` (`reflection.py`, `knowledge_graph.py`)
- [x] S6: `<think>` 标签剥离统一 — 新建 `think_strip.py` 工具 + 替换 7 处内联正则
- [x] B5: 空对话合并拦截 — 对话内容为空时跳过 LLM 调用
- [x] B6: Session JSONL UTF-8 编码 — 所有文件 I/O 显式声明 `encoding="utf-8"`
- [x] L5: KB 子串匹配阈值 — 从 0.50→0.65，最短 4 字符
- [x] C2: 深度合并竞态 — C1 共享锁已覆盖，已验证
- [x] C3: 视觉记忆去重 — 内容哈希去重 (`_persisted_visual_hashes`)
- [x] I3: 工具输出全局限制 — `MAX_TOOL_OUTPUT = 50,000` 字符
- [x] I4: Session JSONL 重构 — `_full_rewrite()` + UTF-8
- [x] E3: 查询改写短路 — 无代词时跳过 LLM 调用
- [x] E4: 错误消息 i18n — 8 个新 key + 7 处 commands.py 硬编码替换

**回归基线: 704 passed, 0 failed**

### Phase 21D: Architecture & Config Improvements
- [x] Config singleton 统一
- [x] Dashboard 新增 KB/Reflection/Graph API
- [x] 统一 async task manager
- [x] Knowledge matching 精度提升（语义缓存、自适应阈值）
- [x] Memory 容量管理（prune/expire）

### Phase 21E: Feature Enhancements
- [x] F1: Streaming response delivery — `stream_chat()` async generator on providers, `StreamChunk`/`StreamEvent` dataclasses, `MessageBus` stream pub/sub, `AgentLoop._stream_llm_call()`, Dashboard `/ws/stream` WebSocket, `StreamingConfig` config flag
- [x] F2: Embedding Model Upgrade — `BAAI/bge-m3` (1024-dim, 100+ languages), configurable model path, dimension introspection, automatic ChromaDB collection migration, `local_files_only=True` preserved
- [x] F3: Vision-Language Feedback Loop — `VLMFeedbackLoop` engine (`vlm_feedback.py`), before/after VLM screenshot comparison, `verify` + `expected_outcome` RPA params, configurable retry loop (`VLMFeedbackConfig`), graceful degradation when VLM not configured

**回归基线: 793 passed**

### Phase 21H: Production Hotfix — Dimension Probe + Feishu Image Support
- [x] H9: Vector dimension probe numpy ndarray truthiness — `is not None` + `len()` 替代布尔检查 (L11)
- [x] F4: 飞书图片下载 — `GetMessageResourceRequest` API + `image_downloader.py` 共享工具
- [x] 新增测试: `test_channel_image_support.py` (7), `TestDimensionMigration` (1)

### Future Backlog
- [x] Embedding model upgrade — BAAI/bge-m3 (1024-dim, 100+ 语言) ✅
- [x] Vision-Language feedback loop ✅
- [x] 飞书图片支持 ✅
- [ ] 多渠道图片支持 — MoChat, Slack, DingTalk
- [ ] Plugin marketplace / dependency management
- [ ] PWA Dashboard
- [ ] Playwright Browser Automation

---


## 📝 关键知识点（供新对话参考）

### 架构决策
- **不做 Router/Expert 分离** — 单 Agent 够用，LLM 自选 tool，省 token
- **知识匹配策略演进** — Phase 12 引入 Dense+BM25 混合检索 + jieba+trigger 快速匹配双路径
- **不做 incremental checkpointing** — 任务短小，SubagentManager 足够
- **双流知识设计 (Phase 12)** — Skill = 宏观工作流(steps)；Experience = 微观战术提示(condition→action)

### 论文参考
- **AutoSkill** (ECNU/上海AI Lab, 2026): `2603.01145v2.pdf` — 显式 SKILL.md 工件、版本化技能迭代、混合检索、Management Judge
- **XSKILL** (HKUST/浙大/华科, 2026): `2603.12056v1.pdf` — Skill+Experience 双流、跨路径对比、层次化合并、检索后适配

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
