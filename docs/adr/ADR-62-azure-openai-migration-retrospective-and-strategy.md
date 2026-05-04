# ADR-62: Azure OpenAI 迁移复盘与未来安全策略

**状态**: 已采纳 (Accepted)
**日期**: 2026-04-19
**验收状态**: Phase 62 已于 2026-05-03 完成人工与探针验证，通过
**Harness 辩证轮次**: 5 阶辩证 (Sonnet Planner → Opus Critic → Gemini Pro High → Gemini Pro Low → Sonnet Final)
**关联 ADR**: ADR-45B (R-SHELL-GUARD), ADR-59 (Antigravity 整合), ADR-60 (LiteLLM 网关), ADR-61 (命令控制分层)
**受影响文件**:
- `nanobot/session/manager.py` (或 Session 持久化层)
- `nanobot/agent/context.py`
- `nanobot/agent/state_handler.py`
- `nanobot/agent/middleware/*.py`
- `nanobot/providers/litellm_provider.py` (Provider 层)
- `nanobot/cron/service.py`
- `tests/adversarial/` (新建目录)

---

## 背景与问题陈述

从 Volcengine/旧版代理切换至 Azure OpenAI（企业级模型）的迁移，在两天内集中引爆了大量在旧模型"宽容环境"下被掩盖的潜伏 Bug。  
本 ADR 从根因维度厘清这批 Bug 的架构本质，并以 Harness 5 阶辩证工作流的完整碰撞结论为基准，定义进一步的防御体系演进路径。

---

## 1. 迁移爆发 Bug 的根因分层

迁移期暴露的 Bug 并非偶然，而是分属三个完全独立的缺陷维度：

| 维度 | 典型症状 | 根因 |
|---|---|---|
| **API 契约层** | `content: None → ""` 导致 400 Bad Request | 旧模型对非标 schema 容忍，Azure 强制按 OpenAI 规范校验 |
| **提示词语义层** | `[System: APPROVED]` 等被视为"恶意注入" | 对弱模型的强制引导词，在企业安全模型面前被识别为越权注入 |
| **代码质量层** | `import asyncio` 缺失 等低级命名空间错误 | 聪明模型会触达旧模型从未走到的极端代码分支，引爆潜伏炸弹 |

**关键洞察**：这三类缺陷的共同守门员是——**过度依赖旧模型的宽容性作为隐性测试基准**。重构的核心不是修复症状，而是建立不依赖模型宽容性的防御测试与协议体系。

---

## 2. 架构决策

### 决策 1：Schema 全链路 Null 合规（P0）

**问题**：经 Opus 红方代码审计，Schema 修复不能仅修改入口（`manager.py`），必须追踪完整链路：

```
Session.add_message() → get_history() → _trim_history() → build_messages() → Provider 序列化 → API Payload
```

**规范约定**：
- 所有携带 `tool_calls` 的 assistant 消息，`content` 字段序列化时**必须为 `None`（JSON `null`）或完全省略**
- **禁止**任何中间层对 `None` 做隐式的 `or ""` 转换
- 该约定以代码注释形式锚定至 `Session.add_message()` 方法签名处

**验证**：构造完整的 Tool Call → Tool Result round-trip 单元测试，断言 API Payload 中 `content` 字段的合规性。

---

### 决策 2：Worker/Cron 内容安全熔断（P0）

**问题（Opus C7 — 致命盲区）**：Worker/Cron 子进程无 HITL 路径，若触发 Azure 内容过滤，直接崩溃且无人值守。

**解决方案 — Worker Graceful Pause**：

在 Provider 底层通信层新增 `AzureContentFilterException` 分类捕获：

```python
# nanobot/providers/litellm_provider.py
class AzureContentFilterException(ProviderExecutionError):
    """Azure OpenAI 内容安全过滤触发 (HTTP 400 content_filter reason)."""
    def __init__(self, blocked_prompt_snippet: str):
        super().__init__(f"Azure content filter blocked request: {blocked_prompt_snippet[:200]}")
        self.blocked_snippet = blocked_prompt_snippet
```

若该异常在 Worker/Cron 上下文触发（`chat_id.startswith("worker:")` 或 `cron_service` 任务池中）：
1. **挂起**该 Worker 的任务队列（不崩溃，不重试）
2. 向所有 `config.master_identities` **广播安全阻断警报**，包含：触发任务 ID、被屏蔽的 prompt 摘要、错误类型
3. 记录结构化日志 `logger.error(...)` 便于事后审计

**决策放弃项**：不在 Worker 内自动降级或自动修改 prompt 重试，因为这等于自动绕过安全过滤。

---

### 决策 3：Role 净化与零信任通信（P1）

**问题（Opus C8 — 高危）**：`state_handler.py:362` 将系统控制流以 `user` 角色伪装注入：

```python
# 危险模式 — 已被废弃
session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
```

在 Azure 的安全审计视角下，`user` 角色消息享有高信任度。将系统事件伪装为 `user` 消息属于隐性权限升级，且 `msg.sender_id` 若可被外部控制则存在注入攻击面。

**解决方案**：

| 原模式 | 替换为 |
|---|---|
| `add_message("user", "[System: sender_id] ...")` | 注入 `ContextBuilder` 的 System Reminder（仅当前轮有效） |
| 跨子代理通报 | 通过虚拟 `tool_call_id` 作为 `tool` 角色结果回传主脑 |
| 拒绝分支强制提示（L299） | 降维为客观事实陈述，移除 `REJECTED/INTERRUPTED` 等强制语气词 |

**编码规约（同步写入 ARCHITECTURE.md #25）**：  
> 禁止任何非 API 模型驱动的代码逻辑主动使用 `role: "user"` 进行内部状态记录或系统事件通报。

---

### 决策 4：Planning Gate V1 实现（精确定义）（P1）

**问题（Opus C1 批判背景）**：Draft V1 中"全局许可令牌"的描述存在与 L1 防火墙矛盾的语义漏洞。

**最终定义（L1 物理隔离，HITL 批量注册）**：

```
触发条件：`write_artifact` 工具被调用 → 输出合规 implementation_plan.md
              ↓
`write_artifact` 已标记 IS_HIGH_RISK → 经 HITLMiddleware 挂起 → 用户 Approve
              ↓
解析 plan.md 中声明的工具类型列表
              ↓
在 ApprovalStore 中批量注册 (tool_name, action_type) 免检凭证
（时效：当前 session_key，Session 结束自动失效）
              ↓
后续步骤中 HITL 层查询 ApprovalStore → 凭证命中 → 静默执行
（L1 check_rules() 全程无感知，时序不受影响）
```

**铁律**：
- ✅ L1 `_DESTRUCTIVE_PATTERNS` 正则群永久保留，Planning Gate 不接触、不感知、不影响
- ✅ 若模型产生了与 plan 不符的 `DESTRUCTIVE` 工具调用，L1 仍铁面拦截
- ✅ 凭证范围绑定至 plan 中声明的具体 `(tool_name, action_type)` 对，不是全局豁免

---

### 决策 5：永久废弃 L1 的 LLM 旁路嗅探（ADR 层面封禁）

**问题（Opus C3 — 致命，全盘接受）**：ADR-62 原始草稿建议"废弃 Regex，让强模型作为 L1 验证器"。

**该提案被 Harness 5 阶辩证永久否决，理由如下**：

1. **延迟灾难**：LLM 调用最低 200ms 延迟 vs Regex 亚微秒级，在 L1 热路径上不可接受
2. **确定性倒退**：以概率性黑箱取代可形式化证明的白箱，在安全关键路径上不可接受
3. **递归信任悖论**：用 LLM 验证 LLM 输出，无穷递归
4. **违反 ARCHITECTURE.md**：`verification.py` 明确要求 "No new external dependencies"

**决策**：`verification.py` 的 `_DESTRUCTIVE_PATTERNS` 及 `_check_rule_destructive_guard` 以纯 Python 代码形式长期固化。后续安全增强只以追加新规则的形式进行，禁止引入任何基于 LLM 的动态评估器至 L1 层。

---

### 决策 6：混沌注入测试套件替代 MockShim（P2）

**问题（Opus C4）**：MockAzureOAIShim 是对 Azure 行为假设的模拟，永远滞后于上游实际行为，属于无效测试。

**解决方案 — Chaos Interceptor（混沌截断器）**：

```python
# tests/adversarial/chaos_interceptor.py
# 仅在 NANOBOT_CHAOS_TEST=1 时激活（环境变量门控，防止泄漏至生产）

class ChaosInterceptor:
    """
    装饰 Provider.chat() 的请求/响应链路，随机注入:
    - truncate(170): 将 800 字响应强行截断至 170 字
    - content_filter_400(): 植入虚拟 Azure HTTP 400 content_filter 错误
    - malformed_tool_call(): 返回缺失 'id' 字段的 tool_calls 结构
    
    测试目标：验证框架在外部异常时的恢复能力，而非识别特定错误模式。
    """
    CHAOS_PROBABILITY = 0.10  # 10% 概率触发
```

**测试目录结构**：
```
tests/adversarial/
  chaos_interceptor.py         ← 混沌截断器核心
  test_azure_schema_compliance.py    ← Schema 合规回归
  test_content_filter_recovery.py    ← 内容安全恢复
  test_worker_graceful_pause.py      ← Worker 熔断验证
  test_planning_gate_e2e.py          ← Planning Gate 端到端
```

---

## 3. 安全策略核心辩证：模型越聪明，管控越放松？

> **用户诉求**："针对模型能力增强，是否适当放宽 HITL，否则显得系统很笨？"

**结论：坚决不放宽底层 L1/L2 管控门槛，但强烈建议"升维管控体验"。**

- **L1 防火墙（纯 Python 正则）**：永久固化，不受模型能力影响。一个系统的智能程度（Reasoning）与破坏力潜力（Blast Radius）正相关。GPT-5.4 产生幻觉时写出的后门代码比旧模型更具破坏性。
- **用户体验的感知障碍**：系统"显得笨"，是因为在执行中段被反复打断（每步单独 HITL），而非 HITL 本身的问题。
- **进阶解法（Planning Gate）**：人类给出大方向 → 模型输出 `implementation_plan.md` → 人类一键批准计划书（全局知情） → 模型在凭证有效期内静默执行。底层防火墙一行不改，用户体验跨越至"真正聪明的助理"层次。

---

## 4. 测试体系的三点自我反思

1. **Ecosystem Blindness（生态視野缺失）**：过去仅测"本地框架是否跑通"，忽视了上游模型的"自我保护过滤"行为和"惰性输出"截断。未来必须将上游模型行为纳入测试假设。

2. **Adversarial Test 缺位**：缺乏"系统在 API 400、内容安全阻断、高频截断时能否优雅恢复"的对抗性测试。Chaos Interceptor 是对此的直接回应。

3. **框架级测试脱离模型变数**：底层权限或框架类验证（如 Schema 合规、L1 拦截），必须使用硬编码测试探针（Test Shim），彻底脱离"用 LLM prompt 触发测试场景"的依赖。

**固化原则**：未来质量保障体系不仅要证明框架能成功"跑通"，更要证明框架在模型突然罢工和环境畸变时依然"坚不可摧"。

---

## 5. 2026-05-03 验收补充复盘（Postmortem Addendum）

Phase 62 / 59 的后续人工验收又暴露出一类与“代码是否存在”不同层级的问题：**运行时接线是否真的闭环，以及我们是否拿到了足够硬的证据。**

### 5.1 主要失真来源

1. **前门拒绝不等于后台熔断**：危险请求被前台直接拒绝，只能证明通用安全策略工作了，不能证明 Worker/Cron 的 `content_filter` 熔断分支真的生效。
2. **模型答对不等于 KI / Prompt 注入真的生效**：如果日志里没有出现诸如 `L0: Injected KI rule ...` 这类硬信号，就不能把“推荐了正确工具”记为规则注入通过。
3. **消费侧存在，不等于生产侧闭环**：TaskTracker 透明化如果只有 prompt 注入、没有主循环稳定写入状态，那只是“能显示”，不是“有真实状态可显示”。
4. **repo 中有资源，不等于 runtime 一定加载到了**：规则文件、workspace 模板、工具注册、审批存储、运行时目录和环境变量，任何一个掉链子，都会让设计意图在 live 环境中失效。

### 5.2 根因判断

这轮问题的根因，不是单点实现缺失，而是**把“设计意图”误当成了“运行时事实”**。  
我们过去容易在以下节点产生假阳性：

- 看到回答像对，就默认机制已触发；
- 看到仓库里有文件，就默认 runtime 会加载；
- 看到 prompt 中能消费状态，就默认一定有人在生产状态；
- 看到人工能复现某条 happy path，就默认 phase 可以宣告完成。

### 5.3 固化后的组织级教训

1. **Proof over prose**：自然语言总结只能作为辅助说明，不能作为通过证据。
2. **Repo / Runtime parity is a deliverable**：运行时资源落点、加载路径、缺失时退化行为，本身就是要交付和验收的内容。
3. **Producer + Consumer must both exist**：任何“透明化/注入/提示增强”能力，都必须同时验证状态生产端与消费端。
4. **Manual bug must become deterministic evidence**：人工验收发现的问题，必须升格为 red test、behavior probe 或 adversarial regression，之后才能重新宣称完成。
5. **Acceptance must isolate layers**：前台拒绝、后台熔断、规则注入、审批挂起、状态透明化等层必须分开验证，不能互相替代。

### 5.4 对流程的强制回写

上述教训已经回写到协作流程本身：

- `execute_phase.md` 现在强制要求 `Runtime Artifact Parity Checklist` 与 `Proof Signals / Observable Success Criteria`
- `execute_phase.md` 明确禁止“回答像对”被当成通过
- `harness_lite.md` / `harness_heavy.md` 现在要求在设计阶段显式写出 `False Positive Success Paths`
- `harness_heavy.md` 要求 ADR Candidate 在进入 `Accepted` 前必须写清运行时前提与验收硬证据

这意味着：**后续类似 Phase 62 的问题，不应再被当成“调试细节”，而应被视为 workflow 未达标。**

---

## 6. 演化路线图

| 优先级 | 任务 | 受影响文件 |
|---|---|---|
| **P0** (立即) | Schema 全链路 Null 合规修复 | `session/manager.py`, `agent/context.py`, `_trim_history` |
| **P0** (立即) | Worker/Cron Graceful Pause + AzureContentFilterException | `providers/litellm_provider.py`, `cron/service.py` |
| **P1** (本 Sprint) | User 角色越权清除（L362, L299 拒绝分支降维） | `agent/state_handler.py` |
| **P1** (本 Sprint) | Planning Gate V1 实现（`write_artifact` + `ApprovalStore` 批量注册） | `agent/loop.py`, `agent/hitl_store.py`, `AGENTS.md` |
| **P1** (本 Sprint) | `middleware/*.py`, `context.py` 语义消防区扫描 & Ruff 自定义规则 | `agent/middleware/`, CI pipeline |
| **P2** (下 Sprint) | Chaos Interceptor 混沌注入测试套件 | `tests/adversarial/` (新建目录) |

---

## 7. 明确不在本 ADR 范围内

- ❌ L1 引入 LLM 旁路嗅探（**辩证永久封禁，禁止重提**）
- ❌ Bootstrap Files 的全量 Prompt 重写（风险过高，需独立 ADR）
- ❌ 客户端（200+ 分布式实例）的任何变更（零客户端侧改动原则）
- ❌ 多模型灰度切换策略（超出当前迁移范畴）

---

## 参考

- `nanobot/agent/state_handler.py` — 越权注入点（L299, L362）
- `nanobot/agent/verification.py` — `_check_rule_destructive_guard` + `_DESTRUCTIVE_PATTERNS`
- `nanobot/agent/loop.py` — HITL `ApprovalStore` 消费点（L721-L794）
- `docs/adr/ADR-61-command-control-l1-vs-hitl.md` — L1/HITL 分层前身决策
- `docs/adr/ADR-59-antigravity-pattern-integration.md` — Planning Gate 架构原型
- `docs/antigravity_architecture_reference.md` — Planning Mode 与 Artifact 机制参考
