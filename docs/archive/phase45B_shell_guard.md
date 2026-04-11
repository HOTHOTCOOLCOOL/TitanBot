# Phase 45B: R-SHELL-GUARD Tag-Driven L1 拦截 技术归档

**日期**: 2026-04-11
**ADR**: ADR-45B-shell-guard-tag-driven-l1.md

## 技术决策与实施摘要

### 已完成的 6 项决策

1. **IS_HIGH_RISK 修正**: `capability.py` — 从 `DESTRUCTIVE | UNTRUSTED_EXTERNAL | SHELL_EXECUTION` 精简为 `DESTRUCTIVE | UNTRUSTED_EXTERNAL`
2. **evaluate_dynamic_tags 实现**: `shell.py` — ExecTool 覆写动态标签评估，运行时检测高危命令
3. **R-SHELL-GUARD 规则落地**: `verification.py` — `_check_rule_shell_guard()` 同时支持 Tag-Driven 和静态正则回退
4. **_guard_command 分离重构**: `shell.py` — 删除 40 行 deny_patterns 黑名单，保留路径遍历检测
5. **check_rules 签名修复**: `verification.py` — 新增 `registry=`、`config_overrides=` 可选参数
6. **plugin_loader 遗留清除**: `plugin_loader.py` — 无 `get_risk_tier` 代理

### 关键架构变更

- `_SHELL_DYNAMIC_RISK_PATTERNS` (shell.py) 成为 DESTRUCTIVE 命令检测的**单一权威**
- `_DESTRUCTIVE_PATTERNS` (verification.py) 退化为无 registry 时的静态兜底
- `FakeRegistry` 测试桩使用真实 `ExecTool()` 实例以保证端到端标签评估

### 验证结果

- `tests/test_phase31_verification.py`: 60/60 通过
- 冒烟测试: `dir`→NONE, `python -c`→DESTRUCTIVE, `rm -rf /`→DESTRUCTIVE, `curl URL`→DESTRUCTIVE
