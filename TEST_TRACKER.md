# Test Tracker

> **最后更新**: 2026-05-04 (补记 Phase 65 定向自动化确认)

## 当前基线

| 指标 | 值 |
|------|-----|
| Passed | 1324 |
| Failed | 0 |
| Skipped | 1 |
| 耗时 | ~130s |
| 测试文件 | 93 |

## 最近定向自动化验证

| 日期 | 范围 | 结果 | 说明 |
|------|------|------|------|
| 2026-05-04 | Phase 65 Harness + execute_phase Artifact contract | ✅ PASS | `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v` -> `24 passed`。覆盖 `tests/test_harness_cli.py`、`tests/test_auto_reviewer.py`、新增 `tests/test_phase65_execute_phase_contract.py`；Phase 65 两份 manual guide 的核心契约场景现已具备确定性回归证据。 |

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
| Phase 61 | Command Control Tiering (ADR-61), `SENSITIVE`/`DESTRUCTIVE` 分层, RPA 修饰键嗅探, 全工具 `R-DESTRUCTIVE-GUARD` 硬阻断 |

## 最近人工验收

| 日期 | 范围 | 结果 | 说明 |
|------|------|------|------|
| 2026-05-03 | Phase 61 Command Control Tiering | ✅ PASS | 按 `docs/tests/manual_guides/phase_61_manual_test_guide.md` 完成 3 个场景：S1 普通 RPA 中心点击直接放行；S2 `rpa(keys=['win'])` 进入 HITL 且 `Reject` 后终止；S3 `exec("echo test | cmd")` 无审批路径，直接被 L1 拦截。同期出现的 `weixin:start:532 ConnectError` 属外部网络噪音，不计入验收结果。 |

## 缺陷封存 (Phase 33 Retro)

| ID | 描述 | 严重性 | 状态 |
|----|------|--------|------|
| BUG-HITL-1 | `loop.py` L597 `self.config.master_identities` — AttributeError | 🔴 Critical | [x] 已修复 |
| BUG-HITL-2 | `hitl_store.py` `_save()` 非原子写入 | 🟠 Medium | [x] 已修复 |
| DEBT-KB-1 | `match_experience` 阈值过低 (0.4) 且 `no_dense_penalty=1.0` | 🟠 Medium | [x] 已修复 |
| DEBT-KB-2 | `_key_extraction_cache` 为模块级全局状态 | 🟡 Low | [x] 已修复 |
| SEC-BUW-1 | `browser_use_worker` 内层 LLM Agent 不受外层保护 | 🟠 Medium | [x] 已修复 |
