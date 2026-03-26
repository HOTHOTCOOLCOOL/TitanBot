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
| Phase 31: Verification Layer | P1 | 三层验证架构 (L1 Rules / L2 Self-Check / L3 External Eval) + Auxiliary Model 动态选型 + Skill `success_criteria` + Harness Necessity Audit |

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

## 🔬 Phase 29 — 论文借鉴增强 (Paper-Inspired)

> 源自 5 篇论文对比分析，按 ROI 排序。完整分析见 `paper_analysis_report.md`。

| 优先级 | ID | 借鉴项 | 来源 | 预计工作量 |
|--------|-----|--------|------|-----------|
| **P0** | P29-1 | Directive Signal → 修正记忆 & Skill 学习 | OpenClaw-RL | 1.5-2 天 |
| **P1** | P29-2 | System Reminders（行为纠偏） | OPENDEV | 半天 |
| **P2** | P29-3 | 离线 Bridging Facts 生成 | IndexRAG | 1-2 天 |
| **P2** | P29-4 | Knowledge Completion（知识补全） | QChunker | 1 天 |
| **P2** | P29-5 | 错误信号 → 自动经验 | OpenClaw-RL | 半天 |
| **P3** | P29-6 | 知识溯源链 | Dual-Tree | 半天 |

> 📌 **专题待讨论**：Per-Workflow 模型路由（认知路由）— 同时关联 Nanobot + 公司 HENRY 项目，将在独立会话中深入讨论。
