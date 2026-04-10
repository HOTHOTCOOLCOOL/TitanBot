# Nanobot 项目进度总览

> 截至 2026-04-06 （当前状态追踪 L1，唯一维护来源）

---

## 🏁 当前位置：Phase 42 核心重构完结 ✅ → 阶段收官

已完成 **42 个大阶段**的架构基建进化，回归测试：**1268 passed, 0 new failures, 20 new tests added**。
- **2026-04-06**: 完成 Phase 41 `L1验证`、`HITL强管控`、`CircuitBreaker防雪崩`、`FloodGuard消息防刷屏` 中间件的生产环境仿真验证。V2 洋葱管线稳健运作。
- **2026-04-06 Harness 架构审查**: 针对核心架构基线（Phase 38~41）完成 5 阶多模型辩证评审。发现 **1 个 P0 安全漏洞**（SubagentManager 绕过中间件裸奔）、**1 个 P1 技术债**（双脑知识库污染）、**2 个 P2 重构项**（Loop 解耦 + Lazy-RAG）。
- **2026-04-07**: 完成 Phase 42A `SubagentManager` 漏洞修复与 Phase 42B 双脑知识库统一合并，并在架构上根除幻觉级联。
- **2026-04-10**: Phase 42 (A/B/C) 全线回归测试完成！涵盖安全沙盒拦截验证、`Experience Bank` 迁移与幂等测试、意图路由（VLM / Chitchat）极速直达逻辑。修复了 `weixin.py` 图像通道 Bug。
- **2026-04-10**: 随后完成了 Phase 42 系列最终的 Backlog：**全链路 Trace-ID 染色系统与可观测性升级**。项目全面达成单次请求内的异步多任务生命周期全息监控。阶段收官！
- **2026-04-10 Harness 架构审查**: 针对 Cron 重试风暴与 SSRS 幻觉替换问题完成 5 阶多模型辩证评审（ADR-44）。核心决策：**① 引入确定性副作用检测（TraceArchive 工具调用日志替代字符串匹配）；② 重试计数器 + `error_fatal` 终态强制熔断（MAX_RETRIES=1）；③ L1 中间件动态封锁 `outlook.search` 防幻觉替换；④ SSRS Fast-fail 10s + 结构化 JSON 错误输出**。

> **ℹ️ 文档归档说明**: 
> 所有的 "Lessons Learned (避坑总结)" 现已收录入 `docs/rules/ARCHITECTURE.md` 第7章。
> Phase 33 - Phase 41 的完整发布历史和技术清单已经全盘冷藏封存至 `docs/archive/EVOLUTION_epoch33_41.md`。这里只保留活跃进度。

---

## 🐛 Hotfixes & Bugfixes

- **2026-03-28**: Fixed a critical `NameError` ("name 'action' is not defined") in `browser.py::get_risk_tier` that caused the agent loop to crash immediately after selecting the `browser` tool during L1 verification.

---

## ⏳ 待做阶段 (Backlog)

### 🚨 Phase 42A: SubagentManager 安全补丁 [P0 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| **P0** | **✅ 已完成** | 已通过 `_run_agent_loop` 门面重构子代理循环，移除无 HITL 执行 Shell 的风险。技术细节已冷藏至 `docs/archive/EVOLUTION_epoch42.md`。 |

### 🔴 Phase 42B: 双脑知识库统一 [P1 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P1 | **✅ 已完成** | 删除了 `ReflectionStore`，移除了双线并行写入与读取路径，仅保留基于 VectorStore 的 Experience Bank 作为知识库唯一事实来源。提供幂等迁移脚本 `migrate_reflections.py` 保留旧版本沉淀规律。节省了冗余上下文和 `_INJECTION_BUDGET`。 |

### 🟡 Phase 42C: loop.py 上帝类解耦首批 [P2 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P2 | **✅ 已完成** | 提取 `nanobot/agent/routing.py`，引入 `ModelRouter` 和 `IntentClassifier`，消除了 VLM 降级配置与 `_CHITCHAT_REGEX` 在 `_run_agent_loop` 及下游环节的双重重复计算。 |

### 🔵 Phase 43: Hybrid Lazy-RAG 向量检索升级 [P3 · 设计预留]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P3 | 设计预留 | 向量库当前存储 LLM 生成的摘要块（粗粒度语义索引），高置信命中后无法获取原始上下文细节。**修复方案**：在 `ingest_text` 时追加 `origin_session_id` + `origin_message_range` 指针元数据；实现 `deep_fetch(origin_ref)` 方法及对应的 `recall_detail(topic)` Agent 工具，实现"摘要目录检索 + 按需深层原文拉取"的两段式 Hybrid Lazy-RAG 架构。工期 8-12h。 |

### 🟢 Phase 43 (ADR-43): Provider-Level XML Tool Call Fallback Parser [P2 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P2 | **✅ 已完成** | 设计并实现基于 Read-Only 与运行时白名单（`valid_tool_names`）过滤的 Provider-Level XML 落底级容灾兜底防线。彻底兼容并防范了 Prompt Injection 等绕过攻击，提取后的工具调用统一走正常代理洋葱防线（L1 Middleware）。 |

### 🆕 Phase 44 (ADR-44): Cron 重试引擎加固 & SSRS 幻觉防线 [P0/P1 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P0 | **✅ 已完成** | **重试引擎重构**：`CronJobState` 新增 `retry_count` + `parent_trace_id`，硬性 `MAX_RETRIES=1` 熔断阈值，`error_fatal` 终态锁死，彻底终止日内重试风暴。副作用检测改为查询 `TraceArchive` 结构化 Tool Call 日志（替代不可靠字符串匹配），`partial_success` 状态携带通知防止静默吞噬。 |
| P1 | **✅ 已完成** | **SSRS 幻觉防线**：`fetch_report.py` timeout 缩至 10s + 失败路径输出 `{"error_type": "DependencyFatal"}` 结构化 JSON。在 `verification.py` 新增 `R-SSRS-001` 规则，一旦检测到 SSRS 致命失败，L1 中间件物理封锁 `outlook.search` 等替代工具，从防线层杜绝幻觉替换。 |
| P3 | ⏳ **待开发** | **UnifiedScheduler 迁移**（@Phase44-Target 后续）：`scheduler.py` 的单一事件循环设计优于 `CronService` 独立 timer 模型，待业务稳定后作为下一窗口期完成迁移。 |



---

### Phase 38: Coordinator Mode (Worker 子进程并发探索) [P3 · 已完成]
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P3 | **✅ 已完成** | 实现了基于 aiohttp JSON-RPC IPC 的真正进程级并发独立 Worker 体系，全面接管并隔离长程任务。已通过沙箱解偶（ReadOnlyKnowledgeStore）与 HITL 多核安全门控。技术细节已冷藏。 |

### 知识库相关技术债
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P2 | Verifying | **Experience 检索阈值回归验证** — 代码层面已修复（`knowledge_workflow.py` L230-231：`threshold=0.65, no_dense_penalty=0.5`，注释标记 `DEBT-KB-1`）。**遗留隐患**：小语料（<5 条 Experience）场景下 BM25 IDF 趋零，退化为 Jaccard fallback 路径，该路径在 `threshold=0.65` 下的拒假命中行为**尚未经过回归测试**。待补：`tests/test_experience_threshold.py`（已创建）。 |

### 架构可观测性债务 (Observability Debt)
| 优先级 | 开发状态 | 功能维度说明 |
|--------|---------|-------------|
| P1 | **✅ 已完成** | **全链路 Trace-ID / X-Route 染色系统 (Phase 42 A/B Backlog)** — 成功落地！在核心主循环 `_process_message` 应用 Shell Pattern 无伤接管元数据。实现了 Loguru全局 Patcher + ContextVar 无态流转隔离，打通了 Subagent 异步血缘传递和各大安全验证中间件拦截的路由标签 (Route/Intercept Tags)。为系统彻底扫清了后台长期任务及并发排障盲区。 |

---

## 📋 文档更新与清理记录

| 文档 | 问题 | 状态 |
|------|------|------|
| `docs/adr/ADR-42B-trace-id.md` | Phase 42B 全链路 Trace-ID 系统 Harness 辩证 ADR：Shell Pattern + Loguru Patcher + 事件边界注入 + Subagent 血缘传播 | ✅ 2026-04-07 已创建 |
| `docs/adr/ADR-42-harness-review.md` | Phase 41 后首次 Harness 5 阶架构辩证审查最终 ADR，记录 P0/P1/P2 发现与架构决策 | ✅ 2026-04-06 已创建 |
| `docs/architecture_harness_baseline.md` | 追加 Harness 审查结论摘要，更新碰撞点为已作答 | ✅ 2026-04-06 已更新 |
| `docs/archive/` | 建立 `EVOLUTION_epoch33_41.md`，将过去几周的大量折叠细节全部冷库封存 | ✅ 2026-04-06 已执行大清理 |
| `docs/rules/ARCHITECTURE.md` | 将散落的避坑指南正式纳入架构戒律的 `第7章` | ✅ 2026-04-06 已入库 |
| `文档历史漏洞` | Phase 22~33 积累的所有陈旧/冲突的 Markdown 文档记录 | ✅ 2026-04-06 彻底清理 |

