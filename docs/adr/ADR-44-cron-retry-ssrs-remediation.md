# ADR-44: Cron 重试引擎加固与 SSRS 幻觉防线重构

**状态**: 已采纳 (Accepted)  
**日期**: 2026-04-10  
**Harness 辩证轮次**: 5 阶 (Planner → Opus Critic → Gemini V2 → Gemini Validator → Claude Final)  
**受影响文件**: `nanobot/cron/service.py`, `nanobot/cron/types.py`, `nanobot/skills/ssrs-report/fetch_report.py`, `nanobot/agent/verification.py`

---

## 背景与问题陈述

生产运营中发现三个相互关联的高危故障：

1. **单次 Cron 任务触发 3 次**：`CronService._execute_job` 在检测到 SSRS 连接超时（响应含 error 字符串）时，无条件追加 15-min 重试，且无执行上限。SSRS 持续不可用时，重试在日内无限循环。
2. **2 封重复邮件输出**：第 1 次已成功发出邮件 → 重试盲目再发第 2 封；若第 2 次仍触发 error → 再发第 3 封。
3. **SSRS 失败 → 幻觉替换报告**：SKILL.md 无硬性禁令 + Task Completion Bias 驱使 LLM 调用 `outlook.search` 寻找"替代报告"，用"销售日报"冒充"排名报告"。

### 关键架构事实确认（纠正前次会话误判）

> `UnifiedScheduler`（`scheduler.py`）已导出至 `__init__.py`，但**零生产调用者**。  
> 当前 gateway 唯一活跃调度引擎是 `CronService`（`service.py`）。  
> 本次修复直接针对 `CronService`，`UnifiedScheduler` 标记为 `@Phase44-Target`（未来升级目标）。

---

## 决策

### 保留的核心设计

- `_skip_stale_cross_day_jobs`（跨天陈旧 Job 跳过）：设计正确，保留。
- `UnifiedScheduler`：本阶段不废止，不在生产侧激活，标记为未来目标。
- SSRS 三层身份认证 fallback（SSPI → Keyring → .env）：保留，与本次无关。
- **确定性优先原则**（源于 `ARCHITECTURE.md §1`）：副作用检测改用 `TraceArchive` 工具调用日志，绝不依赖 LLM 自由文本。

### 核心架构变更

#### 变更 1：引入 `retry_count` + `error_fatal` 终态（重试引擎重构）

**为什么**：旧实现无重试上限，在 SSRS 长期不可用时会在日内无限循环执行，重复发送邮件产生 N 封重复输出。

**决策**：
- `CronJobState` 新增 `retry_count: int = 0` 与 `parent_trace_id: str | None = None`。
- 硬性熔断阈值 `MAX_RETRIES = 1`：重试一次后仍失败，状态锁定为 `error_fatal`，停止本周期所有后续调度并触发告警。
- 新 cron 周期成功触发时（`last_status = "ok"`），重置 `retry_count = 0`。
- 重试时记录 `parent_trace_id`，维护与原执行的 Trace-ID 血缘关系（承接 Phase 42 Trace-ID 基建，防止可观测性断链）。

#### 变更 2：确定性副作用检测（替换字符串匹配）

**为什么**：用 LLM 自由文本（`SIDE_EFFECT_MARKERS` 字符串匹配）判断副作用可靠性约等于掷骰子——假阳性会导致邮件丢失无人知晓，假阴性则导致问题重现。

**决策**：改为查询 `TraceArchive.get_tool_calls(trace_id)` 获取本轮结构化工具调用记录：
- 若 `outlook_send_email` / `send_email` 成功调用（`status == "success"`）→ 副作用确认执行
- 副作用已执行 + 响应含 error → 状态 `partial_success`，**抑制一切重试**，发送通知告知 SSRS 失败
- 副作用未执行 + 响应含 error + `retry_count < MAX_RETRIES` → 正常重试逻辑
- **Fail-safe 原则**：`TraceArchive` 查询失败时，保守判断为"无副作用"，宁可多发一封邮件，也不静默丢失邮件

#### 变更 3：中间件级幻觉防线（替换 SKILL.md 提示词防御）

**为什么**：SKILL.md 中的自然语言约束在 Task Completion Bias 面前是纸糊的（现有 SKILL.md L159-165 同类规则已被证伪）。Cron 无人值守场景下"询问用户"出口不可达。

**决策**：在 `verification.py` 新增规则 `R-SSRS-001`：
- 检测本轮 `exec` 工具输出中是否包含 `{"error_type": "DependencyFatal"}`（来自 `fetch_report.py` 的结构化失败标记）
- 若检测到 SSRS 致命失败，**动态封锁** `allow_outlook_search` 等工具（从 `tool_registry_override` 物理移除），从 L1 层面切断 LLM 寻找替代报告的能力
- `deny` 结果携带明确人类可读说明，引导 LLM 直接向用户坦诚 SSRS 不可用

#### 变更 4：SSRS Fast-fail + 结构化错误输出

**为什么**：原有 `timeout=30` 意味着三次重试 = 90 秒 agent 阻塞。依赖字符串匹配要求中间件对自然语言做模式匹配，脆弱且不可扩展。

**决策**：
- `fetch_as_csv` / `fetch_as_html` 超时从 30s 缩至 **10s**
- CLI 失败路径追加 stdout JSON 输出：`{"error_type": "DependencyFatal", "report_name": ..., "reason": ...}`（stderr 仍保留人类可读错误信息兼容现有调试流程）

---

## 新状态机一览

| 状态 | 含义 | Dashboard 颜色 | 是否触发通知 |
|:---:|:---|:---:|:---:|
| `ok` | 全程成功，`retry_count` 重置为 0 | 🟢 绿色 | 否 |
| `partial_success` | 邮件等副作用已交付，SSRS 辅助依赖失败 | 🟠 橙色 | ✅ 是（告知 SSRS 失败） |
| `error` | 首次失败，已调度 15-min 单次重试 | 🔴 红色 | ✅ 是 |
| `error_fatal` | 超出重试上限，本周期永久停止，需人工介入 | 🟣 深紫色 | ✅ 是（最高优先级） |
| `skipped` | 跨天陈旧任务已跳过（已有逻辑，保留） | ⚫ 灰色 | 否 |

---

## 实施范围

| 模块 | 变更类型 | 优先级 |
|:---|:---|:---:|
| `nanobot/cron/types.py` | 新增 `retry_count`, `parent_trace_id` 字段 | P0 |
| `nanobot/cron/service.py` | 重写 `_execute_job`，新增 `_check_side_effect_via_trace` | P0 |
| `nanobot/skills/ssrs-report/fetch_report.py` | timeout 缩至 10s，失败路径新增结构化 JSON 输出 | P0/P1 |
| `nanobot/agent/verification.py` | 新增 `R-SSRS-001` 规则 | P1 |
| Dashboard UI | 补充 `partial_success` / `error_fatal` 配色 | P3 |

---

## 未解决问题 / 未来展望

- **`on_job` 回调协议升级**（P2）：需将签名从 `Coroutine[str | None]` 改为 `Coroutine[tuple[str | None, str | None]]`（含 trace_id 回传），需同步更新 `commands.py` 中的回调绑定。
- **`UnifiedScheduler` 迁移**（@Phase44-Target）：`scheduler.py` 的单一事件循环设计优于 `CronService` 独立 timer 模型，应在下一个稳定窗口期完成迁移，彻底替换 `CronService`。
- **TraceArchive 接口确认**：`get_tool_calls(trace_id)` 的具体接口形态需在实施前与 Phase 42 Trace-ID 系统对齐。

---

## 参考

- `docs/adr/ADR-42B-trace-id.md` — Phase 42 全链路 Trace-ID 系统（`parent_trace_id` 的基础设施依赖）
- `docs/adr/ADR-42-harness-review.md` — 上次 Harness 审查 ADR
- `nanobot/cron/service.py` — 当前 `CronService` 实现
- `nanobot/agent/verification.py` — L1 验证中间件（规则引擎宿主）
- `nanobot/skills/ssrs-report/SKILL.md` — SSRS 技能定义文档
