# Harness Orchestration Blueprint

## 1. 文档定位

这不是现成工作流，也不是立即开工的实现单。  
这是面向后续新会话讨论的**构建设想蓝图**，目标是把当前的半自动：

- `harness_lite.md`
- `harness_heavy.md`

进一步演化为一个真正的 **orchestration layer**，让用户不再频繁手工切会话、转启动语、判断下一阶段。

---

## 2. 问题陈述

当前半自动 Harness 的优点：

- Artifact-first
- 上下文隔离明确
- 角色分工清楚
- Evidence Gate 能阻止“未验证先 Accepted”

但当前仍有三个高成本点：

1. **HITL 很重**：用户要频繁切会话、复制固定启动语。
2. **状态靠人记忆**：用户需要知道当前进行到哪个阶段。
3. **会话句柄不稳定**：不同会话之间没有统一的 job-state 绑定。

理想中的 orchestration 层，应该把这些机械动作自动化，同时**不破坏 Artifact-first 契约**。

---

## 3. 目标

### 3.1 主要目标

- 自动创建 Harness Job
- 自动建立 Artifact 目录与文件骨架
- 自动驱动 Lite / Heavy 的阶段切换
- 自动把指定 Artifact 投递给正确的会话 / worker
- 自动等待阶段产物出现并推进到下一阶段
- 自动执行 Evidence Gate 前后的状态检查

### 3.2 非目标

- 不追求“全自动无审批”
- 不让 orchestrator 绕过 sandbox / approval / HITL
- 不允许 manager 自己改写 Artifact 契约
- 不把聊天摘要当作状态真值

---

## 4. 核心原则

### 4.1 Artifact Is Truth

所有状态推进都以文件为准，而不是以聊天气氛为准。

### 4.2 Thin Launcher, Fat Artifact

投递给 worker / 会话的消息应尽量薄。真正的内容在 Artifact。

### 4.3 Explicit Session Ownership

每个阶段都要绑定明确所有者：

- Lite：A / B
- Heavy：A / B / C

### 4.4 No Silent Promotion

在 Evidence Gate 通过前，系统不得把 Candidate 自动提升为 Accepted。

### 4.5 Human Is Supervisor, Not Bus

人类只做审批、纠偏、异常处理。  
人类不该再充当复制粘贴和会话说明员。

---

## 5. 目标形态

## 5.1 Lite Orchestration

期望用户只做：

1. `start`
2. `approve critique send`
3. `approve finalize`

系统自动做：

- 建 `job_id`
- 建目录
- 写模板
- 推送到 Session A / B
- 收 `review_packet.md`
- 提醒或自动执行 Evidence Gate

## 5.2 Heavy Orchestration

期望用户只做：

1. `start`
2. `approve B critique`
3. `approve C validation`
4. `approve C evidence gate`
5. `approve final close`

系统自动做：

- 建立 A / B / C 三会话绑定
- 按顺序投递 Artifact
- 等待阶段性文件完成
- 记录回流路径
- 避免错误阶段推进

---

## 6. 建议架构

### 6.1 `HarnessManager`

建议新建一个专用 orchestrator，例如：

`nanobot/agent/harness_manager.py`

它不是通用聊天 agent，而是**有限状态机**：

- 输入：`mode`, `job_id`, `source`, `goal`
- 输出：下一阶段投递、当前状态、异常、完成结论

### 6.2 `HarnessJob`

建议将每个 job 的状态保存为：

`.agent/artifacts/harness_<mode>/<job_id>/state.json`

至少包含：

- `job_id`
- `mode`
- `status`
- `current_stage`
- `owned_sessions`
- `artifact_dir`
- `required_files`
- `last_transition_at`
- `last_error`

### 6.3 `ArtifactScaffold`

负责：

- 创建目录
- 初始化文件模板
- 校验必备 Artifact 是否存在
- 产出固定路径 Registry

### 6.4 `SessionRouter`

负责：

- 将某个阶段路由给 A / B / C
- 记录每个会话的职责和最近一次产物
- 保证不会把 B 的任务错投给 C

### 6.5 `PromptPack`

负责：

- 为每个阶段生成极薄启动语
- 引用固定 Artifact 路径
- 统一 BLOCKED 语义

### 6.6 `EvidenceGateRunner`

负责：

- 检查 `validation_packet.md` / `evidence_plan.md` 是否齐备
- 校验 `A#` 与验证方法是否一一对应
- 在 Gate 完成后做结构化解析

### 6.7 `HumanApprovalLayer`

负责：

- 在关键阶段停下
- 让用户做明确 approve / reject
- 不允许 orchestration 擅自跳过高风险阶段

---

## 7. 建议状态机

### 7.1 Lite

```text
INIT
  -> BASELINE_READY
  -> DRAFT_V1_READY
  -> REVIEW_PACKET_READY
  -> CANDIDATE_READY
  -> EVIDENCE_GATE_READY
  -> DONE
```

失败回流：

```text
EVIDENCE_GATE_READY(FAIL)
  -> CANDIDATE_READY or DRAFT_V1_READY
```

### 7.2 Heavy

```text
INIT
  -> BASELINE_READY
  -> DRAFT_V1_READY
  -> CRITIQUE_READY
  -> DRAFT_V2_READY
  -> VALIDATION_PACKET_READY
  -> ADR_CANDIDATE_READY
  -> EVIDENCE_GATE_READY
  -> DONE
```

失败回流：

```text
EVIDENCE_GATE_READY(FAIL)
  -> ADR_CANDIDATE_READY / DRAFT_V2_READY / BASELINE_READY
```

---

## 8. 与现有体系的关系

### 8.1 与 `execute_phase.md`

建议复用其成熟约束：

- Artifact-first
- 薄启动语
- 固定目录
- 缺件即阻塞
- 用户不是消息总线

Harness 解决“决策与验证”；`execute_phase` 解决“实施与验收”。

### 8.2 与 `SubagentManager` / `CoordinatorManager`

这些现有能力更像**worker substrate**，不是完整的 Harness orchestration。

未来可探索：

- 让 `HarnessManager` 使用现有 worker 作为执行后端
- 但前提是保留显式阶段控制和 Artifact 契约

也就是说，先有 Harness state machine，后谈是否用 subagent / worker 去承载每个阶段。

---

## 9. MVP 路线

### Phase 1：Artifact-only Orchestration

先不真正自动开 worker，只做：

- `harness start --mode lite|heavy`
- 自动建 job 目录
- 自动写模板
- 自动生成“下一句应该发什么”
- 自动检测当前缺什么 Artifact

### Phase 2：Session-aware Orchestration

再做：

- 记录 A / B / C 会话 ID 或句柄
- 自动生成对应阶段启动语
- 自动提示用户去哪个会话

### Phase 3：Auto-dispatch Orchestration

最后再做：

- 自动把启动语和 Artifact 路径投递给目标会话 / agent
- 自动等待文件完成
- 自动推进到下一阶段

### Phase 4：Evidence-aware Gatekeeper

增强：

- 自动检测 `A#` 是否齐备
- 自动检查是否有人提前把状态写成 `Accepted`
- 自动在 FAIL 时回流到正确阶段

---

## 10. 风险

### 10.1 伪自动化

如果 orchestration 只是“自动生成更多聊天文本”，而没有真正接管状态机和 Artifact 检查，那只是更复杂的 HITL。

### 10.2 上下文污染

如果 manager 把完整聊天记录一路转发给所有 worker，会直接破坏 Harness 的会话隔离价值。

### 10.3 状态漂移

如果 `state.json` 与 Artifact 实际内容不同步，会出现“系统以为已经到下一阶段，但文件还没准备好”的问题。

### 10.4 过度自治

如果 orchestrator 能够在高风险阶段不经审批自动推进，会和安全边界冲突。

---

## 11. 建议下一次讨论重点

下个会话建议聚焦这四个问题：

1. `HarnessManager` 是做成 CLI、后台服务，还是 manager agent？
2. `state.json` 的最小字段集是什么？
3. 自动派工前，最小 MVP 是否只做“自动建 Artifact + 自动给出下一句”？
4. 是否要把现有 `execute_phase` 的 Artifact 模式直接抽象成通用底座？

---

## 12. 一句话愿景

最终目标不是“让更多 agent 更自由”，而是：

**让正确的会话在正确的阶段读取正确的 Artifact，并在证据通过前绝不假装任务已经完成。**
