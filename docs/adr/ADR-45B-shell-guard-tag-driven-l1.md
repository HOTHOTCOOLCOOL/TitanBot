# ADR-45B: R-SHELL-GUARD — Tag-Driven L1 高危 Shell 命令拦截

**状态**: 已采纳 (Accepted)  
**日期**: 2026-04-11  
**关联 ADR**: ADR-45-dynamic-sandbox-capability-tags.md (Phase 45B 实施补充)  
**Harness 辩证轮次**: 5 阶 (Gemini Planner → Opus Critic → Sonnet V2 → Gemini Validator → Sonnet Final)  
**受影响文件**:  
- `nanobot/agent/capability.py`  
- `nanobot/agent/tools/shell.py`  
- `nanobot/agent/verification.py`  
- `nanobot/plugin_loader.py`

---

## 背景与问题陈述

ADR-45 中已建立 `CapabilityTag` 基础设施，但 Phase 45B 的核心收口工作（L1 规则 Tag-Driven 化）存在以下实施盲区，在 Phase 45 用例 A3 中被曝光：

1. **`check_rules` 签名断裂**：调用方 (`loop.py:682`, `verification_mw.py:39`) 已传入 `registry=` 和 `config_overrides=` 参数，但方法签名不接受，导致所有 L1 规则实际上在运行时抛 `TypeError` 并静默失效。

2. **`ExecTool.evaluate_dynamic_tags` 缺失**：方法未被覆写，默认返回 `CapabilityTag.NONE`，导致 `DESTRUCTIVE` 标签永远不会出现在 effective tags 中，整条 Tag-Driven 防线无信号来源。

3. **`IS_HIGH_RISK` 定义过宽**：包含 `SHELL_EXECUTION` 导致所有 exec 命令（含无害的 `dir`）触发 HITL 审批，用户体验灾难。

4. **双权威冲突**：`ExecTool._guard_command` 的命令黑名单与 `verification.py` 的 `_DESTRUCTIVE_PATTERNS` 重叠且不同步，违反 ADR-45 "单一权威" 原则。

5. **`R-SHELL-GUARD` 规则未落地**：测试文件 `test_phase31_verification.py` 中大量引用此规则代号，但 `verification.py` 中没有对应实现，测试体系与实现严重撕裂。

---

## 架构决策

### 决策 1：修正 `IS_HIGH_RISK` 组合定义

```python
# 修改前（过宽，所有 exec 触发 HITL）
IS_HIGH_RISK = DESTRUCTIVE | UNTRUSTED_EXTERNAL | SHELL_EXECUTION

# 修改后（精确，只有动态评估为 DESTRUCTIVE 的命令才高危）
IS_HIGH_RISK = DESTRUCTIVE | UNTRUSTED_EXTERNAL
```

**理由**：`SHELL_EXECUTION` 是能力声明（"这个工具能执行 shell"），不是风险判定。风险由 `evaluate_dynamic_tags()` 运行时检测后通过 `DESTRUCTIVE` 标签表达。

---

### 决策 2：实现 `ExecTool.evaluate_dynamic_tags`

在 `shell.py` 模块顶层定义预编译常量 `_SHELL_DYNAMIC_RISK_PATTERNS`，覆盖以下高危模式：

| 模式 | 说明 |
|:---|:---|
| `python\d*\s+-c` | python/python3/py -c 解释器内联执行 |
| `node\s+-e` | Node.js 内联执行 |
| `ruby\s+-e` / `perl\s+-e` | Ruby/Perl 内联执行 |
| `\.py\b` / `\.sh\b` / `\.ps1\b` | 脚本文件执行 |
| `eval\b` | shell/python eval 原语 |
| `__import__` | Python 导入绕过 |
| `base64.*decode` | base64 反序列化攻击 |
| `\|\s*(bash\|sh\|cmd\|powershell\|pwsh)` | 管道注入 |

命中任一模式 → 返回 `CapabilityTag.DESTRUCTIVE`，触发下游 R-SHELL-GUARD 硬阻断。

---

### 决策 3：实现 `R-SHELL-GUARD` L1 规则

```
_check_rule_shell_guard(tool_calls, *, registry, config_overrides)
```

**责任边界**（与 HITL 的区分）：

| 层级 | 触发条件 | 结果 |
|:---:|:---|:---|
| R-SHELL-GUARD (L1) | `effective_tags & DESTRUCTIVE` | 硬阻断，无审批路径 |
| HITLMiddleware | `effective_tags & IS_HIGH_RISK` (= DESTRUCTIVE \| UNTRUSTED_EXTERNAL) | 软拦截，等待人工授权 |

**降级兜底**：当 `registry` 为 `None` 时（如部分单元测试），回退到 `_DESTRUCTIVE_PATTERNS` 静态正则扫描，确保没有注册表环境下也能拦截 `exec` 工具的已知危险命令。

---

### 决策 4：`_guard_command` 分离重构

**命令黑名单**（`deny_patterns` 循环）→ **删除**，职责移交给 L1 `R-SHELL-GUARD`。

**保留**：路径遍历检测（`../`、`..\`）和工作区范围约束。这是执行时物理沙箱，语义不同于 L1 语义拦截，属于纵深防御的最后一道保险。

---

### 决策 5：修复 `check_rules` 签名

```python
def check_rules(
    self,
    tool_calls: list[Any],
    messages: list[dict] | None = None,
    *,
    registry: Any | None = None,
    config_overrides: dict | None = None,
) -> RuleResult:
```

新参数为可选 kwargs，完全向下兼容现有调用方，同时允许 Tag-Driven 规则接收注册表上下文。

---

### 决策 6：清除 `plugin_loader.py` 遗留 `get_risk_tier` 代理

`_ExternalTaggedTool.get_risk_tier()` 引用已废弃的 `RiskTier` API。删除此代理方法，统一使用 `get_effective_tags()` 作为唯一标签查询接口。

---

## 验证计划

| 场景 | 命令 | effective_tags | 预期结果 |
|:---|:---|:---|:---|
| 普通查询 | `dir` | `SHELL_EXECUTION \| MUTATIVE` | HITL 软拦截（非 IS_HIGH_RISK，实际放行，除非有 UNTRUSTED_EXTERNAL） |
| 高危注入 | `python -c 'import os; os.system(...)'` | `SHELL_EXECUTION \| MUTATIVE \| DESTRUCTIVE` | R-SHELL-GUARD 硬阻断 |
| 脚本执行 | `python script.py` | `SHELL_EXECUTION \| MUTATIVE \| DESTRUCTIVE` | R-SHELL-GUARD 硬阻断 |
| 管道攻击 | `echo hacked \| bash` | `SHELL_EXECUTION \| MUTATIVE \| DESTRUCTIVE` | R-SHELL-GUARD 硬阻断 |
| 外部插件 | 任意 plugin 工具 | `UNTRUSTED_EXTERNAL \| MUTATIVE \| ...` | HITL 软拦截（IS_HIGH_RISK 命中） |

**运行现有回归测试**：`tests/test_phase31_verification.py` 中的 `R-SHELL-GUARD` 断言现在应能通过（当使用 registry mock 时）。

---

## 参考

- `ADR-45-dynamic-sandbox-capability-tags.md` — 父级 ADR，定义 CapabilityTag 体系
- `nanobot/agent/verification.py` — L1 规则引擎宿主，`_check_rule_shell_guard` 实现位置
- `nanobot/agent/tools/shell.py` — `ExecTool.evaluate_dynamic_tags` 实现位置
- `nanobot/agent/capability.py` — `IS_HIGH_RISK` 定义修正位置
- `docs/phase_45_comprehensive_test_guide.md` — 用例 A3 验证路径
