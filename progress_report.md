# Nanobot 项目进度总览

> 截至 2026-03-26 （长期维护文档）

---

## 🏁 当前位置：Phase 30 ✅（弱模型防护 / Weak Model Safety Guards）

已完成 **20+ 个大阶段**，从 10 文件聊天机器人发展到 105 文件、14 子包、19 工具、9 通道的企业级 AI Agent。回归测试：**1209 passed, 0 failed, 1 skipped**（排除 gemini/skill 可选依赖）。

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
| Phase 31: Verification Layer | P1 | 基于漏斗模型的防过度工程架构：L0(前置相似度经验认知路由) -> L1(刚性边界规则拦截) -> L2(事前辅助小模型动作自省) -> L3(事后反思与知识萃取闭环) |
| Phase 32: Cross-Platform Support | P2 | Windows/macOS 双端架构优化。解决核心依赖痛点：重构 `outlook.py` 脱离 COM 绑定、强化 `ui_anchors.py` 跨平台跨感知 fallback，并分离 `sandbox` & `shell` 的 OS 保护边界。 |

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
