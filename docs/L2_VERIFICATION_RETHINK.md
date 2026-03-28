# L2 Verification Layer: 架构反思与重设计

> **背景**: 2026-03-27 飞书回复 bug 诊断后的系统性反思。
> **状态**: 待讨论，需在新会话中做出决策。

---

## 一、问题全景

### 实际发生的事故

| 日期 | 现象 | 根因 |
|------|------|------|
| Phase 31 初版 | L2 拒绝合法 tool call（缺失对话上下文） | L2 prompt 只截断 2000 chars |
| Phase 31 修正 | dashboard 回复丢失 | L2 + channel routing 交叉 |
| 2026-03-27 | Feishu 消息完全无回复，10 分钟超时 | L2 反复拒绝 `message()` x10+ |

### 共性模式

所有事故的根因都指向同一个结构性矛盾：

> **一个 100 max_tokens、零温度的 mini 模型，被要求对主模型的决策做出高置信度的 YES/NO 判断。但这个判断所需的信息量（完整上下文 + agent 架构语义 + 多轮 workflow 逻辑）远超小模型能处理的范围。**

---

## 二、L2 的设计初衷 vs 现实表现

### 设计初衷
- 在 tool 执行前，用廉价模型做一次 "sanity check"
- 拦截明显错误的 tool call（参数错、目标错、逻辑错）
- 作为 L1（确定性规则）和 HITL（人工审批）之间的中间层

### 现实表现
- **误拒率远高于误放率**：实际生产中，L2 拦截的绝大多数是正确操作
- **雪崩效应**：一次误拒 → 错误信息注入 context → 主模型被带偏 → 更多误拒 → 直到迭代耗尽
- **延迟成本**：每次 L2 调用 1.5-7 秒，10 次误拒 = 30-70 秒纯耗时
- **白名单膨胀**：通过不断加白名单来绕开 L2，实质上是在承认它不可靠
- **上下文不足**：L2 只看到截断的 request + tool call summary，无法理解多轮 workflow

### 成本-收益不对等

```
误拒 (False Reject):
  → 浪费 1 轮迭代 + 注入错误 context
  → 可能导致完全无回复（用户体验灾难）
  → 成本：极高

误放 (False Accept):
  → 最多一个不理想的 tool call
  → 用户可事后纠正
  → 成本：低-中
```

对于 assistant 类 agent（非自动驾驶/金融交易），**误拒的代价远大于误放**。

---

## 三、可选方案

### 方案 A：Warn-and-Proceed（告警但不阻断）

**改动**：L2 critique 只写入日志/dashboard 观测，不注入回 context、不阻断执行。

```python
# 当前（阻断式）
if l2_critique:
    for tool_call in response.tool_calls:
        messages = self.context.add_tool_result(
            messages, tool_call.id, tool_call.name,
            f"Error: {l2_critique}"
        )
    continue  # ← 整轮作废

# 方案 A（观测式）
if l2_critique:
    logger.warning(f"L2 advisory: {l2_critique}")
    # 不注入 context，不 continue — 正常执行
```

**优点**：
- 改动最小（约 5 行代码）
- 保留 L2 的观测价值（可用于后续 L3 学习）
- 消除误拒雪崩

**缺点**：
- L2 完全失去拦截能力，等同于关闭
- 如果未来遇到真正需要预拦截的场景，又得改回来

**适用场景**：作为紧急止血方案，或者作为 A/B 测试基线。

---

### 方案 B：黑名单制（只审查高危操作）

**改动**：反转白名单逻辑，变为只对特定高危工具做 L2 检查。

```python
# 需要 L2 审查的高危工具+操作
_L2_HIGH_RISK_CHECKS = {
    "exec": None,              # shell 命令 — 总是审查
    "outlook": ["send_email"], # 外发邮件 — 审查
    # 其他所有工具 — 自动放行
}

needs_llm_check = False
for tc in tool_calls:
    if tc.name in _L2_HIGH_RISK_CHECKS:
        allowed_actions = _L2_HIGH_RISK_CHECKS[tc.name]
        if allowed_actions is None:  # 整个工具都需审查
            needs_llm_check = True
            break
        action = tc.arguments.get("action", "")
        if action in allowed_actions:
            needs_llm_check = True
            break
```

**优点**：
- 保留了对 shell 命令和外发邮件的预审（真正有价值的场景）
- 大幅减少 L2 调用频率和延迟
- 不会误拦 `message`、`read_file`、`attachment_analyzer` 等安全工具

**缺点**：
- 仍然依赖小模型判断（对 `exec` 的审查质量存疑）
- 需要手动维护黑名单

**我的评估**：比方案 A 更精准，但没有解决"小模型是否胜任"的根本问题。

---

### 方案 C：删除 L2，强化 L1 + L3

**改动**：移除 L2 层，将安全能力重新分配给 L1（确定性拦截）和 L3（事后学习）。

```
L0 (Context Enrichment)  → 保留不变
L1 (Rigid Rules)          → 扩展规则集，覆盖更多场景
L2 (Small-model check)    → 删除
L3 (Post-reflection)      → 增强，吸收 L2 的观测职能
HITL (Human approval)     → 保留，覆盖 L2 原本想拦截的高危操作
```

**L1 扩展方向**：
- R05: `exec` 命令长度/复杂度上限（防止注入）
- R06: `outlook send_email` 附件大小限制
- R07: `write_file` 敏感路径保护（system32 等）
- R08: 单轮 tool call 数量上限

**L3 增强方向**：
- 如果执行后发现 tool call 有问题，记录为负面经验
- 下次遇到类似请求，L0 通过 Experience Bank 注入警告

**优点**：
- 消除小模型判断的不可靠性
- 零额外延迟
- L1 规则是确定性的，可测试、可审计
- L3 学习是渐进式的，越用越聪明
- HITL 覆盖了真正需要人工判断的高危操作

**缺点**：
- 失去 "预执行审计" 这一层
- 需要投入时间扩展 L1 规则集
- 新型威胁（不在 L1 规则中的）只能靠 L3 事后学习

**我的评估**：最干净的方案，但需要对 L1 规则进行一次系统性扩展。

---

### 方案 D：L2 改为事后审计

**改动**：保留 L2 小模型，但从 pre-execution gate 改为 post-execution audit。

```python
# 执行 tool call 后
results = await asyncio.gather(...)

# 用小模型审计执行结果
audit = await verification.audit_results(tool_calls, results, request_text)
if audit.is_suspicious:
    logger.warning(f"L2 post-audit: {audit.concern}")
    # 可选：通知用户、记录到 L3
```

**优点**：
- 不阻断执行流
- 小模型看到执行结果后判断更准确
- 可与 L3 学习整合

**缺点**：
- 如果操作已经造成损害（如发了错误邮件），事后审计无法撤销
- 增加实现复杂度

**我的评估**：对于 `exec` 和 `send_email` 这种不可逆操作，事后审计价值有限。

---

## 四、决策矩阵

| 维度 | A: Warn | B: 黑名单 | C: 删除L2 | D: 事后审计 |
|------|---------|-----------|-----------|------------|
| 改动量 | 最小 | 小 | 中 | 中 |
| 消除误拒 | ✅ 完全 | ✅ 大部分 | ✅ 完全 | ✅ 完全 |
| 保留拦截力 | ❌ | ⚠️ 部分 | ❌ (靠L1+HITL) | ❌ |
| 延迟影响 | 无变化* | 大幅减少 | 零 | 无变化* |
| 架构清晰度 | ⚠️ 鸡肋 | ⚠️ 中 | ✅ 最清晰 | ⚠️ 复杂 |
| 长期可维护性 | ❌ 低 | ⚠️ 中 | ✅ 高 | ⚠️ 中 |

*方案 A/D 虽然不阻断，但仍有 L2 LLM 调用的延迟开销。

---

## 五、我的建议

**首选方案 C（删除 L2，强化 L1 + L3）**，理由：

1. L1 确定性规则已经在有效拦截高危操作（已验证 `rm -rf`、`format`、`del /f` 等）
2. HITL 机制覆盖了 `exec`、`send_email` 等真正需要人工判断的操作
3. L3 事后学习在正常积累成功模式
4. L2 在这三层之间实际上是 **负资产**——它消耗了资源、增加了延迟，但阻止的主要是正确操作

如果对 "直接删除" 有顾虑，可以先用 **方案 A 作为过渡**（1 行代码改动），观察一周的日志确认没有真正需要 L2 拦截的场景，然后再彻底删除。

---

## 六、待讨论的问题

1. **是否需要对 L1 做一次规则扩展？** 如果选方案 C，L1 应该覆盖哪些新场景？
2. **HITL 的覆盖范围是否足够？** 当前只覆盖 `MUTATE_EXTERNAL` 以上的操作，是否需要调整？
3. **L2 是否有任何真正拦截了正确威胁的案例？** 应该回溯日志确认。
4. **小模型在 agent 系统中的正确定位是什么？** L2 的失败是否意味着 "用小模型审计大模型" 这个范式本身就有问题？

---

## 七、相关文件

| 文件 | 说明 |
|------|------|
| [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py) | L0-L3 实现 |
| [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py) | Agent 主循环，L2 集成点 |
| [base.py](file:///d:/Python/nanobot/nanobot/agent/tools/base.py) | `RiskTier` 定义 |
| [hitl_store.py](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py) | HITL 审批持久化 |
| [test_phase31_verification.py](file:///d:/Python/nanobot/tests/test_phase31_verification.py) | 验证层测试（46 tests） |

---

## 八、最终决策（2026-03-27）

> **状态**: ✅ 已决策，待执行

### 决策结论

**移除 L2，增强 L1 + L3。** 验证管线从 L0→L1→L2→L3 缩减为 L0→L1→L3。

### 核心判断依据

1. **L2 的问题是工程问题，不是范式问题。** "用小模型审计大模型"的范式在信息充足且任务明确时是有效的（参考 Anthropic Evaluator），但 L2 的实现条件不成熟：2000 字符截断上下文 + 开放式判断 = 必然高误拒率。
2. **误拒的雪崩效应使 L2 成为负资产。** 一次误拒注入错误 context → 主模型被带偏 → 更多误拒 → 用户体验灾难（Feishu 10 分钟无回复事故）。
3. **L1 确定性规则 + HITL 已覆盖高危操作。** L2 想拦截的场景，要么可以用正则规则（L1）捕获，要么需要人工判断（HITL）。L2 夹在中间无法可靠地做到任何一种。
4. **L3 可以吸收 L2 的观测价值。** 事后审计 + 经验萃取 → L0 注入，形成闭环。事后审计的信息量更充分、判断成本更低、错误代价可忽略。

### 具体执行方案

| 动作 | 描述 |
|------|------|
| **移除 L2** | 从 `verification.py`、`loop.py`、`schema.py`、测试中彻底删除 |
| **扩展 L1** | 新增 R05 (exec 长度限制)、R07 (敏感路径保护)、R08 (单轮 tool call 数量上限)、R09 (网络外泄检测) |
| **增强 L3** | 新增 anti-pattern 检测（**初期 log-only**，不自动写入 Experience Bank，待人工 review 确认检测质量后再启用自动记录） |

### 保留的设计原则

- Harness Design 理念本身没有被否定——L2 的移除是因为当前工程条件的限制，而非范式错误
- 如果未来引入本地部署的快速小模型（<100ms 延迟），可以重新评估 LLM 审查的可行性
- 任何重新引入都应采用 **黑名单制**（仅审查高危操作）+ **结构化 context brief**（非截断原文）+ **warn-only**（不阻断）的设计
