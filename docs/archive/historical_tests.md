## 🧠 Lessons Learned: LLM Integration vs. Offline Unit Testing

**Why were tests like A1 (Skill Matching), A4 (Config Behavior), and A17 (Knowledge Graph) not tested in the standard `pytest` suite?**
1. **Determinism & Speed**: The core `pytest` suite (1000+ tests) is designed to run completely offline without actual API key mounting, ensuring zero cost, fast CI/CD execution, and elimination of network-based flakiness.
2. **LLM Dependency Context**: Features like A1, A4, and A17 natively require the LLM to actively parse prompts, reflect configurations, or extract exact factual triplets. Mocking the LLM for these tests defeats the purpose of verifying actual prompt-understanding behavior.
3. **New Methodology**: To bridge this gap, we introduced `test_llm_evals.py`—a dedicated, online integration script designed to be run manually against the production `ProviderFactory` configuration (`config.json`), validating true end-to-end model cognition without polluting the offline unit tests.
4. **Long-Running Stability (A18/F1-F8)**: Features involving continuous stream delivery and multi-hour stability cannot be safely wrapped in a sandbox script. These are marked "Deferred" and must be verified in live dashboard usage over extended sessions.

---

## 🧠 Lessons Learned: Client/Server Architecture (2026-03-25)

**Context**: Previously, the `dashboard` and `agent` CLI commands instantiated their own isolated `AgentLoop`, `MessageBus`, and `SessionManager` instances. This caused severe isolation issues: messages from the Web UI couldn't be seen in the CLI, and multiple processes fighting over ChromaDB or `sessions.json` caused file locking constraints and resource bloat (loading multiple LLM/VLM connections in memory).

**Architectural Pivot (Phase 28D)**: We migrated Nanobot to a strict **Client/Server** model:
1. **Gateway is the Single Source of Truth**: The `nanobot gateway` command now hosts the *only* `AgentLoop` and the Web UI (`uvicorn` server). 
2. **Dumb Clients**: The `nanobot agent` (CLI) was stripped of its `AgentLoop` and rewritten as a lightweight HTTP/WebSocket client sending messages to the `gateway`'s `/api/cli_chat` endpoint.
3. **True Lightweight**: This entirely eliminated process duplication. Memory footprint is halved, file-locking concurrency issues are structurally avoided, and the agent possesses single unified memory and context regardless of which channel the user interacts from.

**Takeaway (A29 Plugin Lifecycle)**: The split between synchronous initialization (`__init__` calling `_register_dynamic_tools` but not `setup()`) and asynchronous reloading (`/reload` calling `await _reload_dynamic_tools` which includes `setup()`) must be strictly maintained. Attempting to make the initialization path `async` leads to un-awaited coroutines and silent plugin dropping at startup.

---

## 🧠 Lessons Learned: Feature Discoverability & Operations Manual

**Problem**: Features like `browser(action="login", save_session=true)` are only documented in source code. Users cannot discover these parameters without reading the implementation. The system has 20+ tools, each with multiple action modes and hidden parameters.

**Action**: Created `OPERATIONS.md` — a user-facing operations manual that documents how to use each feature with concrete examples. Every new feature must update this manual as part of Definition of Done.

---


## 1. 测试环境

## ✅ 已完成 & 已测试的功能

### Phase 3: Dynamic Skill Hot-Loading
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Plugin discovery & auto-register | `tests/test_plugin_loader.py` | ✅ 10 pass | ✅ |
| `/reload` hot-reload command | `tests/test_plugin_loader.py` | ✅ | ✅ |
| Error isolation (bad plugin doesn't crash) | `tests/test_plugin_loader.py` | ✅ | ✅ |
| Built-in tool conflict protection | `tests/test_plugin_loader.py` | ✅ | ✅ |
| `onboard.py` skill install from resources | `tests/test_plugin_loader.py` | ✅ | ✅ |

### Phase 7: 轻量化重构
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Router/PreAnalyzer 移除 | `tests/test_loop_integration.py` | ✅ 28 pass | ✅ |
| jieba 分词匹配 | `tests/test_context_knowledge.py` | ✅ | ✅ |
| `/tasks` 命令 | `tests/test_commands.py` | ✅ | ✅ |

### Phase 8: 知识库质量追踪 + 记忆系统
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| success/fail tracking | `tests/test_success_tracking.py` | ✅ 20+ pass | ✅ |
| 隐式反馈 (implicit feedback) | `tests/test_loop_integration.py` | ✅ | ✅ |
| Few-shot prompt injection | `tests/test_loop_integration.py` | ✅ | ✅ |
| Knowledge→Skill 自动升级 | `tests/test_loop_integration.py` | ✅ | ✅ |
| daily memory log | `tests/test_memory_daily.py` | ✅ 9 pass | ✅ |
| 每 20 条消息自动 consolidation | `tests/test_loop_integration.py` | ✅ | ✅ |

### Phase 9: 知识持续进化 (Skill Evolution)
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| P0: 版本化 + 自动合并 | `tests/test_knowledge_versioning.py` | ✅ 23 pass | ✅ |
| P1: 静默步骤更新 | `tests/test_knowledge_versioning.py` | ✅ 6 pass | ✅ |
| P2: `/kb` 命令 | `tests/test_knowledge_versioning.py` | ✅ 7 pass | ✅ |
| P3: ChromaDB 语义 fallback | `tests/test_knowledge_versioning.py` | ✅ 4 pass | ✅ |

### Vector Store (RAG)
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| ChromaDB + sentence-transformers | `tests/test_vector_store.py` | ✅ | ✅ |
| 语义搜索 & 去重 | `tests/test_vector_store.py` | ✅ | ✅ |

### Memory Distiller
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| L1 preferences.json 提取 | — | — | ✅ 手动验证 |
| L2 RAG 完整记忆检索 | `tests/test_vector_store.py` | ✅ | ✅ |

### RPA 视觉架构 (3-Layer)
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Layer 1: UIAutomation | `tests/test_rpa_find.py` | ✅ | ✅ |
| Layer 2: PaddleOCR fallback | `tests/test_ocr_engine.py`, `tests/test_ocr_integration.py` | ✅ | ✅ |
| Layer 3: YOLO UI detection | `tests/test_yolo_detector.py` | ✅ 10/11 pass | ✅ |
| 多显示器坐标转换 | `tests/test_consolidate_offset.py` | ✅ | ✅ |
| `ui_name` 文本匹配快速点击 | `tests/test_rpa_find.py` | ✅ | ✅ |

### ComputeBroker 异步计算
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| ProcessPoolExecutor 卸载 | `tests/test_compute_broker.py` | ✅ | ✅ |
| Graceful shutdown | `tests/test_compute_broker.py` | ✅ | ✅ |

### 其他核心组件
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| CLI 输入处理 | `tests/test_cli_input.py` | ✅ | ✅ |
| CLI commands | `tests/test_commands.py` | ✅ | ✅ |
| i18n 多语言 | `tests/test_i18n.py` | ✅ | ✅ |
| Session pending 状态机 | `tests/test_session_pending.py` | ✅ | ✅ |
| Email channel | `tests/test_email_channel.py` | ✅ | ✅ |
| Tool validation | `tests/test_tool_validation.py` | ✅ | ✅ |
| Save prompt conditions | `tests/test_save_prompt_condition.py` | ✅ | ✅ |
| Gemini provider | `tests/test_gemini.py` | ✅ | ✅ |

### 记忆系统增强（mem9 启发）
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Memory CRUD (store/search/delete) | `tests/test_memory_tool.py` | ✅ 33 pass | ✅ |
| 标签过滤 | `tests/test_memory_tool.py` | ✅ | ✅ |
| 记忆意图检测 | `tests/test_memory_tool.py` | ✅ | ✅ |
| 记忆导出/导入 | `tests/test_memory_tool.py` | ✅ | ✅ |
| i18n 消息 | `tests/test_memory_tool.py` | ✅ | ✅ |

### 代码质量与可维护性 (Optimization Phase 10)
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Config Schema 验证 | `tests/test_config_schema.py` | ✅ 15 pass | ✅ |
| SessionManager CRUD | `tests/test_session_manager.py` | ✅ 14 pass | ✅ |
| LiteLLM Provider 解析 | `tests/test_provider_parse.py` | ✅ 12 pass | ✅ |
| 废弃代码清理 (router, etc.) | 全量测试 | ✅ | ✅ |
| 异常处理优化 (bare except) | 全量测试 | ✅ | ✅ |
| `loop.py` 模块化拆分 | 全量测试 | ✅ | ✅ |
| `metrics` 性能指标追踪集成 | 全量测试 | ✅ | ✅ |

### Phase 11: 深度优化
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| P0: 死代码清理 + 常量提取 | `tests/test_loop_cleanup.py` | ✅ 7 pass | ✅ |
| P1: Token 用量追踪 | `tests/test_metrics_tokens.py` | ✅ 10 pass | ✅ |
| P2: LLM 调用重试机制 | `tests/test_provider_retry.py` | ✅ 12 pass | ✅ |

### Phase 13: 检索增强
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| P0: Query Rewriting | `tests/test_retrieval_enhancement.py` | ✅ 2 pass | ✅ |
| P1: 检索后适配 | `tests/test_retrieval_enhancement.py` | ✅ 3 pass | ✅ |

### Phase 12: Knowledge System Upgrade
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Knowledge Management Judge | `tests/test_knowledge_judge.py` | ✅ 2 pass | ✅ |
| Hybrid Retrieval (BM25+Dense) | `tests/test_hybrid_retrieval.py` | ✅ 2 pass | ✅ |
| Experience Bank (SaveExperienceTool) | 综合集成 | ✅ | ✅ |

### Phase 14: Engineering Hygiene
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| `loop.py` 工具注册重构与提取 | `tests/test_loop_integration.py`, `tests/test_plugin_loader.py` | ✅ 41 pass | ✅ |
| 核心模块 Type Hints 类型注解补全 | `tests/test_commands.py` | ✅ 35 pass | ✅ |

### Phase 15: Web Dashboard & Unified Identity
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Unified Master Identity | `tests/test_identity_mapping.py` | ✅ 2 pass | ✅ |
| Auth Rejection (Strict Whitelisting) | `tests/test_auth_rejection.py` | ✅ 1 pass | ✅ |
| Web Dashboard (WS + API) | `dashboard/app.py` | — | ✅ 手动验证 |

### Phase 16: Bug Fixes & Modularization
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| P0: `match_experience()` 变量修复 | `tests/test_experience_bank.py` | ✅ 4 pass | ✅ |
| P0: Query Rewrite 异步修复 | `tests/test_context.py` | ✅ | ✅ |
| P1: Hybrid Retriever 提取 | `tests/test_hybrid_retrieval.py`, `tests/test_experience_bank.py` | ✅ | ✅ |
| P1: Mochat utils 提取 | `tests/test_mochat.py` | ✅ 32 pass | ✅ |
| P1: Embedding model 配置化 | `tests/test_vector_store.py` | ✅ 10 pass | ✅ |
| P1: 中文 prompt i18n | `tests/test_i18n.py` | ✅ | ✅ |

### Phase 17: Root Cleanup & Architecture Enhancement
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| 根目录文件归档 (23 files) | — | — | ✅ |
| `get_metrics()` Dashboard API 修复 | `tests/test_dashboard_api.py` | ✅ 10 pass | ✅ |
| 错误恢复 metrics 计数器 | 全量测试 | ✅ | ✅ |
| Experience Bank 边界测试 | `tests/test_experience_bank.py` | ✅ 9 pass | ✅ |

### Phase 18A: P0 Critical Security Fixes
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| S1: API Key 泄露修复 | — | — | ✅ `git log --all -- .env` 为空 |
| S2+S5: Dashboard Bearer Token 认证 | `tests/test_dashboard_auth.py` | ✅ 13 pass | ✅ |
| S3: Shell 命令拒绝模式加固 | `tests/test_shell_hardening.py` | ✅ 20 pass | ✅ |
| S4: 路径遍历修复 (`is_relative_to`) | `tests/test_dashboard_api.py` | ✅ 10 pass | ✅ |
| S6: Gateway 默认绑定 127.0.0.1 | `tests/test_config_schema.py` | ✅ | ✅ |

### Phase 18B: P1 Medium Security Fixes
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| S7: 空 allowFrom 启动警告 | `tests/test_channel_security.py` | ✅ 3 pass | ✅ |
| S8: master_identities 缓存优化 | `tests/test_channel_security.py`, `tests/test_auth_rejection.py` | ✅ 4 pass | ✅ |
| S9: 错误消息清理（不泄露内部路径） | `tests/test_channel_security.py` | ✅ 2 pass | ✅ |
| S10: SSRF 防护（内网IP阻断） | `tests/test_ssrf_protection.py` | ✅ 12 pass | ✅ |

### Phase 18C: P2 Code Quality & Bug Fixes
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| `/reload` 命令修复 (调用模块函数) | `tests/test_code_quality.py` | ✅ 2 pass | ✅ |
| Memory 意图检测常量提升 | `tests/test_code_quality.py` | ✅ 11 pass | ✅ |
| `__all__` 导出声明 | `tests/test_code_quality.py` | ✅ 3 pass | ✅ |
| Personalization 导入修复 | `tests/test_code_quality.py` | ✅ 1 pass | ✅ |

### Phase 18D: P3 Architecture Improvements
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Channel Manager DRY 注册表重构 | `tests/test_architecture.py` | ✅ 8 pass | ✅ |
| duck-typed Tool Context 分发 | `tests/test_architecture.py` | ✅ 4 pass | ✅ |
| `__all__` 导出声明 (8 模块) | `tests/test_architecture.py` | ✅ 16 pass | ✅ |
| Uptime 指标 (`uptime_seconds()`) | `tests/test_architecture.py` | ✅ 5 pass | ✅ |

### Phase 19+: Performance & Experience Optimization
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| Async 并行工具执行 | `tests/test_phase19_optimizations.py` | ✅ 10 pass | ✅ |
| Context Window 字符预算 | `tests/test_phase19_optimizations.py` | ✅ | ✅ |
| Dashboard v2 响应式 UI | — | — | ✅ 手动验证 |
| Cron 失败通知 | `tests/test_phase19_optimizations.py` | ✅ | ✅ |
| Knowledge Workflow 拆分 | `tests/test_knowledge_workflow.py` | ✅ | ✅ |

### Phase 20: AI Memory Architecture Enhancement
| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------|
| 20A: Evicted Context Buffer | `tests/test_phase19_optimizations.py` | ✅ | ✅ |
| 20B: CLS 慢路径深度合并 | `tests/test_full_workflow.py` | ✅ | ✅ |
| 20C: 时间衰减检索评分 | `tests/test_vector_store.py` | ✅ | ✅ |
| 20D: 元认知反思记忆 | `tests/test_reflection.py` | ✅ | ✅ |
| 20E: 轻量实体关系图 | `tests/test_knowledge_graph.py` | ✅ | ✅ |
| 20F+G+H: Shared Memory / Visual Persistence / PDF | 综合集成 | ✅ | ✅ |

---

## ✅ Phase 21: Post-Audit Hardening (完成)

| 功能 | 阶段 | 状态 | 测试文件 | 自动测试 | 手动确认 |
|------|------|-----|---------|---------|------|
| S1-S2: Shell 安全加固 | 21A | ✅ | `tests/test_phase21a_fixes.py` | ✅ 27 pass | ✅ |
| B1: 并发工具异常处理 | 21A | ✅ | `tests/test_phase21a_fixes.py` | ✅ | ✅ |
| L1-L2: 隐式反馈与状态机修复 | 21A | ✅ | `tests/test_phase21a_fixes.py` | ✅ | ✅ |
| D1: Memory 功能开关 | 21A | ✅ | `tests/test_phase21a_fixes.py` | ✅ | ✅ |
| S3-S4: WS/Memory 输入校验 | 21B | ✅ | `tests/test_phase21b_fixes.py` | ✅ 19 pass | ✅ |
| B2-B4: 异步任务/VLM/Config 修复 | 21B | ✅ | `tests/test_phase21b_fixes.py` | ✅ | ✅ |
| L3-L4: 工作流判断/竞争条件 | 21B | ✅ | `tests/test_phase21b_fixes.py` | ✅ | ✅ |
| D2-D3/C1: 缓存/上下文限制/写冲突 | 21B | ✅ | `tests/test_phase21b_fixes.py` | ✅ | ✅ |
| P2 全部 (S5-E4) | 21C | ✅ | `tests/test_phase21c_fixes.py` | ✅ 21 pass | ✅ |
| I1-E2: 架构/配置改进 | 21D | ✅ | `tests/test_phase21d_fixes.py` | ✅ 21 pass | ✅ |
| F1: Streaming Response Delivery | 21E | ✅ | `tests/test_phase21e_streaming.py` | ✅ 20 pass | ✅ |
| F2: Embedding Model Upgrade + Migration | 21E | ✅ | `tests/test_phase21e_embedding.py` | ✅ 16 pass | ✅ |
| H5-H8: Recurring Bug Remediation | 21G | ✅ | `test_save_prompt_condition.py`, `test_phase21e_embedding.py` | ✅ 7 new | ✅ |

---

## ✅ Phase 22A: Skill Trigger & Discovery Optimization (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| SK1: AI-First Skill 描述重写 (11 个 SKILL.md) | `tests/test_phase22a_skills.py` | ✅ 27 pass | ✅ |
| SK2: Skill 分类 + `build_skills_summary()` XML 输出 | `tests/test_phase22a_skills.py` | ✅ | ✅ |
| SK3: Skill 执行记忆 (`executions.jsonl` FIFO) | `tests/test_phase22a_skills.py` | ✅ | [ ] |
| SaveSkillTool `category` 参数 | `tests/test_phase22a_skills.py` | ✅ | [ ] |

---

## ✅ Phase 22B: Skill Config & Hooks (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| SK4: per-skill `config.json` 配置 | `tests/test_phase22b_skills.py` | ✅ 36 pass | ✅ |
| SK5: pre/post hooks 系统 | `tests/test_phase22b_skills.py` | ✅ | [ ] |
| SK7: Skill Registry 版本追踪 | `tests/test_phase22b_skills.py` | ✅ | [ ] |

---

## ✅ Phase 22D: Event-Driven Architecture + Session Save (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| AE1: Event Bus 领域事件 + Dashboard WS 转发 | `tests/test_phase22d_architecture.py` | ✅ 35 pass | [ ] |
| AE2: Session 追加模式保存优化 | `tests/test_phase22d_architecture.py` | ✅ | [ ] |

---

## ✅ Phase 23A: P0 安全加固 (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| R1: Dashboard POST 1MB body 限制 | `tests/test_phase23a_security.py` | ✅ 14 pass | [ ] |
| R2: hooks.py 沙箱 (路径/大小/危险导入) | `tests/test_phase23a_security.py` | ✅ | [ ] |
| R4: SSRF DNS rebinding 防护 (Transport 层) | `tests/test_phase23a_security.py` | ✅ | [ ] |
| R5: Dashboard token 日志脱敏 | `tests/test_phase23a_security.py` | ✅ | [ ] |

---

## ✅ Phase 23B: P1 数据完整性 & 架构修复 (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| R3: Session/Cron 原子写入 | `tests/test_phase23b_integrity.py` | ✅ 15 pass | [ ] |
| R7: Config 单例使用 | `tests/test_phase23b_integrity.py` | ✅ | [ ] |
| R8: WebSocket 死连接清理 | `tests/test_phase23b_integrity.py` | ✅ | [ ] |
| R10: Key 提取 LRU 缓存 | `tests/test_phase23b_integrity.py` | ✅ | [ ] |
| R13: Session Key 恢复 | `tests/test_phase23b_integrity.py` | ✅ | [ ] |

---

## ✅ Phase 23C: P2 架构优化 & 边缘加固 (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| R11: 图片 20MB 限制 | `tests/test_phase23c_polish.py` | ✅ 7 pass | [ ] |
| R6: VLM 环境变量 override | `tests/test_phase23c_polish.py` | ✅ | [ ] |
| R16: SHA256 视觉哈希去重 | `tests/test_phase23c_polish.py` | ✅ | [ ] |

---

## ✅ Phase 24: Knowledge Graph Evolution — MDER-DR (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| KG1: Triple 描述 (subject/predicate/object) | `tests/test_phase24_knowledge_graph.py` | ✅ 31 pass | ✅ |
| KG2: Entity 消歧 (实体合并/同义) | `tests/test_phase24_knowledge_graph.py` | ✅ | ✅ |
| KG3: Entity-Centric Summaries | `tests/test_phase24_knowledge_graph.py` | ✅ | ✅ |
| KG4: Query Decomposition | `tests/test_knowledge_decomposition.py` | ✅ | ✅ |
| KG5: Semantic Chunking | `tests/test_phase24_knowledge_graph.py` | ✅ | ✅ |

---

## ✅ Phase 26A: Plugin Dependency Management (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| SK7 扩展: pip 依赖自动安装 | `tests/test_phase26a_deps.py` | ✅ 13 pass | [ ] |
| BrowserConfig schema 定义 | `tests/test_phase26a_deps.py` | ✅ | [ ] |

---

## ✅ Phase 26B: Playwright Skill + BrowserTool Plugin (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| BrowserTool 11 actions (navigate/click/fill/type/select/screenshot/content/evaluate/wait/login/close) | `tests/test_phase26b_browser.py` | ✅ 54 pass | [x] ✅ 2026-03-25 Playwright+Chrome 截图 arXiv PDF |
| 双层 SSRF 防护 (导航前 IP 检查 + page.route 拦截) | `tests/test_phase26b_browser.py` | ✅ | [x] ✅ 2026-03-25 修复 L19/L20: scheme filter + 移除 URL 重写 |
| 渐进信任域名 (TrustManager) | `tests/test_phase26b_browser.py` | ✅ | [x] ✅ 2026-03-25 改为 auto-trust 模式 (L22: LLM 无法处理二次确认) |
| Evaluate JS 白名单 | `tests/test_phase26b_browser.py` | ✅ | [ ] |

---

## ✅ Phase 26C: Session 加密持久化 + TrustManager (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| Phase 26C: Session 加密持久化 | `tests/test_phase26c_sessions.py` | ✅ 28 pass | [x] ✅ 2026-03-25 test_session_persist_manual.py 验证网站 DPAPI 加密与恢复 |
| BrowserSessionStore TTL + 域名隔离 | `tests/test_phase26c_sessions.py` | ✅ | [ ] |
| TrustManager 独立模块 (add/remove/clear/persist) | `tests/test_phase26c_sessions.py` | ✅ | [ ] |

---

## ✅ Phase 27: Security & Stability Hardening (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| SSRF TOCTOU 修复 (DNS pinning) | `tests/test_phase27_skills_ast.py` | ✅ | [ ] |
| AST Sandbox (替换 string-matching hooks 检测) | `tests/test_phase27_skills_ast.py` | ✅ | [ ] |
| Windows Atomic Write `safe_replace` 重试 | `tests/test_phase27_skills_ast.py` | ✅ | [ ] |

---

## ✅ Phase 28A: OpenClaw — Provider Abstraction & Plugin Lifecycle (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| ProviderFactory 抽象 (VLM 动态路由) | `tests/test_provider_factory.py` | ✅ | [x] ✅ 2026-03-25 volcengine/doubao VLM 路由正确，Activity Log 显示正确模型切换 |
| Plugin Lifecycle hooks (setup/teardown) | `tests/test_plugin_lifecycle.py` | ✅ 5 pass | [x] ✅ 2026-03-25 /reload teardown→setup 序列正确，lifecycle_log.txt 确认 |

---

## ✅ Phase 28B: OpenClaw — Execution Layer Sandboxing (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| Python Sandbox (sys.addaudithook + 进程隔离) | `tests/test_phase28b_sandbox.py` | ✅ 5 pass | [ ] |
| Shell Sandbox (stripped env, 无敏感 key) | `tests/test_phase28b_sandbox.py` | ✅ | [ ] |

---

## ✅ Phase 28C: OpenClaw — Memory Architecture (Vector DB → KG) (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| Vector DB 与 Knowledge Graph 集成 (语义检索) | `tests/test_phase28c_knowledge_graph.py` | ✅ 3 pass | [ ] |
| Entity Summary → ChromaDB 注入 | `tests/test_phase28c_knowledge_graph.py` | ✅ | [ ] |

## ✅ Step 8: Channel Offline Verification (C2-C10) (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| C2 MoChat: utils/dedup/target 解析 | `tests/test_channels_offline.py` | ✅ 18 pass | [x] ✅ 2026-03-25 |
| C3 Telegram: HTML 转换/消息分割/sender | `tests/test_channels_offline.py` | ✅ 13 pass | [x] ✅ 2026-03-25 |
| C4 Discord: gateway/rate-limit/payload | `tests/test_channels_offline.py` | ✅ 4 pass | [x] ✅ 2026-03-25 |
| C5 Slack: policy/mrkdwn/table 转换 | `tests/test_channels_offline.py` | ✅ 9 pass | [x] ✅ 2026-03-25 |
| C6 Email: IMAP/SMTP 全流程 | `tests/test_email_channel.py` | ✅ 5 pass | [x] ✅ 已验证 |
| C7 Feishu: post/card/table/headings | `tests/test_channels_offline.py` | ✅ 8 pass | [x] ✅ 2026-03-25 |
| C8 DingTalk: handler/token/lifecycle | `tests/test_channels_offline.py` | ✅ 4 pass | [x] ✅ 2026-03-25 |
| C9 WhatsApp: bridge 消息/status/voice | `tests/test_channels_offline.py` | ✅ 8 pass | [x] ✅ 2026-03-25 |
| C10 QQ: dedup/lifecycle | `tests/test_channels_offline.py` | ✅ 4 pass | [x] ✅ 2026-03-25 |
| ChannelManager 注册表 + Schema | `tests/test_channels_offline.py` | ✅ 4 pass | [x] ✅ 2026-03-25 |

---

## ✅ Phase 30: 弱模型防护 (Weak Model Safety Guards) (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| 混合模型 Tool Calling 防护架构 | `tests/test_phase30_high.py`, `tests/test_phase30_remaining.py` | ✅ 20 pass | [ ] |
| Medium 缺陷修复 | `tests/test_code_quality.py`, etc. | ✅ 8 pass | [ ] |

---
