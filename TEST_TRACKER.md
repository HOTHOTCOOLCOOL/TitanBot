# Test Tracker

> **最后更新**: 2026-04-11 (完成 Phase 44 & 45 全量回归与操作演练)

## 当前基线

| 指标 | 值 |
|------|-----|
| Passed | 1324 |
| Failed | 0 |
| Skipped | 1 |
| 耗时 | ~130s |
| 测试文件 | 93 |

## 架构变更

| Phase | 变更概要 |
|-------|---------|
| Phase 29 | 论文借鉴增强 (Directive Signal, System Reminders, Bridging Facts, Knowledge Completion) |
| Phase 30 | 弱模型安全护栏 (Pre-validation, Circuit Breaker, 重复工具调用检测) |
| Phase 31 | 漏斗验证层引入 (L0 上下文增强, L1 刚性拦截 R01-R05, L3 事后审计) |
| Phase 32 | L2 移除, L1 扩展至 R09, Smart HITL 审批框架 (ApprovalStore 通配符匹配) |
| Phase 33 | Browser-RPA 降级链路优化 (`ensure_visible` 生命周期, 坐标漂移修复, `[FALLBACK_RPA]` 信号协议, CDP 代码清理) |
| Phase 34 | KG 检索增强 (Semantic Anchor Grouping, Coverage Penalty, Schema Relaxation) |
| Phase 40 | 稳定性基石与可靠性增强 (工具结果截断, Session快照隔离, 动态Token裁剪, 轻量断点续传/Crash Recovery, 滚动.bak备份) |
| Phase 44 | Cron 重试引擎加固、幻觉防线 (ADR-44), SSRS 兜底防线, 副作用重试隔离 |
| Phase 45 | 动态沙箱能力标签 (ADR-45), R-SHELL-GUARD L1 高危 Shell 拦截 (ADR-45B), Worker IPC 安全隔离 |

## 缺陷封存 (Phase 33 Retro)

| ID | 描述 | 严重性 | 状态 |
|----|------|--------|------|
| BUG-HITL-1 | `loop.py` L597 `self.config.master_identities` — AttributeError | 🔴 Critical | [x] 已修复 |
| BUG-HITL-2 | `hitl_store.py` `_save()` 非原子写入 | 🟠 Medium | [x] 已修复 |
| DEBT-KB-1 | `match_experience` 阈值过低 (0.4) 且 `no_dense_penalty=1.0` | 🟠 Medium | [x] 已修复 |
| DEBT-KB-2 | `_key_extraction_cache` 为模块级全局状态 | 🟡 Low | [x] 已修复 |
| SEC-BUW-1 | `browser_use_worker` 内层 LLM Agent 不受外层保护 | 🟠 Medium | [x] 已修复 |
