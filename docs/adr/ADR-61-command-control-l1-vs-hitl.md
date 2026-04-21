# ADR-61: 细分命令管控 — 分离高危执行 (HITL 软拦截) 与毁灭操作 (L1 硬阻断)

**状态**: 已采纳 (Accepted)  
**日期**: 2026-04-19  
**Harness 辩证轮次**: 5 阶辩证 (Sonnet Planner → Opus Critic → Gemini V2 → Gemini Validator → Sonnet Final)  
**关联 ADR**: ADR-45 (CapabilityTag 体系), ADR-45B (R-SHELL-GUARD 落地), ADR-59 (Antigravity 整合)  
**受影响文件**:
- `nanobot/agent/capability.py`
- `nanobot/agent/tools/rpa_executor.py`
- `nanobot/agent/verification.py`

---

## 背景与问题陈述

ADR-45B 已成功建立了 Tag-Driven 的 L1 防线（`R-SHELL-GUARD`）和 HITL 软拦截机制，
但以下三个语义盲区在生产中持续暴露：

1. **`RPAExecutorTool` 完全无分级保护**：`static_tags = MUTATIVE` 一刀切，`hotkey(['ctrl','alt','del'])` 与 `click('Submit')` 享有相同权限。
2. **`DESTRUCTIVE` 标签无法覆盖 Shell 工具以外的工具**：`R-SHELL-GUARD` 有 `SHELL_EXECUTION` 静态标签的硬性前置条件，导致其他工具（如 RPA）即使动态返回 `DESTRUCTIVE`，也不会被 L1 拦截。
3. **"可批准的高危"与"永不批准的毁灭"语义混同**：缺少中间档 `SENSITIVE` 标签，导致 `write_file`/`send_email` 要么无保护，要么需要加 `DESTRUCTIVE`（过激）。

---

## 架构决策

### 决策 1：新增 `SENSITIVE` 标签，重定义 `IS_HIGH_RISK`

```python
# capability.py

SENSITIVE = auto()  # 高危但可获批准的操作（通过 HITL 软拦截路径）
                    # 例如：RPA 系统级热键、用户明确配置的邮件审批

# 组合定义：DESTRUCTIVE 纳入 IS_HIGH_RISK，作为 HITL 兜底线
IS_HIGH_RISK = SENSITIVE | DESTRUCTIVE | UNTRUSTED_EXTERNAL
```

**理由**：
- `SENSITIVE`: 表达"重要，需人类知情"，进入 HITL 审批路径
- `DESTRUCTIVE`: 表达"永不批准"，主要由 L1 `R-DESTRUCTIVE-GUARD` 捕获
- 将 `DESTRUCTIVE` 纳入 `IS_HIGH_RISK`：防止 L1 失效时因无兜底而穿透

**保留约定**：`coordinator.py` 使用 `IS_HIGH_RISK` 的现有行为不变（`spawn` 必须 HITL 审批）。

---

### 决策 2：将 `R-SHELL-GUARD` 泛化为 `R-DESTRUCTIVE-GUARD`

**废弃** `_check_rule_shell_guard` 中 `SHELL_EXECUTION` 的静态标签前置条件。

新规则对**所有工具**一视同仁：只要 `get_effective_tags()` 结果含 `DESTRUCTIVE`，无论工具名称，L1 立即硬阻断。

**关键保留**：
- 无 registry 时的正则 fallback（`exec` 工具的保底防线）
- `try-except` 兜底时必须打印 `logger.error`（禁止静默降级掩盖 Bug）

---

### 决策 3：为 `RPAExecutorTool` 实现 `evaluate_dynamic_tags()`（修饰键嗅探策略）

**废弃** 热键黑名单枚举（脆弱，组合爆炸，别名可绕过）。  
**采用** 修饰键语义嗅探：

| 条件 | 返回标签 | 路由结果 |
|---|---|---|
| `hotkey/press` 包含 `win/command` 系统修饰键 | `SENSITIVE` | HITL 软拦截 |
| `hotkey/press` 包含 `alt+f4` | `SENSITIVE` | HITL 软拦截 |
| `type` 文本超过 800 字符 | `SENSITIVE` | HITL 软拦截 |
| 其他所有 RPA 动作 | `NONE` | 直接执行（叠加 `static_tags = MUTATIVE`） |

---

### 决策 4：业务连续性保护（Cron/Worker 不受影响）

**拒绝**对 `send_email`、`write_file` 施加全局 `SENSITIVE` 标签。

**理由**：Worker/Cron 子进程没有 HITL 审批路径（`hitl.py:68-77` 硬阻断），
全局升级会立即摧毁所有定时自动化任务（ADR-44/ADR-53 核心用例）。

**企业级扩展口**：需要邮件审批的场景，通过 `config.yaml` 中的 `capability_overrides` 注入 `SENSITIVE` 标签即可，零代码改动。

---

## 验证计划

| 场景 | 工具调用 | effective_tags | 预期结果 |
|---|---|---|---|
| 普通点击 | `rpa(action=click, ui_name=Submit)` | `MUTATIVE` | ✅ 直接执行 |
| 系统热键 | `rpa(action=hotkey, keys=[ctrl,alt,del])` | `MUTATIVE\|SENSITIVE` | ⚠️ HITL 软拦截 |
| Win 键操作 | `rpa(action=hotkey, keys=[win,r])` | `MUTATIVE\|SENSITIVE` | ⚠️ HITL 软拦截 |
| 超长输入 | `rpa(action=type, text=...>800字)` | `MUTATIVE\|SENSITIVE` | ⚠️ HITL 软拦截 |
| Python 脚本执行 | `exec(command=python script.py)` | `SHELL_EXECUTION\|MUTATIVE\|DESTRUCTIVE` | 🚫 L1 硬阻断 |
| Cron 发邮件 | `outlook(action=send_email,...)` | `SYS_COMMUNICATION\|MUTATIVE` | ✅ 业务畅通 |
| 外部 MCP 插件 | `plugin_tool(...)` | `UNTRUSTED_EXTERNAL\|...` | ⚠️ HITL 软拦截（行为不变） |
| evaluate_dynamic_tags 异常 | 任意工具 | fallback to static_tags | 🟡 logger.error 可见，继续判断 |

---

## 参考

- `ADR-45-dynamic-sandbox-capability-tags.md` — CapabilityTag 体系基础
- `ADR-45B-shell-guard-tag-driven-l1.md` — R-SHELL-GUARD 前身决策
- `nanobot/agent/capability.py` — 标签枚举定义位置
- `nanobot/agent/verification.py` — `_check_rule_destructive_guard` 实现位置
- `nanobot/agent/tools/rpa_executor.py` — `evaluate_dynamic_tags` 实现位置
