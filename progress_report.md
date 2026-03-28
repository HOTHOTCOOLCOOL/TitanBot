# Nanobot 项目进度总览

> 截至 2026-03-28 （长期维护文档）

---

## 🐛 Hotfixes & Bugfixes

- **2026-03-28**: Fixed a critical `NameError` ("name 'action' is not defined") in `browser.py::get_risk_tier` that caused the agent loop to crash immediately after selecting the `browser` tool during L1 verification.

---

## 🏁 当前位置：Phase 32 ✅（Agent Safety & Smart HITL Framework）

已完成 **20+ 个大阶段**，从 10 文件聊天机器人发展到 106 文件、14 子包、19 工具、9 通道的企业级 AI Agent。回归测试：**1249 passed, 0 failed, 1 skipped**（排除 gemini/skill 可选依赖）。

---

---

## ⏳ 待做阶段

### Phase 22C — Multi-Modal & Channel Extension

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Multi-Channel Image Support | P1 | 扩展图片下载到 MoChat, Slack, DingTalk |
| Unified Speech-to-Text | P2 | 统一语音输入管道（目前仅 Telegram） |
| Image Generation Tool | P2 | 集成 DALL-E / Stable Diffusion |

### 长期 Backlog

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Phase 33: Cross-Platform Support | P2 | Windows/macOS 双端架构优化。解决核心依赖痛点：重构 `outlook.py` 脱离 COM 绑定、强化 `ui_anchors.py` 跨平台跨感知 fallback，并分离 `sandbox` & `shell` 的 OS 保护边界。 |
| Experience 检索阈值隐患修复 | P1 | `KnowledgeWorkflow` 中 `match_experience` 的相似度阈值偏低（0.53 仍可召回无关经验），需要排查并提高至 0.65 以上，避免干扰大模型上下文。 |

---

## 📋 文档过期问题

| 文档 | 问题 | 状态 |
|------|------|------|
| `SECURITY.md` L248-254 | 5 项标记 "pending fix" 但 Phase 21 已全部修复 | [x] ✅ 2026-03-24 已修复 |
| `ARCHITECTURE_LESSONS.md` L273 | "Phase 22" 说明已过时 | 低优先级 |
| `TEST_TRACKER.md` | 停在 Phase 21G，未覆盖 22A-25；回归基线过期 (924 vs 979) | **需更新** |
| `README.md` | 总体内容仍准确，无需改动 | ✅ |

---

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

> 基于防御纵深设计的四层安全网，在引入生产级操作拦截的同时，通过“零成本白名单”保障了日常流畅交互。

| 状态 | 功能维度 | 功能说明 | 实现细节 |
|------|-----|--------|---------|
| ✅ | **1. 风险分级 (Static Guardrails)** | 所有 `Tool` 内置静态或动态风险评估 (`RiskTier`) | 修改 `base.py:Tool`，将 `browser(content)` 标为读取、`shell` 与 `outlook(send)` 标为高危修改。 |
| ✅ | **2. 拦截与审批 (Smart HITL)** | 自动阻断并保存 L1 会话，直到人工给予授权 | 修改 `AgentLoop` 和 `Session`，拦截并挂起执行，向外推送 3 选项互动审批卡。 |
| ✅ | **3. 信任白名单 (ApprovalStore)** | 用户对于同类高危动作可以选择 "Always Approve" 生成永久免打扰白名单 | `hitl_store.py` 基于通配符进行规则下放匹配，实现“只问一次”的智能审批体验。 |
| ✅ | **4. L2 退役与 L1/L3 强化** | 移除误拒率过高的小模型自省层，扩展确定性拦截和事后审计 | 新增 L1 R05-R09 规则，L3 新增 anti-pattern 审计（log-only）。详见 `docs/L2_VERIFICATION_RETHINK.md`。 |
