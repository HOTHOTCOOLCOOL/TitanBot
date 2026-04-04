# Nanobot 项目进度总览

> 截至 2026-04-04 （长期维护文档）

---

## 🐛 Hotfixes & Bugfixes

- **2026-03-28**: Fixed a critical `NameError` ("name 'action' is not defined") in `browser.py::get_risk_tier` that caused the agent loop to crash immediately after selecting the `browser` tool during L1 verification.

---

## 🏁 当前位置：Phase 37 ✅（Execution Trace Archive — Meta-Harness Inspired）

已完成 **20+ 个大阶段**，从 10 文件聊天机器人发展到 106 文件、14 子包、19 工具、9 通道的企业级 AI Agent。回归测试：**1264 passed, 0 failed, 1 skipped**（排除 gemini/skill 可选依赖）。

---

---

## ⏳ 待做阶段



### 🔜 Phase 39 — 延迟优化与智能分层降级 (Latency Optimization — Finalized)

> 经由三模型 Harness 碰撞论证产出的闭环降级方案。核心目标是打破 LLM 网络 TTFT 刚性下限，并解决异步本地 RAG 的 GIL 阻塞问题。详见 `docs/phase_39_latency_optimization.md`。

| 状态 | ID | 功能维度 | 优先级 | 估计工作量 |
|------|-----|---------|--------|------------|
| ⏳ | P39-1 | **L0 极简正则拦截 (Strict Regex)** | P1 | 在 `_execute_with_llm` 实现高效正则白名单，跳过 Rewriter。 |
| ⏳ | P39-2 | **动态模型轮切 (Dynamic Routing)** | P1 | 配合 `chitchat_safe` 意图，自动切换至 `fast_model` 并保留全量工具定义。 |
| ⏳ | P39-3 | **非侵入式 Context 并行拉取** | P1 | 将同步检索外置化，利用独立 ThreadPoolExecutor 异步并发抓取 RAG/KG。 |
| ⏳ | P39-4 | **熵密度反思注入 (Entropy Reflection)** | P2 | 优化 L3 反思层 Prompt，利用语义过滤闲聊垃圾数据，保留微观偏好。 |

---

### ❌ Phase 35 — Context & Skill Hardening (CC-Mini Inspired) [已取消]

> 深度逆向 `cc-mini` (Claude Code极简实现版) 提取出的效能架构范式。核心目标是以最小的代码代价解决大模型上下文冗余，并对特定工作流执行进行精准控制。详细分析见 `docs/cc_mini_analysis.md`。经过内部 Harness 审计，判定 ROI 极低，不符合 Nanobot 初衷，予以取消。

| 状态 | ID | 借鉴项 | 优先级 | 改动文件 | 估计工作量 |
|------|-----|--------|--------|---------|------------|
| ❌ | P35-1 | **Auto-Compaction** — 在触发 L4 Token 截断前，主动利用小模型进行多轮对话上下文滚动摘要压缩，保留核心决策树 | 已降级为 Hotfix | `memory.py`, `context.py` | 1-2 天 |
| ❌ | P35-2 | **First-Class CLI Skills** — 引入原生 `/review`, `/simplify` 级指令，绕开通用路由推断，建立专用隔离的执行 loop | 暂缓/搁置 | `cli/` & `skills/` | 1 天 |

**结论**：Nanobot 存量的 `memory_manager` (深层合并) 与 `evicted_context` 已能满足上下文承载需求；Skill 的 CLI 分离通道复用价值低。取消独立 Phase 发版，开发重心全面回调至 **Phase 34 (KG 检索增强)** 以及 **Phase 35v2 (Hook 机制)**。

---

### ✅ Phase 35v2 — Tool Hook & Sandbox (OpenHarness Inspired)

> 基于对 `HKUDS/OpenHarness` 的架构分析，提取符合 "单智能体/零基础设施" 原则的高 ROI 安全增强机制。完整分析见 `docs/openharness_analysis.md`。
> **经三模型 Harness 审议 (2026-04-04)**：Draft V1 的 3 项中 2 项被 Critic 否决（Hook 过度工程 / LLM 审计重蹈 L2 覆辙），仅 P35v2-3 以精简形态保留。

| 状态 | ID | 借鉴项 | 优先级 | 估计工作量 |
|------|-----|--------|--------|------------|
| ❌ | ~~P35v2-1~~ | ~~生命周期 Hook 机制 (PreToolUse/PostToolUse 事件流)~~ | 取消 | `_L1_RULES` 列表已是 Hook 管线，Pub/Sub 总线过度工程 |
| ❌ | ~~P35v2-2~~ | ~~大模型双重确认 (LLM-based 动态安全审计)~~ | 取消 | 与 L2 移除决策冲突，见 `docs/L2_VERIFICATION_RETHINK.md` L272 |
| ✅ | P35v2-3 | **可配置路径沙盒** — 扩展 L1 `_check_rule_sensitive_path()` 支持 `fnmatch` Glob deny patterns | P1 | 已完成 (2026-04-04) |
| ❌ | ~~P35v2-4~~ | ~~Swarm Coordinator 子代理协同~~ | 放弃 | 不符合架构初衷 |
| ✅ | P35v2-5 | **edit_file 路径盲区修复** — R07 规则补全 `edit_file` 工具的敏感路径检查 | P1 | 与 P35v2-3 合并完成 |

---

### ✅ Phase 22C — Multi-Modal & Channel Extension (2026-04)

| 状态 | 优先级 | 描述 |
|------|--------|------|
| ✅ | P1 | Multi-Channel Image Support (Feishu 原子交付与交互卡片无缝拼接) |
| ✅ | P2 | Unified Speech-to-Text (解耦频道下载与通用 STT 工厂) |
| ✅ | P2 | Pluggable Text-to-Speech (EdgeTTS 异步指令化合成与回传) |
| ✅ | P2 | Image Generation Tool (集成 DALL-E / Seedance 并跳过 Loop 自行发信) |

### 长期 Backlog

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Phase 38: Coordinator Mode | P2 | 受 `cc-mini` 启发，引入基于 Actor 的后台并行动作组。赋予 Agent 衍生独立 Worker 子进程的能力，探索不阻塞主会话（Chat）的高并发异步任务委派系统。 |
| Experience 检索阈值隐患修复 | P1 | `KnowledgeWorkflow` 中 `match_experience` 的相似度阈值偏低（**实际值 0.4**，且 `no_dense_penalty=1.0` 使纯 BM25 不打折），需提高至 0.65 并将 penalty 调至 0.5，避免干扰大模型上下文。 |

---

## 📋 文档过期问题

| 文档 | 问题 | 状态 |
|------|------|------|
| `SECURITY.md` L248-254 | 5 项标记 "pending fix" 但 Phase 21 已全部修复 | [x] ✅ 2026-03-24 已修复 |
| `SECURITY.md` | 新增 browser-use Worker 威胁模型章节 | ✅ 2026-03-31 已补充 |
| `ARCHITECTURE_LESSONS.md` L273 | "Phase 22" 说明已过时 | ✅ 2026-04-04 文件已归档/删除 |
| `TEST_TRACKER.md` | Phase 33 更新完毕，含缺陷追踪表 | ✅ 2026-03-31 已更新 |
| `README.md` | Badge (1271/33→12 papers), Roadmap 修正, Phase 34 加入 | ✅ 2026-03-31 已修正 |
| `paper_analysis_report.md` | BubbleRAG 论文对比分析完整报告 | ✅ 2026-03-31 新建 |
| `docs/cc_mini_analysis.md` | CC-Mini 与 Claude Code 架构提取分析及高 ROI 方案 | ✅ 2026-04-02 新建 |
| `docs/openharness_analysis.md` | OpenHarness 架构借鉴分析与 Harness 审计策略 | ✅ 2026-04-03 新建 |
| `.agent/workflows/harness.md` | 混合模型碰撞工作流 (Planner/Critic) 初始化 | ✅ 2026-04-03 新建 |

---

---

<details>
<summary><b>历史完结阶段归档 (Phase 29 - Phase 36)</b></summary>
<br>

## 🛡️ Phase 36 — Cross-Platform & OS Sandbox ✅ 已完成 (2026-04)

> 深度采纳 Harness (Planner/Critic) 碰撞意见。摒弃庞大重构，零基建下实现跨平台优雅降级与沙箱自适应加固。

| 状态 | ID | 模块 | 实现细节 |
|------|-----|--------|---------|
| ✅ | P36-1 | Outlook 平台降级 | `outlook.py` 执行时检查 `sys.platform`，跨平台实现 Graceful Degradation，放弃高成本重构。 |
| ✅ | P36-2 | 智能沙箱感知 | `sandbox.py` 根据 macOS/Win 发放对应基础环节环境变 (如 macOS 独有 `$TMPDIR` / `$HOME`)。 |
| ✅ | P36-3 | L1 OS 黑名单补强 | 赋予 `shell.py` L1 Guard 包含 `osascript` / `launchctl` 等专属 macOS deny patterns。 |

---

## 🔬 Phase 34 — KG 检索增强 (BubbleRAG-Inspired) ✅ 已完成 (2026-04)

> 源自 BubbleRAG (arXiv 2603.20309) 论文对比分析，提取并集成 3 项在零架构成本内的检索增强技术。

| 状态 | ID | 借鉴项 | 实现细节 |
|------|-----|--------|---------|
| ✅ | P34-1 | **Semantic Anchor Grouping** | `vector_store.py` 中 `rewrite_query_with_anchors` 抽取纯 JSON Anchors。 |
| ✅ | P34-2 | **Coverage Penalty** | 基于 Anchor 命中率，在 `get_entity_context` 给候选实体计算软底线惩罚。 |
| ✅ | P34-3 | **Schema Relaxation** | `get_entity_context` 将得分为 0 若在 `prefetch_rag` 出现的实体拯救为 1.0。 |

---

## 🔬 Phase 29 — 论文借鉴增强 (Paper-Inspired) ✅ 已完成 (2026-03)

> 源自 5 篇论文对比分析，已全部集成到现有单智能体循环中，保持了零额外架构成本的原则。

| 状态 | ID | 借鉴项 | 实现细节 |
|------|-----|--------|---------| 
| ✅ | P29-1 | Directive Signal | `outcome_tracker` 检测负面反馈，LLM 提取 Actionable Rule 存入 Experience Bank |
| ✅ | P29-2 | System Reminders | `loop.py` 长会话检测并注入行为纠偏 prompt；配置支持按 Workflow 路由独立模型 |
| ✅ | P29-3 | Bridging Facts | `KnowledgeGraph.generate_bridging_facts` 离线推导多跳关联 |
| ✅ | P29-4 | Knowledge Completion | `VectorMemory.search_with_completion` 检索后缺失验证与补充召回 |
| ✅ | P29-5 | 自动经验生成 | `loop.py` 错误断路器触发 LLM 分析并存入 Experience Bank |
| ✅ | P29-6 | 知识溯源链 | `task_knowledge.py` 存入溯源字段 `derived_from` |

---

## 🛡️ Phase 31/32 — 漏斗验证层 (Verification Layer L0→L1→L3) ✅ 已完成 (2026-03)

> 基于漏斗模型的防过度工程架构，完全解耦于 AgentLoop，各层可通过 `config.json` 独立开关。L2（小模型自省）因结构性误拒问题在 Phase 32 中移除，详见 `docs/L2_VERIFICATION_RETHINK.md`。

| 状态 | 层级 | 功能说明 | 实现细节 |
|------|-----|--------|---------| 
| ✅ | **L0** | 认知路由与上下文增强 | 重构原有零散注入，在执行前统一注入 Experience/Reflection/System Reminder |
| ✅ | **L1** | 刚性边界规则拦截 | 纯 Python Pre-execution 拦截（R01-R09: 空消息、破坏指令、敏感路径、网络外泄、命令长度） |
| ❌ | ~~L2~~ | ~~辅助小模型自省验证~~ | 已移除 — 因误拒率远高于误放率，导致雪崩效应 |
| ✅ | **L3** | 事后反思与知识萃取 | Async fire-and-forget：成功路径提取 + anti-pattern 审计（log-only） |

---

## 🛡️ Phase 32 — 智能审批与安全护栏 (Agent Safety & Smart HITL Framework) ✅ 已完成 (2026-03)

> 基于防御纵深设计的四层安全网，在引入生产级操作拦截的同时，通过"零成本白名单"保障了日常流畅交互。

| 状态 | 功能维度 | 功能说明 | 实现细节 |
|------|-----|--------|---------| 
| ✅ | **1. 风险分级 (Static Guardrails)** | 所有 `Tool` 内置静态或动态风险评估 (`RiskTier`) | 修改 `base.py:Tool`，将 `browser(content)` 标为读取、`shell` 与 `outlook(send)` 标为高危修改。 |
| ✅ | **2. 拦截与审批 (Smart HITL)** | 自动阻断并保存 L1 会话，直到人工给予授权 | 修改 `AgentLoop` 和 `Session`，拦截并挂起执行，向外推送 3 选项互动审批卡。 |
| ✅ | **3. 信任白名单 (ApprovalStore)** | 用户对于同类高危动作可以选择 "Always Approve" 生成永久免打扰白名单 | `hitl_store.py` 基于通配符进行规则下放匹配，实现"只问一次"的智能审批体验。 |
| ✅ | **4. L2 退役与 L1/L3 强化** | 移除误拒率过高的小模型自省层，扩展确定性拦截和事后审计 | 新增 L1 R05-R09 规则，L3 新增 anti-pattern 审计（log-only）。详见 `docs/L2_VERIFICATION_RETHINK.md`。 |

---

## 🔬 Phase 33 — Browser-RPA 降级链路优化 ✅ 已完成 (2026-03)

> 对 browser-use Worker 与 RPA OS 级操作的降级链路进行全面优化。实施 6 项架构改进。

| 状态 | 功能维度 | 功能说明 | 实现细节 |
|------|---------|---------|----------|
| ✅ | **1. 生命周期管理** | `ensure_visible` 有头/无头切换 | 配置化控制 `headless=False` 为默认，`ensure_visible` 保留为 escape hatch |
| ✅ | **2. 坐标漂移修复** | Playwright 截图坐标与物理屏幕对齐 | `--start-maximized` + `viewport=None` + `monitor_context` 60s 过期 |
| ✅ | **3. 降级信号协议** | 统一 `[FALLBACK_RPA]` 结构化信号 | Worker 异常/超时时前缀标记，LLM 自然规划 `screen_capture` -> `rpa` |
| ✅ | **4. 超时强制释放** | `asyncio.wait_for` 僵尸清理 | `try...finally` + `browser.close()` + `_sync_pages()` |
| ✅ | **5. CDP 端口移除** | 9222 硬编码架构不可行 | 移除 CDP 共享管道，Worker 自行启动独立 browser-use 会话 |
| ✅ | **6. 代码清理** | 死代码/硬编码移除 | `browser.py` 死代码清除，配置化 headless，`rpa_executor.py` 拦截修正 |

---

## 🔍 Phase 33 Retro — 安全审计发现 (2026-03-31)

> 三模型 Harness 工作流（Planner -> Critic -> Synthesizer）对项目进行深度回顾审计。以下为已确认的缺陷和待修复项。

| 严重性 | ID | 描述 | 影响范围 | 修复方案 |
|--------|-----|------|---------|----------|
| 🔴 Critical | BUG-HITL-1 | `loop.py` L597 `self.config.master_identities` -> `AttributeError` | 远程 HITL 审批广播永远崩溃 | ✅ 已修复：改用 `self._get_config()` |
| 🟠 Medium | BUG-HITL-2 | `hitl_store._save()` 非原子写入 | 崩溃后 `approvals.json` 损坏 | ✅ 已修复：改用 `tempfile` + `os.replace()` |
| 🟠 Medium | DEBT-KB-1 | `match_experience` 阈值=0.4, `no_dense_penalty=1.0` | 小语料库误召回噪音注入 | ✅ 已修复：提高至 0.65, penalty 降至 0.5 |
| 🟠 Medium | SEC-BUW-1 | `browser_use_worker` 内层 Agent 绕过 L1/HITL | 间接 Prompt Injection 风险 | ✅ 已修复：Context Sandwiching + Forced-HITL |
| 🟡 Low | DEBT-KB-2 | `_key_extraction_cache` 模块级全局状态 | 多租户数据泄露 | ✅ 已修复：迁移至实例级 |

</details>
