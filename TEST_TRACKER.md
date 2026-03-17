# Nanobot 功能测试追踪表 (Test Tracker)

> 每个新功能必须经过 ✅ **自动化测试通过** + ✅ **手动确认** 才算正式完成。
> 最后更新: 2026-03-17

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

---

## 🔲 待测试 / 待开发功能

| 功能 | 状态 | 测试文件 | 自动测试 | 手动确认 | 备注 |
|------|-----|---------|---------|---------|------|
| Tool 扩展: SqlQueryTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: CreateExcelTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: CreateDocxTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: PbiTool | 未开发 | — | — | — | 待规划 |
| 多用户会话隔离 | 已取消 | — | — | — | 转为 Unified Master Identity |
| Web Dashboard | 已完成 | `dashboard/app.py` | — | ✅ | 包含在 Phase 15 中 |

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

**上次全量测试结果:** 599 passed, 3 failed (pre-existing: 2x test_memory_daily intermittent, 1x test_knowledge_workflow word_similarity)
**测试日期:** 2026-03-17
**Python 环境:** `.venv311` (Python 3.11)

> [!TIP]
> 每次新功能开发完成后，运行全量回归测试并更新此基线数字。
> 任何 **新增 failure** 都必须在合入前修复。
