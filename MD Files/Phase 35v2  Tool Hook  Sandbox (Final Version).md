# Phase 35v2 — Tool Hook & Sandbox (Final Version)

> **Harness 三阶段审议结果**：经 Planner Draft V1 → Critic 深度批判 → Planner 终稿融合

---

## 核心决策：砍掉 2/3，精准落地 1/3

Critic 阶段暴露了 Draft V1 的三个致命问题：

1. **P35v2-2（LLM 双重确认）就是被移除的 L2 的借尸还魂**
2. **P35v2-1（Hook 机制）为一个消费者搭建完整的 Pub/Sub 总线是过度工程**
3. **P35v2-3（路径沙盒）与已有的 `_SENSITIVE_PATHS` 高度重叠**

> [!CAUTION]
> **L2 历史教训 (L2_VERIFICATION_RETHINK.md)**：
> - 误拒率远高于误放率 → 雪崩效应 → 用户体验灾难
> - 单次误拒 = 浪费 1 轮迭代 + 错误 context 注入 + 主模型被带偏
> - **任何在执行前引入 LLM 判断的机制，都必须满足：< 100ms 延迟 + 黑名单制 + warn-only（不阻断）**
> - 当前条件不成熟，P35v2-2 直接取消

### 最终方案概览

| 原 ID | 原提案 | 最终决策 | 理由 |
|--------|--------|----------|------|
| P35v2-1 | Hook 机制 (Pub/Sub 事件总线) | ❌ **取消** | L1 `_L1_RULES` 列表本身就是 Hook 管线，无需平行宇宙 |
| P35v2-2 | LLM 双重确认 (LLMAuditHook) | ❌ **取消** | 与 L2 移除决策直接冲突，条件不成熟 |
| P35v2-3 | Glob 路径沙盒 | ✅ **精简落地** | 合并入 L1 规则，扩展 `VerificationConfig`，~30 行代码 |
| — | 新增 L1 R11: `filesystem` 写操作路径检查 | ✅ **新增** | 补全 `write_file`/`edit_file` 的路径防护盲区 |

---

## Proposed Changes

### Component 1: Config Schema

#### [MODIFY] [schema.py](file:///d:/Python/nanobot/nanobot/config/schema.py)

在 `VerificationConfig` 中新增一个 `path_deny_patterns` 字段：

```python
class VerificationConfig(Base):
    # ... existing fields ...
    
    # Phase 35v2: Configurable path deny patterns (Glob syntax via fnmatch)
    # These supplement the hardcoded _SENSITIVE_PATHS in verification.py.
    # Users can add project-specific deny rules in config.json.
    # Example: ["*.env", "**/.git/*", "/secrets/*"]
    path_deny_patterns: list[str] = Field(default_factory=list)
```

**设计决策**：
- 使用 deny-list（黑名单）而非 allow-list（白名单），因为 fail-open 比 fail-closed 安全——配置出错时不会锁死所有操作
- 空列表 = 仅使用硬编码的 `_SENSITIVE_PATHS`，零破坏性变更
- Glob 语法用 Python 内置 `fnmatch`，零新依赖

---

### Component 2: Verification Layer L1 规则扩展

#### [MODIFY] [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py)

**变更 1**：扩展 `_check_rule_sensitive_path()` → 支持从 config 读取额外 deny patterns

```python
import fnmatch

def _check_rule_sensitive_path(tool_calls: list[Any], *, extra_deny: list[str] | None = None) -> list[str]:
    """R07: write_file / exec / edit_file must not target sensitive system paths."""
    violations = []
    for tc in tool_calls:
        path_to_check = ""
        if tc.name == "write_file":
            path_to_check = tc.arguments.get("path", "")
        elif tc.name == "edit_file":
            path_to_check = tc.arguments.get("file_path", "")
        elif tc.name == "exec":
            path_to_check = tc.arguments.get("command", "")
        else:
            continue

        path_lower = path_to_check.lower()
        
        # Hardcoded sensitive paths (existing)
        for sensitive in _SENSITIVE_PATHS:
            if sensitive in path_lower:
                violations.append(
                    f"R07: Operation targets a sensitive system path containing '{sensitive}'. "
                    f"This has been blocked for safety."
                )
                break
        
        # Phase 35v2: Configurable deny patterns (Glob)
        if extra_deny:
            for pattern in extra_deny:
                if fnmatch.fnmatch(path_lower, pattern.lower()):
                    violations.append(
                        f"R07: Path matches deny pattern '{pattern}'. "
                        f"This has been blocked by sandbox configuration."
                    )
                    break
    
    return violations
```

**变更 2**：`VerificationLayer.check_rules()` 传递 config 中的 deny patterns

```python
def check_rules(self, tool_calls: list[Any]) -> RuleResult:
    if not self.config.l1_enabled:
        return RuleResult(passed=True)
    
    # Phase 35v2: Read configurable deny patterns
    extra_deny = getattr(self.config, 'path_deny_patterns', None) or None
    
    all_violations: list[str] = []
    for rule_fn in _L1_RULES:
        if rule_fn is _check_rule_sensitive_path:
            violations = rule_fn(tool_calls, extra_deny=extra_deny)
        else:
            violations = rule_fn(tool_calls)
        all_violations.extend(violations)
    # ... rest unchanged ...
```

> [!IMPORTANT]
> **Fail-open 防护**：如果 `path_deny_patterns` 配置有语法错误（如空字符串），`fnmatch.fnmatch()` 不会抛异常，只会返回 False（不匹配）。这确保了配置错误不会导致误拒雪崩。

---

### Component 3: 补全 `edit_file` 的路径检查盲区

当前 `_check_rule_sensitive_path()` 只检查 `write_file` 和 `exec`，但 `edit_file` 工具同样可以修改敏感路径文件。这是一个真实的防护缺口。

上面的代码变更已包含 `edit_file` 的 `file_path` 参数检查。

---

## 被取消项的正式记录

### ❌ P35v2-1: Hook 机制 — 已取消

**Critic 论据（C2, C5）完全成立：**
- `_L1_RULES` 列表本身就是一个顺序执行的 Hook 管线
- 现有消费者只有 L1 确定性规则和 HITL 审批，无需 Pub/Sub
- 新增 `hooks/` 子包只为放一个文件，安全逻辑碎片化

### ❌ P35v2-2: LLM 双重确认 — 已取消

**Critic 论据（C1）一击致命：**
- 与 `L2_VERIFICATION_RETHINK.md` 第272行明确的重新引入条件冲突
- 现有条件不满足（无本地快速小模型 < 100ms）
- 误拒雪崩风险与已移除的 L2 完全一致

**保留的复活条件**（沿用 L2 文档第272行）：
> 任何重新引入都应采用 **黑名单制**（仅审查高危操作）+ **结构化 context brief**（非截断原文）+ **warn-only**（不阻断）的设计

---

## Verification Plan

### Automated Tests

1. 在 `tests/test_phase31_verification.py` 中新增测试：
   - `test_r07_edit_file_sensitive_path` — 验证 `edit_file` 对敏感路径的拦截
   - `test_r07_configurable_deny_patterns` — 验证 Glob deny pattern 匹配
   - `test_r07_empty_deny_patterns_passthrough` — 验证空 deny list 不影响正常操作
   - `test_r07_malformed_pattern_fail_open` — 验证畸形 pattern 不导致误拒

2. 运行全量回归：`python -m pytest tests/ -x -q`

### Manual Verification

- 在 `config.json` 中添加 `"pathDenyPatterns": ["*.env", "**/secrets/*"]` 后启动 Agent
- 让 Agent 尝试 `write_file` 到 `.env` 路径，确认被 L1 拦截
- 让 Agent 正常 `write_file` 到 workspace 内路径，确认不受影响

---

## 改动量预估

| 文件 | 改动行数 | 类型 |
|------|---------|------|
| `config/schema.py` | ~3 行 | 新增字段 |
| `verification.py` | ~20 行 | 扩展现有函数 |
| `test_phase31_verification.py` | ~40 行 | 新增测试 |
| `progress_report.md` | ~5 行 | 更新状态 |
| **总计** | **~70 行** | — |

**零新文件。零新抽象。零新依赖。与 L1 管线完全一致。**
