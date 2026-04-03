# Test Tracker

> **最后更新**: 2026-03-31 (Phase 33 回顾审计完成后)

## 当前基线

| 指标 | 值 |
|------|-----|
| Passed | 1271 |
| Failed | 0 |
| Skipped | 1 |
| 耗时 | ~119s |
| 测试文件 | 91 |

## 架构变更

| Phase | 变更概要 |
|-------|---------|
| Phase 29 | 论文借鉴增强 (Directive Signal, System Reminders, Bridging Facts, Knowledge Completion) |
| Phase 30 | 弱模型安全护栏 (Pre-validation, Circuit Breaker, 重复工具调用检测) |
| Phase 31 | 漏斗验证层引入 (L0 上下文增强, L1 刚性拦截 R01-R05, L3 事后审计) |
| Phase 32 | L2 移除, L1 扩展至 R09, Smart HITL 审批框架 (ApprovalStore 通配符匹配) |
| Phase 33 | Browser-RPA 降级链路优化 (`ensure_visible` 生命周期, 坐标漂移修复, `[FALLBACK_RPA]` 信号协议, CDP 代码清理) |

## 待修复缺陷

| ID | 描述 | 严重性 | 状态 |
|----|------|--------|------|
| BUG-HITL-1 | `loop.py` L597 `self.config.master_identities` — AttributeError，远程 HITL 广播必崩 | 🔴 Critical | ✅ 已修复 |
| BUG-HITL-2 | `hitl_store.py` `_save()` 非原子写入，进程崩溃可导致 `approvals.json` 损坏 | 🟠 Medium | ✅ 已修复 |
| DEBT-KB-1 | `match_experience` 阈值过低 (0.4) 且 `no_dense_penalty=1.0`，小语料库下噪音注入 | 🟠 Medium | ✅ 已修复 |
| DEBT-KB-2 | `_key_extraction_cache` 为模块级全局状态，多租户场景存在数据泄露风险 | 🟡 Low | ✅ 已修复 |
| SEC-BUW-1 | `browser_use_worker` 内层 LLM Agent 不受外层 L1/HITL 管线保护 | 🟠 Medium | ✅ 已修复 (Context Sandwiching + Forced-HITL) |
