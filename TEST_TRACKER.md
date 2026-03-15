# Nanobot 功能测试追踪表 (Test Tracker)

> 每个新功能必须经过 ✅ **自动化测试通过** + ✅ **手动确认** 才算正式完成。
> 最后更新: 2026-03-15

---

## 测试环境

```bash
# 标准测试命令（使用 .venv311 / Python 3.11）
cd d:\Python\nanobot
$env:NO_PROXY="*"; $env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
.venv311\Scripts\python.exe -m pytest tests/ --ignore=tests/skill -q
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

---

## 🔲 待测试 / 待开发功能

| 功能 | 状态 | 测试文件 | 自动测试 | 手动确认 | 备注 |
|------|-----|---------|---------|---------|------|
| Tool 扩展: SqlQueryTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: CreateExcelTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: CreateDocxTool | 未开发 | — | — | — | 待规划 |
| Tool 扩展: PbiTool | 未开发 | — | — | — | 待规划 |
| 多用户会话隔离 | 未开发 | — | — | — | 待规划 |
| Web Dashboard | 未开发 | — | — | — | 待规划 |

---

## ⚠️ 已知问题

| 问题 | 影响 | 状态 |
|------|-----|------|
| `chromadb` 不兼容 Python 3.14 | `.venv` 无法运行 chromadb 相关测试 | 已绕过 (使用 `.venv311`) |
| `test_memory_daily.py` 有 2 个间歇性失败 | 不影响功能，环境相关 | 已知，暂不修复 |
| YOLO `test_live_yolo_detection` 需要真实 GPU | CI 环境跳过 | expected |

---

## 📋 回归测试基线

**上次全量测试结果:** 311 passed, 2 failed (pre-existing)
**测试日期:** 2026-03-14
**Python 环境:** `.venv311` (Python 3.11)

> [!TIP]
> 每次新功能开发完成后，运行全量回归测试并更新此基线数字。
> 任何 **新增 failure** 都必须在合入前修复。
