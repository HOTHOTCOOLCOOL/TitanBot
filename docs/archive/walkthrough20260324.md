# Step 3 & Step 4 完成报告

## Step 3: 根目录清理 ✅

删除 **30 个临时文件**，根目录从 52 → 22 文件：

| 类别 | 文件 | 数量 |
|------|------|------|
| 错误日志 | [err.txt](file:///d:/Python/nanobot/err.txt) ~ [err5.txt](file:///d:/Python/nanobot/err5.txt), [errs.log](file:///d:/Python/nanobot/errs.log), [errs_utf8.log](file:///d:/Python/nanobot/errs_utf8.log) | 7 |
| 测试输出 | [test_all.txt](file:///d:/Python/nanobot/test_all.txt), [test_error.txt](file:///d:/Python/nanobot/test_error.txt), [test_out.txt](file:///d:/Python/nanobot/test_out.txt), [test_output.txt](file:///d:/Python/nanobot/test_output.txt), [test_stdout.txt](file:///d:/Python/nanobot/test_stdout.txt), [pytest_out.txt](file:///d:/Python/nanobot/pytest_out.txt), [fail.txt](file:///d:/Python/nanobot/fail.txt), [fail2.txt](file:///d:/Python/nanobot/fail2.txt) | 8 |
| 回归输出 | [regress.txt](file:///d:/Python/nanobot/regress.txt), [regression_report.txt](file:///d:/Python/nanobot/regression_report.txt) | 2 |
| 临时脚本 | [tmp_extract.py](file:///d:/Python/nanobot/tmp_extract.py) ~ [tmp_extract5.py](file:///d:/Python/nanobot/tmp_extract5.py), [tmp_parse_mhtml.py](file:///d:/Python/nanobot/tmp_parse_mhtml.py), [run_test.py](file:///d:/Python/nanobot/run_test.py), [test_browser_dns.py](file:///d:/Python/nanobot/test_browser_dns.py) | 8 |
| 其他 | [clean_log.txt](file:///d:/Python/nanobot/clean_log.txt), [debug_pytest.txt](file:///d:/Python/nanobot/debug_pytest.txt), [openclaw_output.txt](file:///d:/Python/nanobot/openclaw_output.txt), [openclaw_raw.html](file:///d:/Python/nanobot/openclaw_raw.html), `Skill trq212.md` | 5 |

[.gitignore](file:///d:/Python/nanobot/.gitignore) 新增 11 个 glob 模式防止再次积累。[.env](file:///d:/Python/nanobot/.env) **保留**（仍作本地 override 用，已在 [.gitignore](file:///d:/Python/nanobot/.gitignore)）。

---

## Step 4: TEST_TRACKER 补全 ✅

### TEST_TRACKER.md

```diff:TEST_TRACKER.md
# Nanobot 功能测试追踪表 (Test Tracker)

> 每个新功能必须经过 ✅ **自动化测试通过** + ✅ **手动确认** 才算正式完成。
> 最后更新: 2026-03-19

---

## 测试环境

```bash
# 标准测试命令（使用 .venv311 / Python 3.11）
cd d:\Python\nanobot
$env:NO_PROXY="*"; $env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
.venv311\Scripts\python.exe -m pytest tests/ --ignore=tests/skill --ignore=tests/test_gemini.py -q
```

> [!IMPORTANT]
> `.venv` (Python 3.14) 已废弃，所有测试和开发使用 `.venv311` (Python 3.11)，因 `chromadb` 不兼容 3.14。

---

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

## ⚠️ 已知问题

| 问题 | 影响 | 状态 |
|------|-----|------|
| `chromadb` 不兼容 Python 3.14 | `.venv` 无法运行 chromadb 相关测试 | 已绕过 (使用 `.venv311`) |
| `test_memory_daily.py` 有 2 个间歇性失败 | 不影响功能，环境相关 | 已知，暂不修复 |
| YOLO `test_live_yolo_detection` 需要真实 GPU | CI 环境跳过 | expected |
| `test_gemini.py` ImportError `google.genai` | 需 `--ignore=tests/test_gemini.py` 或安装 `google-genai` | 已知 |

---

## 📋 回归测试基线

**上次全量测试结果:** 924+ passed, 0 failed
**测试日期:** 2026-03-21 (Phase 23A + Config Cleanup 完成后)
**Python 环境:** `.venv311` (Python 3.11)
**下一里程碑:** Phase 23B 数据完整性修复

> [!TIP]
> 每次新功能开发完成后，运行全量回归测试并更新此基线数字。
> 任何 **新增 failure** 都必须在合入前修复。

===
# Nanobot 功能测试追踪表 (Test Tracker)

> 每个新功能必须经过 ✅ **自动化测试通过** + ✅ **手动确认** 才算正式完成。
> 最后更新: 2026-03-24

---

## 测试环境

```bash
# 标准测试命令（使用 .venv311 / Python 3.11）
cd d:\Python\nanobot
$env:NO_PROXY="*"; $env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
.venv311\Scripts\python.exe -m pytest tests/ --ignore=tests/skill --ignore=tests/test_gemini.py -q
```

> [!IMPORTANT]
> `.venv` (Python 3.14) 已废弃，所有测试和开发使用 `.venv311` (Python 3.11)，因 `chromadb` 不兼容 3.14。

---

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
| SK1: AI-First Skill 描述重写 (11 个 SKILL.md) | `tests/test_phase22a_skills.py` | ✅ 27 pass | [ ] |
| SK2: Skill 分类 + `build_skills_summary()` XML 输出 | `tests/test_phase22a_skills.py` | ✅ | [ ] |
| SK3: Skill 执行记忆 (`executions.jsonl` FIFO) | `tests/test_phase22a_skills.py` | ✅ | [ ] |
| SaveSkillTool `category` 参数 | `tests/test_phase22a_skills.py` | ✅ | [ ] |

---

## ✅ Phase 22B: Skill Config & Hooks (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| SK4: per-skill `config.json` 配置 | `tests/test_phase22b_skills.py` | ✅ 36 pass | [ ] |
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
| KG1: Triple 描述 (subject/predicate/object) | `tests/test_phase24_knowledge_graph.py` | ✅ 31 pass | [ ] |
| KG2: Entity 消歧 (实体合并/同义) | `tests/test_phase24_knowledge_graph.py` | ✅ | [ ] |
| KG3: Entity-Centric Summaries | `tests/test_phase24_knowledge_graph.py` | ✅ | [ ] |
| KG4: Query Decomposition | `tests/test_knowledge_decomposition.py` | ✅ | [ ] |
| KG5: Semantic Chunking | `tests/test_phase24_knowledge_graph.py` | ✅ | [ ] |

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
| BrowserTool 11 actions (navigate/click/fill/type/select/screenshot/content/evaluate/wait/login/close) | `tests/test_phase26b_browser.py` | ✅ 54 pass | [ ] |
| 双层 SSRF 防护 (导航前 IP 检查 + page.route 拦截) | `tests/test_phase26b_browser.py` | ✅ | [ ] |
| 渐进信任域名 (TrustManager) | `tests/test_phase26b_browser.py` | ✅ | [ ] |
| Evaluate JS 白名单 | `tests/test_phase26b_browser.py` | ✅ | [ ] |

---

## ✅ Phase 26C: Session 加密持久化 + TrustManager (完成)

| 功能 | 测试文件 | 自动测试 | 手动确认 |
|------|---------|---------|---------| 
| DPAPI/Fernet/Base64 三级加密 | `tests/test_phase26c_sessions.py` | ✅ 28 pass | [ ] |
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
| ProviderFactory 抽象 (VLM 动态路由) | `tests/test_provider_factory.py` | ✅ | [ ] |
| Plugin Lifecycle hooks (setup/teardown) | `tests/test_plugin_lifecycle.py` | ✅ | [ ] |

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

---

## ⚠️ 已知问题

| 问题 | 影响 | 状态 |
|------|-----|------|
| `chromadb` 不兼容 Python 3.14 | `.venv` 无法运行 chromadb 相关测试 | 已绕过 (使用 `.venv311`) |
| `test_memory_daily.py` 有 2 个间歇性失败 | 不影响功能，环境相关 | 已知，暂不修复 |
| YOLO `test_live_yolo_detection` 需要真实 GPU | CI 环境跳过 | expected |
| `test_gemini.py` ImportError `google.genai` | 需 `--ignore=tests/test_gemini.py` 或安装 `google-genai` | 已知 |

---

## 📋 回归测试基线

**上次全量测试结果:** 1097 passed, 0 failed
**测试日期:** 2026-03-24 (Phase 28C + Security Scan 完成后)
**Python 环境:** `.venv311` (Python 3.11)
**下一里程碑:** 手动验证 + Phase 22C

> [!TIP]
> 每次新功能开发完成后，运行全量回归测试并更新此基线数字。
> 任何 **新增 failure** 都必须在合入前修复。

```

- 新增 **14 个 Phase section**（22A/22B/22D/23A/23B/23C/24/26A/26B/26C/27/28A/28B/28C）
- 回归基线：924 → **1097 passed**
- 下一里程碑更新为「手动验证 + Phase 22C」

### TOOLS.md

```diff:TOOLS.md
# Nanobot Tool Design Audit (Phase 22B — SK6)

> Systematic review of all tool I/O formats for model-friendliness.
> Last updated: 2026-03-20

## Audit Criteria

| Dimension | Description |
|-----------|-------------|
| **Error Prefix** | Returns `"Error: ..."` on failure (per L4 lesson) |
| **Output Format** | Structured, parseable output (JSON preferred) |
| **Output Cap** | Global 50K char cap via `ToolRegistry` (I3) |
| **Smart Defaults** | Minimal required params, intelligent defaults |
| **Description** | Clear, model-optimized tool description |
| **Idempotency** | Safe to retry on failure |

## Global Safeguards

- **Output Truncation**: `ToolRegistry.execute()` enforces `MAX_TOOL_OUTPUT = 50,000` chars with `[OUTPUT TRUNCATED]` marker — applies to ALL tools automatically.
- **Error Detection**: Agent loop checks `_FAIL_INDICATORS` against tool output to detect failures.
- **Param Validation**: `Tool.validate_params()` validates against JSON Schema before execution.

---

## Tool Audit Results

### 1. ExecTool (`shell.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Returns stderr with clear error context |
| Output Format | ✅ | Raw stdout/stderr — appropriate for shell |
| Smart Defaults | ✅ | `timeout` defaults to 30s |
| Description | ✅ | Clear usage guidance |
| Security | ✅ | 14 deny patterns, workspace restriction |

---

### 2. OutlookTool (`outlook.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Consistent `"Error: ..."` across all 7 actions |
| Output Format | ✅ | Structured JSON for find_emails/read_email |
| Smart Defaults | ✅ | `max_results=10`, `folder="inbox"` defaults |
| Description | ✅ | Unified `action` parameter design |
| Idempotency | ⚠️ | `send_email` is not idempotent (expected) |

**Strength**: Single tool with `action` parameter reduces model decision load — exemplary design.

---

### 3. AttachmentAnalyzerTool (`attachment_analyzer.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: ..."` for missing files, missing libs |
| Output Format | ✅ | Structured text extraction |
| Smart Defaults | ✅ | Auto-detects file type |
| Description | ✅ | Clear supported formats listed |

**Note**: Provides helpful `pip install` instructions when optional deps missing.

---

### 4. WebSearchTool / WebFetchTool (`web.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: ..."` for SSRF, fetch failures |
| Output Format | ✅ | Clean text extraction from HTML |
| Smart Defaults | ✅ | PDF support auto-detected |
| Security | ✅ | RFC1918/SSRF protection |

---

### 5. MemorySearchTool (`memory_search_tool.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: query parameter is required."` |
| Output Format | ✅ | Structured search results with scores |
| Smart Defaults | ✅ | `action` param with sensible defaults |
| Description | ✅ | Multi-action design (store/search/delete) |

---

### 6. Filesystem Tools (`filesystem.py`) ✅

4 tools: `ReadFileTool`, `WriteFileTool`, `EditFileTool`, `ListDirTool`

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: File not found"`, `"Error: Not a directory"` |
| Output Format | ✅ | Clear text output, dir listing with metadata |
| Smart Defaults | ✅ | EditFileTool uses exact-match replacement |
| Description | ✅ | Focused, single-purpose tools |

**Strength**: Separate tools for read/write/edit/list — avoids ambiguity.

---

### 7. CronTool (`cron.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: message is required"` etc. |
| Output Format | ✅ | Structured JSON for list, clear confirmations |
| Smart Defaults | ✅ | Natural language scheduling |
| Description | ✅ | Clear action-based design (add/list/remove) |

---

### 8. MessageTool (`message.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: No target channel"` |
| Output Format | ✅ | Simple success/error confirmation |
| Smart Defaults | ✅ | Auto-uses current channel context |

**Note**: Terminal action — must NOT be in `_CONTINUE_TOOLS` (L1 lesson).

---

### 9. ScreenCaptureTool (`screen_capture.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling with context |
| Output Format | ✅ | File path + Set-of-Marks annotations |
| Smart Defaults | ✅ | Auto multi-monitor handling |

---

### 10. RPAExecutorTool (`rpa_executor.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error context for UIA failures |
| Output Format | ✅ | Action result with element details |
| Smart Defaults | ✅ | VLM feedback loop integration (F3) |
| Description | ✅ | Rich action set with clear params |

---

### 11. SaveSkillTool (`save_skill.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Schema validation before execution |
| Output Format | ✅ | Clear success message with file path |
| Smart Defaults | ✅ | Optional params with sensible defaults |
| **Phase 22B** | ✅ | Added `version`, `config`, `pip_dependencies` |

---

### 12. SaveExperienceTool (`save_experience.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Via schema validation |
| Output Format | ✅ | Confirmation message |
| Smart Defaults | ✅ | Minimal required fields |

---

### 13. TaskMemoryTool (`task_memory.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Structured task state output |
| Smart Defaults | ✅ | Action-based design |

---

### 14. SpawnTool (`spawn.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Returns sub-agent result |
| Smart Defaults | ✅ | Minimal params (task only) |

---

### 15. MCP Tool (`mcp.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Passes through MCP server response |
| Smart Defaults | ✅ | Auto-connects to configured server |

---

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Compliant | 18/18 | **100%** |
| ⚠️ Minor notes | 1 | `send_email` non-idempotent (by design) |
| ❌ Non-compliant | 0 | — |

### Key Findings

1. **Error prefix consistency**: All 18 tools use `"Error: ..."` prefix ✅
2. **Output truncation**: Handled globally by `ToolRegistry` (50K char cap) ✅
3. **Smart defaults**: All tools have sensible defaults reducing model decision load ✅
4. **Unified action pattern**: `OutlookTool`, `CronTool`, `MemorySearchTool` use action-based design reducing tool count ✅
5. **Param validation**: `Tool.validate_params()` provides schema-level validation ✅

### Design Principles Confirmed

- **Fewer, more powerful tools** over many specialized ones (Lesson 7)
- **Consistent error format** so models reliably detect failures (L4)
- **Smart defaults** that reduce the number of required params
- **Structured output** that models can parse and act on
===
# Nanobot Tool Design Audit (Phase 22B — SK6)

> Systematic review of all tool I/O formats for model-friendliness.
> Last updated: 2026-03-24

## Audit Criteria

| Dimension | Description |
|-----------|-------------|
| **Error Prefix** | Returns `"Error: ..."` on failure (per L4 lesson) |
| **Output Format** | Structured, parseable output (JSON preferred) |
| **Output Cap** | Global 50K char cap via `ToolRegistry` (I3) |
| **Smart Defaults** | Minimal required params, intelligent defaults |
| **Description** | Clear, model-optimized tool description |
| **Idempotency** | Safe to retry on failure |

## Global Safeguards

- **Output Truncation**: `ToolRegistry.execute()` enforces `MAX_TOOL_OUTPUT = 50,000` chars with `[OUTPUT TRUNCATED]` marker — applies to ALL tools automatically.
- **Error Detection**: Agent loop checks `_FAIL_INDICATORS` against tool output to detect failures.
- **Param Validation**: `Tool.validate_params()` validates against JSON Schema before execution.

---

## Tool Audit Results

### 1. ExecTool (`shell.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Returns stderr with clear error context |
| Output Format | ✅ | Raw stdout/stderr — appropriate for shell |
| Smart Defaults | ✅ | `timeout` defaults to 30s |
| Description | ✅ | Clear usage guidance |
| Security | ✅ | 14 deny patterns, workspace restriction |

---

### 2. OutlookTool (`outlook.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Consistent `"Error: ..."` across all 7 actions |
| Output Format | ✅ | Structured JSON for find_emails/read_email |
| Smart Defaults | ✅ | `max_results=10`, `folder="inbox"` defaults |
| Description | ✅ | Unified `action` parameter design |
| Idempotency | ⚠️ | `send_email` is not idempotent (expected) |

**Strength**: Single tool with `action` parameter reduces model decision load — exemplary design.

---

### 3. AttachmentAnalyzerTool (`attachment_analyzer.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: ..."` for missing files, missing libs |
| Output Format | ✅ | Structured text extraction |
| Smart Defaults | ✅ | Auto-detects file type |
| Description | ✅ | Clear supported formats listed |

**Note**: Provides helpful `pip install` instructions when optional deps missing.

---

### 4. WebSearchTool / WebFetchTool (`web.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: ..."` for SSRF, fetch failures |
| Output Format | ✅ | Clean text extraction from HTML |
| Smart Defaults | ✅ | PDF support auto-detected |
| Security | ✅ | RFC1918/SSRF protection |

---

### 5. MemorySearchTool (`memory_search_tool.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: query parameter is required."` |
| Output Format | ✅ | Structured search results with scores |
| Smart Defaults | ✅ | `action` param with sensible defaults |
| Description | ✅ | Multi-action design (store/search/delete) |

---

### 6. Filesystem Tools (`filesystem.py`) ✅

4 tools: `ReadFileTool`, `WriteFileTool`, `EditFileTool`, `ListDirTool`

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: File not found"`, `"Error: Not a directory"` |
| Output Format | ✅ | Clear text output, dir listing with metadata |
| Smart Defaults | ✅ | EditFileTool uses exact-match replacement |
| Description | ✅ | Focused, single-purpose tools |

**Strength**: Separate tools for read/write/edit/list — avoids ambiguity.

---

### 7. CronTool (`cron.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: message is required"` etc. |
| Output Format | ✅ | Structured JSON for list, clear confirmations |
| Smart Defaults | ✅ | Natural language scheduling |
| Description | ✅ | Clear action-based design (add/list/remove) |

---

### 8. MessageTool (`message.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: No target channel"` |
| Output Format | ✅ | Simple success/error confirmation |
| Smart Defaults | ✅ | Auto-uses current channel context |

**Note**: Terminal action — must NOT be in `_CONTINUE_TOOLS` (L1 lesson).

---

### 9. ScreenCaptureTool (`screen_capture.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling with context |
| Output Format | ✅ | File path + Set-of-Marks annotations |
| Smart Defaults | ✅ | Auto multi-monitor handling |

---

### 10. RPAExecutorTool (`rpa_executor.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error context for UIA failures |
| Output Format | ✅ | Action result with element details |
| Smart Defaults | ✅ | VLM feedback loop integration (F3) |
| Description | ✅ | Rich action set with clear params |

---

### 11. SaveSkillTool (`save_skill.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Schema validation before execution |
| Output Format | ✅ | Clear success message with file path |
| Smart Defaults | ✅ | Optional params with sensible defaults |
| **Phase 22B** | ✅ | Added `version`, `config`, `pip_dependencies` |

---

### 12. SaveExperienceTool (`save_experience.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Via schema validation |
| Output Format | ✅ | Confirmation message |
| Smart Defaults | ✅ | Minimal required fields |

---

### 13. TaskMemoryTool (`task_memory.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Structured task state output |
| Smart Defaults | ✅ | Action-based design |

---

### 14. SpawnTool (`spawn.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Returns sub-agent result |
| Smart Defaults | ✅ | Minimal params (task only) |

---

### 15. MCP Tool (`mcp.py`) ✅

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | Error handling present |
| Output Format | ✅ | Passes through MCP server response |
| Smart Defaults | ✅ | Auto-connects to configured server |

---

### 16. BrowserTool (`plugins/browser.py`) ✅

> Plugin tool — auto-discovered by `plugin_loader.py` from `nanobot/plugins/`. Phase 26B+C.

| Dimension | Status | Notes |
|-----------|--------|-------|
| Error Prefix | ✅ | `"Error: ..."` for missing playwright, SSRF, untrusted domains |
| Output Format | ✅ | Structured JSON for all 11 actions |
| Smart Defaults | ✅ | `timeout_ms` defaults to 30s, viewport 1920×1080 |
| Description | ✅ | Clear action-based design with 11 actions |
| Security | ✅ | Dual-layer SSRF (DNS + route), progressive trust, JS evaluate whitelist, encrypted sessions (DPAPI/Fernet) |
| Idempotency | ⚠️ | `click`, `fill`, `type` are not idempotent (expected) |

**Actions**: `navigate`, `click`, `fill`, `type`, `select`, `screenshot`, `content`, `evaluate`, `wait`, `login`, `close`

**Strength**: Graceful degradation — if Playwright not installed, returns helpful install instructions. Zero startup cost.

---

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Compliant | 19/19 | **100%** |
| ⚠️ Minor notes | 2 | `send_email` non-idempotent (by design); `click`/`fill`/`type` non-idempotent (expected) |
| ❌ Non-compliant | 0 | — |

### Key Findings

1. **Error prefix consistency**: All 19 tools use `"Error: ..."` prefix ✅
2. **Output truncation**: Handled globally by `ToolRegistry` (50K char cap) ✅
3. **Smart defaults**: All tools have sensible defaults reducing model decision load ✅
4. **Unified action pattern**: `OutlookTool`, `CronTool`, `MemorySearchTool` use action-based design reducing tool count ✅
5. **Param validation**: `Tool.validate_params()` provides schema-level validation ✅

### Design Principles Confirmed

- **Fewer, more powerful tools** over many specialized ones (Lesson 7)
- **Consistent error format** so models reliably detect failures (L4)
- **Smart defaults** that reduce the number of required params
- **Structured output** that models can parse and act on
```

- 新增 **#16 BrowserTool** ([plugins/browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)) 审计条目
- Summary 计数 18/18 → **19/19**

### progress_report.md

```diff:progress_report.md
# Nanobot 项目进度总览

> 截至 2026-03-23 （长期维护文档）

---

## 🏁 当前位置：Phase 28C ✅（OpenClaw Memory Architecture 完成）

已完成 **18+ 个大阶段**，从 10 文件聊天机器人发展到 95+ 文件、14 子包、19 工具、9 通道的企业级 AI Agent。回归测试：**1097 passed**。

---

## ✅ 已完成阶段

| 阶段 | 核心内容 | 测试 |
|------|---------|------|
| Phase 7 | 轻量化重构 | ✅ |
| Phase 8 | 知识追踪 + 记忆系统 | ✅ |
| Phase 9 | 知识进化 (版本化/合并/KB命令) | ✅ |
| Phase 11 | 深度优化 (死代码/Token追踪/LLM重试) | ✅ |
| Phase 12 | Knowledge System Upgrade (AutoSkill/XSKILL) | ✅ |
| Phase 13-14 | 检索增强 + 工程清理 | ✅ |
| Phase 15 | Web Dashboard + Master Identity | ✅ |
| Phase 16-17 | Bug Fixes + Root Cleanup | ✅ |
| Phase 18A-D | 安全审计 (32 项全修复) | ✅ 529→599 |
| Phase 19/19+ | 性能优化 + Knowledge 拆分 | ✅ 602 |
| Phase 20A-H | AI Memory 7 层架构 | ✅ |
| Phase 21A-E | 审计修复 + Streaming + Embedding升级 | ✅ 793 |
| Phase 21F-H | 生产热修复 (3 轮) | ✅ |
| Phase 22A | Skill 触发 & 发现优化 (SK1-SK3) | ✅ 811 |
| Phase 22B | Skill 配置 & Hooks (SK4-SK7) | ✅ 847 |
| Phase 22D | Event-Driven Architecture + Session Save 优化 | ✅ 847 |
| Phase 23A | P0 安全加固 (Dashboard/SSRF/Hooks/Token) | ✅ 924+ |
| Config Cleanup | 移除 `.env` 冗余层，`config.json` 为唯一配置源 | ✅ |
| Phase 23B | P1 数据完整性 & 架构修复 (R3/R7/R8/R9/R10/R13) | ✅ 948 |
| Phase 23C | P2 架构优化 & 边缘加固 (R6/R11/R12/R14/R16) | ✅ 948 |
| Phase 24 | Knowledge Graph Evolution — MDER-DR (KG1-KG5) | ✅ 979 |
| **Phase 25** | **项目回头看 & 加固 (F1-F8)** | **✅ 979** |
| **Phase 26A** | **Plugin Dependency Management — SK7 pip 依赖 + BrowserConfig** | **✅ 992** |
| **Phase 26B** | **Playwright Skill + BrowserTool Plugin — 11 action + 双层 SSRF + 渐进信任** | **✅ 1046** |
| **Phase 26C** | **Session 加密持久化 (DPAPI/Fernet) + TrustManager 独立模块** | **✅ 1074** |
| **Phase 27** | **Security & Stability Hardening (SSRF TOCTOU/AST Sandbox/Atomic Writes)** | **✅** |
| **Phase 28A** | **OpenClaw Optimization: Provider Abstraction & Plugin Lifecycle hooks** | **✅ 1088** |
| **Phase 28B** | **OpenClaw Optimization: Execution Layer Sandboxing** | **✅ 1093** |

---

## ⏳ 待做阶段

### Phase 26 — Playwright Browser Automation 🔜 (Next)

> **架构方案**：Skill + Tool Hybrid，按需加载。详见 `implementation_plan.md`。

| 子阶段 | 内容 | 预计工作量 | 状态 |
|--------|------|-----------|------|
| **26A** | Plugin Dependency Management — SK7 扩展 + `BrowserConfig` schema | 半天 | ✅ |
| **26B** | Playwright Skill + `BrowserTool` Plugin — 11 action + 双层 SSRF + 渐进信任 | 1-2天 | ✅ |
| **26C** | Session 加密持久化 + Trust Manager | 1天 | ✅ |

**关键设计决策**（已讨论确认）：
- ✅ Skill 层 (`skills/browser-automation/SKILL.md`) + Plugin Tool 层 (`plugins/browser.py`)
- ✅ 渐进信任域名模型 — 首次导航问一次，永久记住，子请求静默放行
- ✅ Session 持久化 — DPAPI 加密 + TTL + 域名隔离
- ✅ 双层 SSRF — 导航前 IP 检查 + `page.route("**/*")` 请求拦截
- ✅ 与桌面 RPA 互补 — `browser` 管 Web，`rpa` 管桌面应用

### Phase 22C — Multi-Modal & Channel Extension

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Multi-Channel Image Support | P1 | 扩展图片下载到 MoChat, Slack, DingTalk |
| Unified Speech-to-Text | P2 | 统一语音输入管道（目前仅 Telegram） |
| Image Generation Tool | P2 | 集成 DALL-E / Stable Diffusion |

### 长期 Backlog

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Plugin Marketplace | P3 | 可浏览的社区 Skill 仓库（Phase 26 完成后推进） |

---

## 📋 文档过期问题

| 文档 | 问题 | 状态 |
|------|------|------|
| `SECURITY.md` L248-254 | 5 项标记 "pending fix" 但 Phase 21 已全部修复 | **需更新** |
| `ARCHITECTURE_LESSONS.md` L273 | "Phase 22" 说明已过时 | 低优先级 |
| `TEST_TRACKER.md` | 停在 Phase 21G，未覆盖 22A-25；回归基线过期 (924 vs 979) | **需更新** |
| `README.md` | 总体内容仍准确，无需改动 | ✅ |

---

## 🔍 手动验证追踪清单

> **规则**：每项验证通过后标 `[x]`，附日期。一人维护大项目，逐项记录确保无遗漏。

### A. 阶段功能 — 仅有自动测试，缺少生产手动验证

> Phase 22A 至 Phase 25 均有自动化测试通过，但 `TEST_TRACKER.md` 未记录手动确认。

| # | Phase | 功能 | 自动测试 | 手动验证 |
|---|-------|------|---------|---------|
| A1 | 22A | SK1: AI-First Skill 描述重写 (11 个 SKILL.md) | ✅ 27 pass | [ ] 验证 LLM 实际触发匹配 |
| A2 | 22A | SK2: Skill 分类 + `build_skills_summary()` XML | ✅ | [ ] 验证 system prompt 中分类显示 |
| A3 | 22A | SK3: Skill 执行记忆 (`executions.jsonl`) | ✅ | [ ] 执行 skill → 检查 jsonl 写入 |
| A4 | 22B | SK4: per-skill `config.json` 配置 | ✅ 36 pass | [ ] 修改 config → 验证行为变化 |
| A5 | 22B | SK5: pre/post hooks 系统 | ✅ | [ ] 放 hooks.py → 验证触发 |
| A6 | 22B | SK7: Skill Registry 版本追踪 | ✅ | [ ] 查看 `skills_registry.json` 内容正确 |
| A7 | 22D | AE1: Event Bus 领域事件 + Dashboard WS 转发 | ✅ 35 pass | [ ] Dashboard WS 实时接收事件 |
| A8 | 22D | AE2: Session 追加模式保存优化 | ✅ | [ ] 多轮对话 → 检查 JSONL 追加 |
| A9 | 23A | R1: Dashboard POST 1MB body 限制 | ✅ 14 pass | [ ] curl 大 body → 验证 413 |
| A10 | 23A | R2: hooks.py 沙箱 (路径/大小/危险导入) | ✅ | [ ] 放恶意 hooks → 验证拒绝 |
| A11 | 23A | R4: SSRF DNS rebinding 防护 (Transport 层) | ✅ | [ ] `web_fetch http://127.0.0.1` → 验证阻断 |
| A12 | 23A | R5: Dashboard token 日志脱敏 | ✅ | [ ] 启动后查日志 token 已 mask |
| A13 | 23B | R3: Session 原子写入 | ✅ 15 pass | [ ] 对话中断电 → Session 不损坏 |
| A14 | 23B | R10: Key 提取 LRU 缓存 | ✅ | [ ] 重复查询 → 检查缓存命中 |
| A15 | 23C | R11: 图片 20MB 限制 | ✅ 7 pass | [ ] 发大图 → 验证跳过不崩溃 |
| A16 | 23C | R16: SHA256 视觉哈希去重 | ✅ | [ ] 重复截图 → 验证去重 |
| A17 | 24 | KG1-KG5: 知识图谱演进 (5 项) | ✅ 31 pass | [ ] 多轮对话 → 检查实体/三元组 |
| A18 | 25 | F1-F8: 回头看加固 (7项修复) | ✅ 979 pass | [ ] 长时间运行稳定性 |
| A19 | 28C| OpenClaw Memory Architecture (Vector DB) | ✅ 3 pass | [ ] 多轮对话 → 检查 KG Semantic 检索 |
| A20 | 26B | BrowserTool 11 actions (navigate/click/fill/screenshot 等) | ✅ 54 pass | [ ] 真实浏览器 → 打开网页并截图 |
| A21 | 26B | 双层 SSRF 防护 (导航前 IP 检查 + route 拦截) | ✅ | [ ] 尝试导航到 `http://169.254.x.x` → 阻断 |
| A22 | 26B | 渐进信任域名 (首次确认后永久记住) | ✅ | [ ] 首次访问域名 → 确认提示 → 二次跳过 |
| A23 | 26C | Session DPAPI/Fernet 加密持久化 | ✅ 28 pass | [ ] 登录网站 → 关闭→重启 → Session 恢复 |
| A24 | 26C | TrustManager 独立化 + clear/remove | ✅ | [ ] `trusted_domains.json` 手动编辑确认 |
| A25 | 27 | SSRF TOCTOU 修复 (DNS pinning) | ✅ | [ ] 高并发 web_fetch → 无竞态 |
| A26 | 27 | AST Sandbox (替换 string-matching) | ✅ | [ ] 写 `__import__('os')` 的 hooks → 验证 AST 阻断 |
| A27 | 27 | Windows Atomic Write `safe_replace` 重试 | ✅ | [ ] Windows Defender 场景下快速写入 → 无崩溃 |
| A28 | 28A | ProviderFactory 抽象 (VLM 动态路由) | ✅ | [ ] 切换 VLM provider → 验证正确路由 |
| A29 | 28A | Plugin Lifecycle (setup/teardown hooks) | ✅ | [ ] 手动 `/reload` → 确认 teardown→setup 序列 |
| A30 | 28B | Python Sandbox (sys.addaudithook) | ✅ 5 pass | [ ] 写恶意 Python 脚本 → 验证 audit hook 阻断 |
| A31 | 28B | Shell Sandbox (stripped env) | ✅ | [ ] 检查 shell 进程环境变量 → 无敏感 key |

### B. 核心功能 — 需要生产环境验证

| # | 功能 | 描述 | 手动验证 |
|---|------|------|---------|
| B1 | Streaming 响应 | F1: `/ws/stream` 流式 token 推送 | [ ] Dashboard 实时看到逐字输出 |
| B2 | VLM Feedback Loop | F3: RPA 执行后 VLM 截图验证 | [ ] `verify=true` → VLM 比对结果 |
| B3 | Embedding 迁移 | bge-m3 1024-dim 自动迁移 | [ ] 旧 ChromaDB → 自动重建无报错 |
| B4 | Cron 跨日守护 | L15: 重启后不补跑昨天的任务 | [ ] 次日重启 → 昨日任务标 skipped |
| B5 | Outlook 外部地址 | L14: COM PropertyAccessor 发送外部邮件 | [ ] 发送到 @gmail.com → 成功 |
| B6 | 重复工具调用检测 | L16: 连续相同 tool call → 自动终止 | [ ] 触发场景 → 验证中断 |
| B7 | 深度记忆整合 | 20B CLS 慢路径 → KG 自动 re-summary | [ ] 20+ 消息 → 整合触发 |

### C. 通道生产就绪状态

| # | 通道 | 代码存在 | 生产验证 |
|---|------|---------|---------|
| C1 | CLI | ✅ | [x] 日常使用 |
| C2 | MoChat (企业微信) | ✅ | [ ] 消息收发 + 附件 |
| C3 | Telegram | ✅ | [ ] 消息 + 语音 STT |
| C4 | Discord | ✅ | [ ] WebSocket 长连 + 消息 |
| C5 | Slack | ✅ | [ ] Socket Mode + Thread 回复 |
| C6 | Email (IMAP/SMTP) | ✅ | [ ] 收信 → 自动回复 |
| C7 | 飞书 (Feishu) | ✅ | [ ] 消息 + 图片下载 |
| C8 | 钉钉 (DingTalk) | ✅ | [ ] Stream Mode 消息 |
| C9 | WhatsApp | ✅ | [ ] Bridge WS + 消息收发 |
| C10 | QQ | ✅ | [ ] botpy SDK 消息 |

### D. 安全与文档维护

| # | 项目 | 描述 | 状态 |
|---|------|------|------|
| D1 | `SECURITY.md` 更新 | L248-254 的 5 个 "pending fix" 标注需更新为已修复 | [ ] |
| D2 | `TEST_TRACKER.md` 补全 | 添加 Phase 22A ~ **Phase 28C** 的测试记录 | [ ] |
| D3 | `TEST_TRACKER.md` 基线 | 回归基线从 924 更新为 **1097** | [ ] |
| D4 | `ARCHITECTURE_LESSONS.md` | L273 "Phase 22" 说明过时 | [ ] 低优先级 |
| D5 | `config.sample.json` | **缺少** BrowserConfig / StreamingConfig / MemoryFeaturesConfig 等 | [ ] |
| D6 | `TOOLS.md` | 缺少 BrowserTool (第 19 个工具)，需更新为 19/19 | [ ] |
| D7 | `pip-audit` 安全扫描 | `pip-audit` 发现 7 CVE / 6 包，已在 .venv311 升级修复；`npm audit` 跳过（WhatsApp Bridge 低优先级） | [x] ✅ 2026-03-24 |
| D8 | `PROJECT_STATUS.md` 去重 | L343-403 重复了 Phase 21D-21H 的内容 | [ ] |
| D9 | 根目录临时文件清理 | 20+ stale 文件 (err*.txt, test_*.txt, tmp_*.py) 应清理 | [ ] |
| D10 | `EVOLUTION.md` 数据更新 | 数据汇总区仍写 811 测试用例，实际 1097+ | [ ] |

---

## 📝 每次 Phase 完成后必须更新的 5 个文档

1. ✅ `EVOLUTION.md` — 演进时间线 + Phase 条目
2. ✅ `LESSONS_LEARNED.md` — 本轮教训
3. ✅ `PROJECT_STATUS.md` — 详细进度跟踪
4. ✅ `progress_report.md` — 精简进度总览（本文档）
5. ✅ 测试全部通过

---

## 🚀 执行计划（跨会话逐步完成）

> **2026-03-23 审计后制定**，每完成一步标 `[x]`。

### Step 1：文档修复（消除信息不一致）

- [ ] 1.1 删除 `PROJECT_STATUS.md` L343-403 重复的 Phase 21D-21H 内容 (D8)
- [ ] 1.2 更新 `EVOLUTION.md` 数据汇总区：测试用例 811→1097+，工具数 18→19 (D10)
- [ ] 1.3 补全 `config.sample.json`：添加 `browser`、`streaming`、`memoryFeatures` 等新配置段 (D5)
- [ ] 1.4 更新 `SECURITY.md` L248-254：5 个 "pending fix" 改为已修复 (D1)

### Step 2：安全扫描 ✅ 2026-03-24

- [x] 2.1 执行 `pip-audit` 检查 Python 依赖漏洞 (D7) — 发现 7 CVE（cryptography/pip/pyjwt/pypdf×2/urllib3/wheel），已在 .venv311 升级修复
- [x] 2.2 `npm audit` 跳过 — WhatsApp Bridge 用户极少，未来可能裁剪；`bridge/` 无 lockfile 且 Baileys git+ssh 依赖无法解析

### Step 3：根目录清理

- [ ] 3.1 归档/删除根目录 20+ 临时文件 (`err*.txt`, `test_*.txt`, `tmp_*.py`, `clean_log.txt` 等) (D9)
- [ ] 3.2 确认残留 `.env` 文件是否需要删除（Config Cleanup 阶段已标记 `config.json` 为唯一源）

### Step 4：TEST_TRACKER 补全

- [ ] 4.1 添加 Phase 22A ~ 28C 全部 7 个阶段的测试记录 (D2)
- [ ] 4.2 更新回归基线为 1097 (D3)
- [ ] 4.3 更新 `TOOLS.md` 添加 BrowserTool 审计条目，计数改为 19/19 (D6)

### Step 5：手动测试 — B 类核心功能（优先）

- [ ] B1-B7 逐项执行（需要启动 gateway 进行生产环境验证）

### Step 6：手动测试 — A 类新增 Phase (26-28)

- [ ] A20-A31 逐项执行（Phase 26 需要安装 playwright）

### Step 7：手动测试 — A 类旧 Phase (22-25)

- [ ] A1-A19 逐项执行

### Step 8：手动测试 — C 类通道

- [ ] C2-C10 逐通道执行（需各通道 API 配置）

### Step 9：后续开发决策

- [ ] 根据测试结果决定进入 Phase 22C（Multi-Modal & Channel Extension）或先修 bug

===
# Nanobot 项目进度总览

> 截至 2026-03-24 （长期维护文档）

---

## 🏁 当前位置：Phase 28C ✅（OpenClaw Memory Architecture 完成）

已完成 **18+ 个大阶段**，从 10 文件聊天机器人发展到 95+ 文件、14 子包、19 工具、9 通道的企业级 AI Agent。回归测试：**1097 passed**。

---

## ✅ 已完成阶段

| 阶段 | 核心内容 | 测试 |
|------|---------|------|
| Phase 7 | 轻量化重构 | ✅ |
| Phase 8 | 知识追踪 + 记忆系统 | ✅ |
| Phase 9 | 知识进化 (版本化/合并/KB命令) | ✅ |
| Phase 11 | 深度优化 (死代码/Token追踪/LLM重试) | ✅ |
| Phase 12 | Knowledge System Upgrade (AutoSkill/XSKILL) | ✅ |
| Phase 13-14 | 检索增强 + 工程清理 | ✅ |
| Phase 15 | Web Dashboard + Master Identity | ✅ |
| Phase 16-17 | Bug Fixes + Root Cleanup | ✅ |
| Phase 18A-D | 安全审计 (32 项全修复) | ✅ 529→599 |
| Phase 19/19+ | 性能优化 + Knowledge 拆分 | ✅ 602 |
| Phase 20A-H | AI Memory 7 层架构 | ✅ |
| Phase 21A-E | 审计修复 + Streaming + Embedding升级 | ✅ 793 |
| Phase 21F-H | 生产热修复 (3 轮) | ✅ |
| Phase 22A | Skill 触发 & 发现优化 (SK1-SK3) | ✅ 811 |
| Phase 22B | Skill 配置 & Hooks (SK4-SK7) | ✅ 847 |
| Phase 22D | Event-Driven Architecture + Session Save 优化 | ✅ 847 |
| Phase 23A | P0 安全加固 (Dashboard/SSRF/Hooks/Token) | ✅ 924+ |
| Config Cleanup | 移除 `.env` 冗余层，`config.json` 为唯一配置源 | ✅ |
| Phase 23B | P1 数据完整性 & 架构修复 (R3/R7/R8/R9/R10/R13) | ✅ 948 |
| Phase 23C | P2 架构优化 & 边缘加固 (R6/R11/R12/R14/R16) | ✅ 948 |
| Phase 24 | Knowledge Graph Evolution — MDER-DR (KG1-KG5) | ✅ 979 |
| **Phase 25** | **项目回头看 & 加固 (F1-F8)** | **✅ 979** |
| **Phase 26A** | **Plugin Dependency Management — SK7 pip 依赖 + BrowserConfig** | **✅ 992** |
| **Phase 26B** | **Playwright Skill + BrowserTool Plugin — 11 action + 双层 SSRF + 渐进信任** | **✅ 1046** |
| **Phase 26C** | **Session 加密持久化 (DPAPI/Fernet) + TrustManager 独立模块** | **✅ 1074** |
| **Phase 27** | **Security & Stability Hardening (SSRF TOCTOU/AST Sandbox/Atomic Writes)** | **✅** |
| **Phase 28A** | **OpenClaw Optimization: Provider Abstraction & Plugin Lifecycle hooks** | **✅ 1088** |
| **Phase 28B** | **OpenClaw Optimization: Execution Layer Sandboxing** | **✅ 1093** |

---

## ⏳ 待做阶段

### Phase 26 — Playwright Browser Automation 🔜 (Next)

> **架构方案**：Skill + Tool Hybrid，按需加载。详见 `implementation_plan.md`。

| 子阶段 | 内容 | 预计工作量 | 状态 |
|--------|------|-----------|------|
| **26A** | Plugin Dependency Management — SK7 扩展 + `BrowserConfig` schema | 半天 | ✅ |
| **26B** | Playwright Skill + `BrowserTool` Plugin — 11 action + 双层 SSRF + 渐进信任 | 1-2天 | ✅ |
| **26C** | Session 加密持久化 + Trust Manager | 1天 | ✅ |

**关键设计决策**（已讨论确认）：
- ✅ Skill 层 (`skills/browser-automation/SKILL.md`) + Plugin Tool 层 (`plugins/browser.py`)
- ✅ 渐进信任域名模型 — 首次导航问一次，永久记住，子请求静默放行
- ✅ Session 持久化 — DPAPI 加密 + TTL + 域名隔离
- ✅ 双层 SSRF — 导航前 IP 检查 + `page.route("**/*")` 请求拦截
- ✅ 与桌面 RPA 互补 — `browser` 管 Web，`rpa` 管桌面应用

### Phase 22C — Multi-Modal & Channel Extension

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Multi-Channel Image Support | P1 | 扩展图片下载到 MoChat, Slack, DingTalk |
| Unified Speech-to-Text | P2 | 统一语音输入管道（目前仅 Telegram） |
| Image Generation Tool | P2 | 集成 DALL-E / Stable Diffusion |

### 长期 Backlog

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Plugin Marketplace | P3 | 可浏览的社区 Skill 仓库（Phase 26 完成后推进） |

---

## 📋 文档过期问题

| 文档 | 问题 | 状态 |
|------|------|------|
| `SECURITY.md` L248-254 | 5 项标记 "pending fix" 但 Phase 21 已全部修复 | **需更新** |
| `ARCHITECTURE_LESSONS.md` L273 | "Phase 22" 说明已过时 | 低优先级 |
| `TEST_TRACKER.md` | 停在 Phase 21G，未覆盖 22A-25；回归基线过期 (924 vs 979) | **需更新** |
| `README.md` | 总体内容仍准确，无需改动 | ✅ |

---

## 🔍 手动验证追踪清单

> **规则**：每项验证通过后标 `[x]`，附日期。一人维护大项目，逐项记录确保无遗漏。

### A. 阶段功能 — 仅有自动测试，缺少生产手动验证

> Phase 22A 至 Phase 25 均有自动化测试通过，但 `TEST_TRACKER.md` 未记录手动确认。

| # | Phase | 功能 | 自动测试 | 手动验证 |
|---|-------|------|---------|---------|
| A1 | 22A | SK1: AI-First Skill 描述重写 (11 个 SKILL.md) | ✅ 27 pass | [ ] 验证 LLM 实际触发匹配 |
| A2 | 22A | SK2: Skill 分类 + `build_skills_summary()` XML | ✅ | [ ] 验证 system prompt 中分类显示 |
| A3 | 22A | SK3: Skill 执行记忆 (`executions.jsonl`) | ✅ | [ ] 执行 skill → 检查 jsonl 写入 |
| A4 | 22B | SK4: per-skill `config.json` 配置 | ✅ 36 pass | [ ] 修改 config → 验证行为变化 |
| A5 | 22B | SK5: pre/post hooks 系统 | ✅ | [ ] 放 hooks.py → 验证触发 |
| A6 | 22B | SK7: Skill Registry 版本追踪 | ✅ | [ ] 查看 `skills_registry.json` 内容正确 |
| A7 | 22D | AE1: Event Bus 领域事件 + Dashboard WS 转发 | ✅ 35 pass | [ ] Dashboard WS 实时接收事件 |
| A8 | 22D | AE2: Session 追加模式保存优化 | ✅ | [ ] 多轮对话 → 检查 JSONL 追加 |
| A9 | 23A | R1: Dashboard POST 1MB body 限制 | ✅ 14 pass | [ ] curl 大 body → 验证 413 |
| A10 | 23A | R2: hooks.py 沙箱 (路径/大小/危险导入) | ✅ | [ ] 放恶意 hooks → 验证拒绝 |
| A11 | 23A | R4: SSRF DNS rebinding 防护 (Transport 层) | ✅ | [ ] `web_fetch http://127.0.0.1` → 验证阻断 |
| A12 | 23A | R5: Dashboard token 日志脱敏 | ✅ | [ ] 启动后查日志 token 已 mask |
| A13 | 23B | R3: Session 原子写入 | ✅ 15 pass | [ ] 对话中断电 → Session 不损坏 |
| A14 | 23B | R10: Key 提取 LRU 缓存 | ✅ | [ ] 重复查询 → 检查缓存命中 |
| A15 | 23C | R11: 图片 20MB 限制 | ✅ 7 pass | [ ] 发大图 → 验证跳过不崩溃 |
| A16 | 23C | R16: SHA256 视觉哈希去重 | ✅ | [ ] 重复截图 → 验证去重 |
| A17 | 24 | KG1-KG5: 知识图谱演进 (5 项) | ✅ 31 pass | [ ] 多轮对话 → 检查实体/三元组 |
| A18 | 25 | F1-F8: 回头看加固 (7项修复) | ✅ 979 pass | [ ] 长时间运行稳定性 |
| A19 | 28C| OpenClaw Memory Architecture (Vector DB) | ✅ 3 pass | [ ] 多轮对话 → 检查 KG Semantic 检索 |
| A20 | 26B | BrowserTool 11 actions (navigate/click/fill/screenshot 等) | ✅ 54 pass | [ ] 真实浏览器 → 打开网页并截图 |
| A21 | 26B | 双层 SSRF 防护 (导航前 IP 检查 + route 拦截) | ✅ | [ ] 尝试导航到 `http://169.254.x.x` → 阻断 |
| A22 | 26B | 渐进信任域名 (首次确认后永久记住) | ✅ | [ ] 首次访问域名 → 确认提示 → 二次跳过 |
| A23 | 26C | Session DPAPI/Fernet 加密持久化 | ✅ 28 pass | [ ] 登录网站 → 关闭→重启 → Session 恢复 |
| A24 | 26C | TrustManager 独立化 + clear/remove | ✅ | [ ] `trusted_domains.json` 手动编辑确认 |
| A25 | 27 | SSRF TOCTOU 修复 (DNS pinning) | ✅ | [ ] 高并发 web_fetch → 无竞态 |
| A26 | 27 | AST Sandbox (替换 string-matching) | ✅ | [ ] 写 `__import__('os')` 的 hooks → 验证 AST 阻断 |
| A27 | 27 | Windows Atomic Write `safe_replace` 重试 | ✅ | [ ] Windows Defender 场景下快速写入 → 无崩溃 |
| A28 | 28A | ProviderFactory 抽象 (VLM 动态路由) | ✅ | [ ] 切换 VLM provider → 验证正确路由 |
| A29 | 28A | Plugin Lifecycle (setup/teardown hooks) | ✅ | [ ] 手动 `/reload` → 确认 teardown→setup 序列 |
| A30 | 28B | Python Sandbox (sys.addaudithook) | ✅ 5 pass | [ ] 写恶意 Python 脚本 → 验证 audit hook 阻断 |
| A31 | 28B | Shell Sandbox (stripped env) | ✅ | [ ] 检查 shell 进程环境变量 → 无敏感 key |

### B. 核心功能 — 需要生产环境验证

| # | 功能 | 描述 | 手动验证 |
|---|------|------|---------|
| B1 | Streaming 响应 | F1: `/ws/stream` 流式 token 推送 | [ ] Dashboard 实时看到逐字输出 |
| B2 | VLM Feedback Loop | F3: RPA 执行后 VLM 截图验证 | [ ] `verify=true` → VLM 比对结果 |
| B3 | Embedding 迁移 | bge-m3 1024-dim 自动迁移 | [ ] 旧 ChromaDB → 自动重建无报错 |
| B4 | Cron 跨日守护 | L15: 重启后不补跑昨天的任务 | [ ] 次日重启 → 昨日任务标 skipped |
| B5 | Outlook 外部地址 | L14: COM PropertyAccessor 发送外部邮件 | [ ] 发送到 @gmail.com → 成功 |
| B6 | 重复工具调用检测 | L16: 连续相同 tool call → 自动终止 | [ ] 触发场景 → 验证中断 |
| B7 | 深度记忆整合 | 20B CLS 慢路径 → KG 自动 re-summary | [ ] 20+ 消息 → 整合触发 |

### C. 通道生产就绪状态

| # | 通道 | 代码存在 | 生产验证 |
|---|------|---------|---------|
| C1 | CLI | ✅ | [x] 日常使用 |
| C2 | MoChat (企业微信) | ✅ | [ ] 消息收发 + 附件 |
| C3 | Telegram | ✅ | [ ] 消息 + 语音 STT |
| C4 | Discord | ✅ | [ ] WebSocket 长连 + 消息 |
| C5 | Slack | ✅ | [ ] Socket Mode + Thread 回复 |
| C6 | Email (IMAP/SMTP) | ✅ | [ ] 收信 → 自动回复 |
| C7 | 飞书 (Feishu) | ✅ | [ ] 消息 + 图片下载 |
| C8 | 钉钉 (DingTalk) | ✅ | [ ] Stream Mode 消息 |
| C9 | WhatsApp | ✅ | [ ] Bridge WS + 消息收发 |
| C10 | QQ | ✅ | [ ] botpy SDK 消息 |

### D. 安全与文档维护

| # | 项目 | 描述 | 状态 |
|---|------|------|------|
| D1 | `SECURITY.md` 更新 | L248-254 的 5 个 "pending fix" 标注需更新为已修复 | [ ] |
| D2 | `TEST_TRACKER.md` 补全 | 添加 Phase 22A ~ **Phase 28C** 的测试记录 | [x] ✅ 2026-03-24 |
| D3 | `TEST_TRACKER.md` 基线 | 回归基线从 924 更新为 **1097** | [x] ✅ 2026-03-24 |
| D4 | `ARCHITECTURE_LESSONS.md` | L273 "Phase 22" 说明过时 | [ ] 低优先级 |
| D5 | `config.sample.json` | **缺少** BrowserConfig / StreamingConfig / MemoryFeaturesConfig 等 | [ ] |
| D6 | `TOOLS.md` | 缺少 BrowserTool (第 19 个工具)，需更新为 19/19 | [x] ✅ 2026-03-24 |
| D7 | `pip-audit` 安全扫描 | `pip-audit` 发现 7 CVE / 6 包，已在 .venv311 升级修复；`npm audit` 跳过（WhatsApp Bridge 低优先级） | [x] ✅ 2026-03-24 |
| D8 | `PROJECT_STATUS.md` 去重 | L343-403 重复了 Phase 21D-21H 的内容 | [ ] |
| D9 | 根目录临时文件清理 | 20+ stale 文件 (err*.txt, test_*.txt, tmp_*.py) 应清理 | [x] ✅ 2026-03-24 |
| D10 | `EVOLUTION.md` 数据更新 | 数据汇总区仍写 811 测试用例，实际 1097+ | [ ] |

---

## 📝 每次 Phase 完成后必须更新的 5 个文档

1. ✅ `EVOLUTION.md` — 演进时间线 + Phase 条目
2. ✅ `LESSONS_LEARNED.md` — 本轮教训
3. ✅ `PROJECT_STATUS.md` — 详细进度跟踪
4. ✅ `progress_report.md` — 精简进度总览（本文档）
5. ✅ 测试全部通过

---

## 🚀 执行计划（跨会话逐步完成）

> **2026-03-23 审计后制定**，每完成一步标 `[x]`。

### Step 1：文档修复（消除信息不一致）

- [ ] 1.1 删除 `PROJECT_STATUS.md` L343-403 重复的 Phase 21D-21H 内容 (D8)
- [ ] 1.2 更新 `EVOLUTION.md` 数据汇总区：测试用例 811→1097+，工具数 18→19 (D10)
- [ ] 1.3 补全 `config.sample.json`：添加 `browser`、`streaming`、`memoryFeatures` 等新配置段 (D5)
- [ ] 1.4 更新 `SECURITY.md` L248-254：5 个 "pending fix" 改为已修复 (D1)

### Step 2：安全扫描 ✅ 2026-03-24

- [x] 2.1 执行 `pip-audit` 检查 Python 依赖漏洞 (D7) — 发现 7 CVE（cryptography/pip/pyjwt/pypdf×2/urllib3/wheel），已在 .venv311 升级修复
- [x] 2.2 `npm audit` 跳过 — WhatsApp Bridge 用户极少，未来可能裁剪；`bridge/` 无 lockfile 且 Baileys git+ssh 依赖无法解析

### Step 3：根目录清理 ✅ 2026-03-24

- [x] 3.1 归档/删除根目录 20+ 临时文件 (`err*.txt`, `test_*.txt`, `tmp_*.py`, `clean_log.txt` 等) (D9)
- [x] 3.2 确认残留 `.env` 文件是否需要删除（Config Cleanup 阶段已标记 `config.json` 为唯一源）— **保留**，仍作本地 override

### Step 4：TEST_TRACKER 补全 ✅ 2026-03-24

- [x] 4.1 添加 Phase 22A ~ 28C 全部 14 个阶段的测试记录 (D2)
- [x] 4.2 更新回归基线为 1097 (D3)
- [x] 4.3 更新 `TOOLS.md` 添加 BrowserTool 审计条目，计数改为 19/19 (D6)

### Step 5：手动测试 — B 类核心功能（优先）

- [ ] B1-B7 逐项执行（需要启动 gateway 进行生产环境验证）

### Step 6：手动测试 — A 类新增 Phase (26-28)

- [ ] A20-A31 逐项执行（Phase 26 需要安装 playwright）

### Step 7：手动测试 — A 类旧 Phase (22-25)

- [ ] A1-A19 逐项执行

### Step 8：手动测试 — C 类通道

- [ ] C2-C10 逐通道执行（需各通道 API 配置）

### Step 9：后续开发决策

- [ ] 根据测试结果决定进入 Phase 22C（Multi-Modal & Channel Extension）或先修 bug

```

- D2/D3/D6/D9 标记 `[x] ✅ 2026-03-24`
- Step 3 / Step 4 全部 checklist 标记完成

---

## 待做项 (Step 5+)

下一步为 **Step 5: 手动测试 B 类核心功能**（需启动 gateway 进行生产环境验证）。
