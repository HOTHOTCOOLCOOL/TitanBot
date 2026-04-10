# Epoch 3: Phase 33-41 演进回顾与架构对比

> Last updated: 2026-04-06
> 本代重点：跨平台降级、RPA-Browser链路深化、论文借鉴增强（检索与决策）、L0-L3 漏斗验证层重构、洋葱中间件架构管线、智能 HITL 拦截体系、崩溃恢复断点续传。

---

## ✅ Phase 40A — 稳定性基石 (Stability Foundations)
> 经由 5 段 Harness 辩证法锤炼产出并已全面落实通过测试。详见 `implementation_plan.md`。

| 状态 | ID | 功能维度 | 优先级 | 改动文件 |
|------|-----|---------|--------|------------|
| ✅ | P40A-1 | **工具结果强制截断** — `max_tool_result_chars=16000`，保留头尾各 8000 chars | P0 | `loop.py`, `config/schema.py` |
| ✅ | P40A-2 | **Session 并发门闩 + 快照传递** — Lock + `to_snapshot()` 隔离后台任务直接引用 | P0 | `session/manager.py`, `agent/loop.py` |
| ✅ | P40A-3 | **动态 Token-Budget 裁剪** — `litellm.token_counter` 替换固定 `memory_window=50` | P0 | `loop.py`, `config/schema.py` |

---

## ✅ Phase 40B — 可靠性增强 (Reliability)

| 状态 | ID | 功能维度 | 优先级 | 改动文件 |
|------|-----|---------|--------|------------|
| ✅ | P40B-1 | **轻量断点续传** — 工具执行前写 checkpoint WAL，进程崩溃后向 master_identities 推送恢复通知 | P1 | `loop.py`, `session/manager.py`, `config/schema.py` |
| ✅ | P40B-2 | **MEMORY.md 滚动 .bak 备份** — 覆写前保留最新 5 份，防 LLM Hallucination 覆写损坏记忆 | P1 | `agent/memory.py` |

---

## ✅ Phase 41 — 洋葱中间件架构 (Onion Middleware Pattern)

> 经由 5 段 Harness 辩证法锤炼产出并全面落地。旧代码完全保留，通过 `agents.experimental.middleware_enabled` 开关灰度至 v2 管线。

| 状态 | ID | 功能维度 | 改动文件 |
|------|-----|---------|--------|
| ✅ | P41-1 | **中间件基础架构** — TurnContext (abort/finish 状态机) + AgentMiddleware 两段式基类 + MiddlewarePipeline 迭代式执行器 (O(1) 栈深) | `middleware/{__init__,base,pipeline}.py` |
| ✅ | P41-2 | **MetricsMiddleware** — 计时器迁移（最外层） | `middleware/metrics.py` |
| ✅ | P41-3 | **CircuitBreakerMiddleware** — 全-exception 熔断、L14 精确重复、模糊循环检测 + P37 postmortem | `middleware/circuit_breaker.py` |
| ✅ | P41-4 | **VerificationMiddleware** — L1 规则拦截 + L3 反模式审计 | `middleware/verification_mw.py` |
| ✅ | P41-5 | **HITLMiddleware** — 风险分级 + 强制 HITL + 审批挂起 + 远程广播 | `middleware/hitl.py` |
| ✅ | P41-6 | **CrashRecoveryMiddleware** — P40B-1 WAL checkpoint 写入/清除 | `middleware/crash_recovery.py` |
| ✅ | P41-7 | **ActionHistoryMiddleware** — P33 browser/RPA 历史注入+记录 | `middleware/action_history.py` |
| ✅ | P41-8 | **FloodGuardMiddleware** — message() 洪水防护 | `middleware/flood_guard.py` |
| ✅ | P41-9 | **ToolExecutor** — 洋葱最内层，并发工具执行 + 结果组装 | `middleware/tool_executor.py` |
| ✅ | P41-10 | **loop.py 集成** — _is_error_result 提升、_call_llm_for_turn 提取、_run_agent_loop_v2、config 开关 | `loop.py`, `config/schema.py` |

---

## ✅ Phase 39 — 延迟优化与智能分层降级 (Latency Optimization)

> 经由三模型 Harness 碰撞论证产出的闭环降级方案。核心目标是打破 LLM 网络 TTFT 刚性下限，并解决异步本地 RAG 的 GIL 阻塑问题。详见 `docs/phase_39_latency_optimization.md`。

| 状态 | ID | 功能维度 | 改动文件 |
|------|-----|---------|--------|
| ✅ | P39-1 | **L0 极简正则拦截 (Strict Regex)** | `agent/loop.py` |
| ✅ | P39-2 | **动态模型轮切 (Dynamic Routing)** | `agent/loop.py`, `config/schema.py` |
| ✅ | P39-3 | **非侵入式 Context 并行拉取** | `agent/loop.py` |
| ✅ | P39-4 | **熵密度反思注入 (Entropy Reflection)** | `agent/verification.py` |

---

## ❌ Phase 35 — Context & Skill Hardening (CC-Mini Inspired) [已取消]
> 深度逆向 `cc-mini` 提取出的效能架构范式。经过内部 Harness 审计，判定 ROI 极低，不符合 Nanobot 初衷，予以取消。开发重心全面回调至 Phase 34 (KG 检索增强) 以及 Phase 35v2 (Hook 机制)。

---

## ✅ Phase 35v2 — Tool Hook & Sandbox (OpenHarness Inspired)
> 基于对 `HKUDS/OpenHarness` 的架构分析，提取符合 "单智能体/零基础设施" 原则的高 ROI 安全增强机制。

| 状态 | ID | 借鉴项 | 优先级 |
|------|-----|--------|--------|
| ✅ | P35v2-3 | **可配置路径沙盒** — 扩展 L1 `_check_rule_sensitive_path()` 支持 `fnmatch` Glob deny patterns | P1 |
| ✅ | P35v2-5 | **edit_file 路径盲区修复** — R07 规则补全 `edit_file` 工具的敏感路径检查 | P1 |

---

## ✅ Phase 22C — Multi-Modal & Channel Extension (2026-04)

| 状态 | 优先级 | 描述 |
|------|--------|------|
| ✅ | P1 | Multi-Channel Image Support (Feishu 原子交付与交互卡片无缝拼接) |
| ✅ | P2 | Unified Speech-to-Text (解耦频道下载与通用 STT 工厂) |
| ✅ | P2 | Pluggable Text-to-Speech (EdgeTTS 异步指令化合成与回传) |
| ✅ | P2 | Image Generation Tool (集成 DALL-E / Seedance 并跳过 Loop 自行发信) |
| ✅ | P2 | **Channel 加减法** — 新增 WeCom (企业微信) + Weixin (个人微信)；移除 Discord/Slack/Telegram/Mochat 顺序列表 |

---

## 🛡️ Phase 36 — Cross-Platform & OS Sandbox
> 深度采纳 Harness 碰撞意见。摒弃庞大重构，零基建下实现跨平台优雅降级与沙箱自适应加固。

| 状态 | ID | 模块 | 实现细节 |
|------|-----|--------|---------|
| ✅ | P36-1 | Outlook 平台降级 | `outlook.py` 执行时检查 `sys.platform` 实现 Graceful Degradation |
| ✅ | P36-2 | 智能沙箱感知 | `sandbox.py` 根据 macOS/Win 发放对应基础环节环境变量 |
| ✅ | P36-3 | L1 OS 黑名单补强 | 赋予 `shell.py` L1 Guard 包含 `osascript` / `launchctl` 等专属 deny patterns |

---

## 🔬 Phase 34 — KG 检索增强 (BubbleRAG-Inspired)
> 源自 BubbleRAG (arXiv 2603.20309) 论文对比分析，提取并集成检索增强技术。

| 状态 | ID | 借鉴项 | 实现细节 |
|------|-----|--------|---------|
| ✅ | P34-1 | **Semantic Anchor Grouping** | `vector_store.py` 中 `rewrite_query_with_anchors` 抽取纯 JSON Anchors |
| ✅ | P34-2 | **Coverage Penalty** | 基于 Anchor 命中率在 `get_entity_context` 给候选实体计算软底线惩罚 |
| ✅ | P34-3 | **Schema Relaxation** | `get_entity_context` 将得分为0若在 `prefetch_rag` 出现的实体拯救为1.0 |

---

## 🔬 Phase 29 — 论文借鉴增强 (Paper-Inspired)
> 源自 5 篇论文对比分析，集成到现有单智能体循环中，保持零额外架构成本。

| 状态 | ID | 借鉴项 | 实现细节 |
|------|-----|--------|---------| 
| ✅ | P29-1 | Directive Signal | `outcome_tracker` 检测负面反馈，LLM 提取 Actionable Rule 存入 Experience Bank |
| ✅ | P29-2 | System Reminders | `loop.py` 长会话检测并注入行为纠偏 prompt；配置支持按 Workflow 路由独立模型 |
| ✅ | P29-3 | Bridging Facts | `KnowledgeGraph.generate_bridging_facts` 离线推导多跳关联 |
| ✅ | P29-4 | Knowledge Completion | `VectorMemory.search_with_completion` 检索后缺失验证与补充召回 |
| ✅ | P29-5 | 自动经验生成 | `loop.py` 错误断路器触发 LLM 分析并存入 Experience Bank |
| ✅ | P29-6 | 知识溯源链 | `task_knowledge.py` 存入溯源字段 `derived_from` |

---

## 🛡️ Phase 31/32 — 漏斗验证层 (Verification Layer L0→L1→L3)
> 基于漏斗模型的防过度工程架构，完全解耦于 AgentLoop，各层可通过 `config.json` 独立开关。

| 状态 | 层级 | 功能说明 | 实现细节 |
|------|-----|--------|---------| 
| ✅ | **L0** | 认知路由与上下文增强 | 重构原有零散注入，在执行前统一注入 Experience/Reflection/System Reminder |
| ✅ | **L1** | 刚性边界规则拦截 | 纯 Python Pre-execution 拦截（R01-R09: 空消息、破坏指令、敏感路径、网络外泄、命令长度） |
| ✅ | **L3** | 事后反思与知识萃取 | Async fire-and-forget：成功路径提取 + anti-pattern 审计（log-only） |

---

## 🛡️ Phase 32 — 智能审批与安全护栏 (Agent Safety & Smart HITL)
> 基于防御纵深设计的四层安全网，在引入生产级操作拦截的同时，通过"零成本白名单"保障了日常流畅交互。

| 状态 | 功能维度 | 功能说明 |
|------|-----|--------| 
| ✅ | **1. 风险分级 (Static Guardrails)** | 所有 `Tool` 内置风险评估 (`RiskTier`)，`browser(content)` 标读取，`shell` 为高危修改。 |
| ✅ | **2. 拦截与审批 (Smart HITL)** | 拦截挂起执行，向外推送选项审批卡。 |
| ✅ | **3. 信任白名单 (ApprovalStore)** | 用户对高危动作可开启 "Always Approve" 免打扰白名单。 |
| ✅ | **4. L1/L3 强化** | 移除 L2 模型自省（因高误拒率），扩展确定性拦截。详见 `docs/L2_VERIFICATION_RETHINK.md`。 |

---

## 🔬 Phase 33 — Browser-RPA 降级链路优化
> 对 browser-use Worker 与 RPA OS 级操作的降级链路进行全面优化。

| 状态 | 功能维度 | 功能说明 | 实现细节 |
|------|---------|---------|----------|
| ✅ | **1. 生命周期管理** | `ensure_visible` 有头/无头切换 | 配置化控制 `headless=False` 为默认 |
| ✅ | **2. 坐标漂移修复** | Playwright 截图坐标对齐 | `--start-maximized` + `viewport=None` |
| ✅ | **3. 降级信号协议** | 统一 `[FALLBACK_RPA]` 结构化信号 | Worker 异常前缀标记，自然规划 `screen_capture` -> `rpa` |
| ✅ | **4. 超时强制释放** | `asyncio.wait_for` 僵尸清理 | `try...finally` + `browser.close()` |
| ✅ | **5. CDP 端口移除** | 9222 硬编码架构不可行 | 移除 CDP 管道，启动独立 browser-use 会话 |
| ✅ | **6. 代码清理** | 死代码消除 | `browser.py` 按需配置化，拦截修正 |

---

## 🔍 Phase 33 Retro — 安全审计发现
> 三模型 Harness 工作流审计。

| 严重性 | ID | 描述 | 影响范围 | 修复方案 |
|--------|-----|------|---------|----------|
| 🔴 Critical | BUG-HITL-1 | `loop.py` L597 `self.config.master_identities` -> `AttributeError` | 远程 HITL 广播崩溃 | ✅ 改用 `self._get_config()` |
| 🟠 Medium | BUG-HITL-2 | `hitl_store._save()` 非原子写入 | 崩溃后 json 损坏 | ✅ 改用 `tempfile` + `os.replace()` |
| 🟠 Medium | DEBT-KB-1 | `match_experience` 阈值=0.4 | 语料纯度降低 | ✅ 提高至0.65, penalty 降至 0.5 |
| 🟠 Medium | SEC-BUW-1 | Worker 绕过 HITL | Prompt Injection | ✅ Context Sandwiching + Forced-HITL |
| 🟡 Low | DEBT-KB-2 | `_key_extraction_cache` 模块级全局状态 | 多租户泄露 | ✅ 迁移至实例级 |
