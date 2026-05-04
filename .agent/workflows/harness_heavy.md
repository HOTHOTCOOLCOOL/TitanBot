---
description: 三会话、Artifact-first 的半自动 Harness，用于架构调整、安全边界与重大决策
---

# Harness Heavy

`harness_heavy` 是面向**重大决策**的三会话版 Harness。  
它建立在 `harness.md` 的“辩证 + 证据门禁”原则上，但做了更强的上下文隔离：

- 作者与批判者分离
- 批判者与验证者分离
- Evidence Gate 尽量由**非作者会话**执行

如果 `harness_lite` 是“快速但不草率”，`harness_heavy` 就是“慢一点，但尽量不自欺”。

---

## 1. 适用范围

### 适合使用

- 架构调整
- 安全边界变化
- 数据 / Schema 迁移
- 多模块协同改动
- 影响范围大、回滚代价高的方案
- 正式 ADR 进入 `Accepted` 前的候选决策审查

### 不适合使用

- 小 Bug
- 单文件局部修补
- 只需要事实确认、不需要多轮 trade-off 的任务

这类任务使用 `harness_lite.md` 即可。

---

## 2. 三会话拓扑

### Session A：Lead / Synthesizer

负责：

- 建立事实基线
- 产出 `Draft V1`
- 吸收批判后写出 `Draft V2`
- 生成 `adr_candidate.md`
- 最终读取 Evidence Gate 并决定是否收口或返工

### Session B：Extreme Critic

负责：

- 对 `Draft V1` 发动高强度批判
- 重点攻击逻辑漏洞、事实假设、性能与安全冲突、契约漂移
- 不做最终整合

### Session C：Validator / Evidence Auditor

负责：

- 对 `Draft V2` 做中立审查
- 写出“必须保留”的正确设计
- 产出验收矩阵
- 在后续阶段执行独立 Evidence Gate

### 角色铁律

- A 不得假装自己是 B 或 C。
- B 不得顺手替 A 写最终方案。
- C 不得被拿来当润色器；它的职责是验证和把关。
- 用户只做固定切换，不做自由摘要。

---

## 3. Phase 62 / 59 反自欺护栏

Heavy 的设计目标之一，就是防止团队把“看起来成功”误写成“已经被证明成功”。对所有涉及安全边界、审批、后台任务、Prompt 注入、工具链路、运行时状态透明化、workspace 资源或 Provider 行为的方案，必须额外遵守：

1. **行为表象不能替代机制证据**：模型推荐了正确工具、前台返回了正确话术、某条请求被拒绝了，都不足以证明目标机制真的生效。必须追问“是哪条机制触发的、证据在哪里”。
2. **ADR 候选必须写清运行时前提**：凡是未来会进入 ADR、Planning Gate 或 `execute_phase` 的候选方案，必须写清 repo 制品、运行时落点、加载路径、缺失时退化行为。
3. **Evidence Gate 只认硬证据**：日志、状态迁移、持久化字段、审批状态、禁用标记、探针输出，比自然语言总结更高优先级。没有硬证据，不得进入 `Accepted`。
4. **必须主动设计假阳性反例**：每个方案都要回答“如果底层机制根本没有触发，什么外部现象会让人误判为通过？”；答不出来，说明方案尚未完成验证设计。

---

## 4. Artifact 目录

固定目录：

`.agent/artifacts/harness_heavy/<job_id>/`

`job_id` 规则：

1. 优先使用稳定、ASCII、无空格名称。
2. 推荐格式：`heavy_<YYYYMMDD>_<topic>`。
3. 若用户未提供，Session A 必须生成。

### 必备文件

1. `problem_statement.md`
2. `baseline.md`
3. `draft_v1.md`
4. `critique.md`
5. `draft_v2.md`
6. `validation_packet.md`
7. `adr_candidate.md`
8. `evidence_plan.md`
9. `evidence_gate.md`

### 文件职责

#### `problem_statement.md`

至少包含：

- `Job ID`
- `Goal`
- `Business / Technical Context`
- `In Scope`
- `Out of Scope`
- `Decision Type`
- `Expected Deliverable`

#### `baseline.md`

这是整个 Heavy 流程的真值起点。至少包含：

- `Claim / Evidence / Status`
- `Source of Truth Files`
- `Operational Constraints`
- `Runtime Preconditions / Runtime Artifacts`
- `Hidden Runtime States`
- `Observable Proof Signals`
- `Unknowns`
- `Questions Critic Must Attack`

#### `draft_v1.md`

至少包含：

- 初始技术路径
- 核心 trade-off
- 风险清单
- `False Positive Success Paths`
- 仍未验证的假设

#### `critique.md`

由 Session B 写入。至少包含：

- `Findings`
- `Fatal Assumptions`
- `Contract Drift Risks`
- `False Positive Success Risks`
- `Where Draft V1 Overreaches`
- `What Is Still Worth Keeping`

#### `draft_v2.md`

由 Session A 写入。至少包含：

- `Adopted Criticisms`
- `Rejected Criticisms`
- `Trade-off Rationale`
- `Runtime Prerequisites / Repo-Runtime Parity`
- `Updated Risks`
- `Open Verification Items`

#### `validation_packet.md`

由 Session C 写入。至少包含：

- `Must Keep`
- `Resolved vs Unresolved`
- `Unverified Claims`
- `Acceptance Matrix`

其中 `Acceptance Matrix` 至少包含：

- `A#`
- `Claim`
- `Evidence Method`
- `Proof Signal`
- `Expected Result`
- `If Fail, What It Means`

#### `adr_candidate.md`

由 Session A 写入。至少包含：

- `Status`：只能是 `Proposed`、`Candidate` 或 `Needs Validation`
- `Context`
- `Decision`
- `Runtime Prerequisites`
- `Acceptance Proof`
- `Adopted / Rejected`
- `Consequences`
- `Residual Risks`

#### `evidence_plan.md`

由 Session A 写入。至少包含：

- 要执行的命令 / 测试 / 文件断言
- 每条验证对应哪个 `A#`
- repo / runtime parity 检查
- 需要观测的 `Proof Signal`
- 哪些验证是关键门禁

#### `evidence_gate.md`

由 Session C 写入。至少包含：

- `A# / Status / Evidence / Meaning`
- `Observed Proof Signals`
- `Critical Pass Summary`
- `Failures / Blockers`
- `Decision`

---

## 5. 上下文隔离铁律

### Session B 允许读取

- `problem_statement.md`
- `baseline.md`
- `draft_v1.md`
- 上述文件中明确点名的 repo 文件

### Session B 禁止读取

- Session A 的完整聊天记录
- 用户自己的总结性转述
- Session C 的任何文档

### Session C 在验证阶段允许读取

- `problem_statement.md`
- `baseline.md`
- `draft_v2.md`
- `critique.md`
- 相关 repo 文件

### Session C 在 Evidence Gate 阶段允许读取

- `adr_candidate.md`
- `evidence_plan.md`
- `validation_packet.md`
- 验证所需 repo 文件 / 测试入口 / 命令信息

### 全局禁令

- 禁止把整段聊天历史粘给另一个会话。
- 禁止用户用自然语言“顺手解释一下之前发生了什么”。
- 缺件、路径不明、Artifact 冲突，立即 `BLOCKED`。

---

## 6. 标准流程

### Phase A0：启动与事实基线

由 Session A 执行：

1. 创建 `job_id`
2. 创建 Artifact 目录
3. 写入 `problem_statement.md`
4. 写入 `baseline.md`
5. 对运行时敏感方案，必须在 `baseline.md` 中写清 runtime 前提、隐藏状态、repo / runtime 落点与可观测硬信号。
6. 若无法建立事实基线，直接 `BLOCKED`

### Phase A1：Draft V1

由 Session A 执行：

1. 基于 `baseline.md` 写入 `draft_v1.md`
2. 明确事实、假设、风险
3. 必须显式写出 `False Positive Success Paths`
4. 结束时只给 Session B 固定启动语

### Phase B2：Extreme Critic

由 Session B 执行：

1. 读取指定 Artifact
2. 写入 `critique.md`
3. 必须优先攻击“表面正确但机制未触发”的假阳性成功路径
4. 不给最终方案
5. 不替 A 做折中整合

### Phase A3：Draft V2

由 Session A 执行：

1. 读取 `critique.md`
2. 写入 `draft_v2.md`
3. 必须显式说明采纳 / 拒绝了哪些批判
4. 必须补齐 `Runtime Prerequisites / Repo-Runtime Parity`

### Phase C4：Validation Packet

由 Session C 执行：

1. 读取 `draft_v2.md` 与 `critique.md`
2. 写入 `validation_packet.md`
3. 必须产出 `Acceptance Matrix`
4. 对运行时敏感方案，`Acceptance Matrix` 中每个关键 `A#` 都必须带 `Proof Signal`

### Phase A5：ADR Candidate + Evidence Plan

由 Session A 执行：

1. 读取 `validation_packet.md`
2. 写入 `adr_candidate.md`
3. 写入 `evidence_plan.md`
4. 对 ADR 候选，必须把 `Runtime Prerequisites` 与 `Acceptance Proof` 写进正文，而不是只放在聊天解释里
5. 不得将状态写为 `Accepted`

### Phase C6：Evidence Gate

由 Session C 执行：

1. 读取 `adr_candidate.md`、`evidence_plan.md`、`validation_packet.md`
2. 逐条执行关键 `A#`
3. 写入 `evidence_gate.md`
4. 若只能证明“回答像对”或“前台行为像成功”，但未观测到 `Proof Signal`，必须判定 `FAIL` 或 `BLOCKED`
5. 若任一关键 `A#` 为 `FAIL` 或 `BLOCKED`，必须判定未通过

### Phase A7：收口或返工

由 Session A 执行：

1. 读取 `evidence_gate.md`
2. 若通过，给出收口结论
3. 收口时必须明确哪些结论已被硬证据证明、哪些仍是残余风险
4. 若未通过，明确回到哪一阶段返工

---

## 7. 固定启动语

### 6.1 启动 Heavy

在 Session A 原样发送：

```text
请按 harness_heavy 工作流启动任务。
job_id: <可留空，让会话生成>
source: <issue / ADR / 文档 / 文件路径>
goal: <一句话目标>
```

### 6.2 送往 Session B 做 Extreme Critic

当 Session A 完成 `draft_v1.md` 后，必须让用户原样发送：

```text
请按 harness_heavy 的 Extreme Critic 阶段执行。
先读取 `.agent/artifacts/harness_heavy/<job_id>/problem_statement.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/baseline.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/draft_v1.md`
必要时只额外读取上述 Artifact 中明确点名的 repo 文件。
不要读取其他聊天历史，不要补作者的意图，不要做最终综合。
把结果写入 `.agent/artifacts/harness_heavy/<job_id>/critique.md`
如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。
```

### 6.3 回到 Session A 做 Draft V2

回到 Session A 原样发送：

```text
继续 harness_heavy 重构，job_id=<job_id>
请先读取 `.agent/artifacts/harness_heavy/<job_id>/critique.md`
然后写出 `draft_v2.md`。
必须明确写出 Adopted Criticisms、Rejected Criticisms、Trade-off Rationale。
```

### 6.4 送往 Session C 做 Validation Packet

当 Session A 完成 `draft_v2.md` 后，必须让用户原样发送：

```text
请按 harness_heavy 的 Validation 阶段执行。
先读取 `.agent/artifacts/harness_heavy/<job_id>/problem_statement.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/baseline.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/critique.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/draft_v2.md`
必要时只额外读取上述 Artifact 中明确点名的 repo 文件。
不要读取其他聊天历史，不要代替作者做最终决策。
把结果写入 `.agent/artifacts/harness_heavy/<job_id>/validation_packet.md`
其中必须包含 Acceptance Matrix。
如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。
```

### 6.5 回到 Session A 产出 ADR Candidate

回到 Session A 原样发送：

```text
继续 harness_heavy 生成候选决策，job_id=<job_id>
请先读取 `.agent/artifacts/harness_heavy/<job_id>/validation_packet.md`
然后写出 `adr_candidate.md` 与 `evidence_plan.md`。
注意：状态只能是 Proposed / Candidate / Needs Validation，不得写 Accepted。
```

### 6.6 送往 Session C 做 Evidence Gate

当 Session A 完成 `adr_candidate.md` 与 `evidence_plan.md` 后，必须让用户原样发送：

```text
请按 harness_heavy 的 Evidence Gate 阶段执行。
先读取 `.agent/artifacts/harness_heavy/<job_id>/adr_candidate.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/evidence_plan.md`
再读取 `.agent/artifacts/harness_heavy/<job_id>/validation_packet.md`
按其中 A# 执行必要验证，并把结果写入 `.agent/artifacts/harness_heavy/<job_id>/evidence_gate.md`
对每个 A# 输出 PASS / FAIL / BLOCKED 与证据摘要。
若任一关键 A# 未通过，不得给出 Accepted 结论。
如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。
```

### 6.7 回到 Session A 收口

回到 Session A 原样发送：

```text
继续 harness_heavy 收口，job_id=<job_id>
请先读取 `.agent/artifacts/harness_heavy/<job_id>/evidence_gate.md`
若关键项全部通过，给出最终收口结论；
若未通过，明确指出应回到哪一阶段返工。
```

---

## 8. BLOCKED 条件

以下任一命中，必须停止：

- `problem_statement.md` / `baseline.md` / `draft_v1.md` 缺失
- `critique.md` 不包含明确 findings
- `validation_packet.md` 不包含 `Acceptance Matrix`
- `adr_candidate.md` 状态被提前写成 `Accepted`
- `evidence_plan.md` 没有把验证映射到 `A#`
- `evidence_gate.md` 没有输出 `PASS / FAIL / BLOCKED`
- 运行时敏感方案的 `baseline.md` 缺少 `Runtime Preconditions / Runtime Artifacts`、`Hidden Runtime States` 或 `Observable Proof Signals`
- `draft_v1.md` 没有写出 `False Positive Success Paths`
- `validation_packet.md` 的关键 `A#` 缺少 `Proof Signal`

---

## 9. 通过条件

只有同时满足下面条件，`harness_heavy` 才算通过：

1. `adr_candidate.md` 已存在
2. `evidence_plan.md` 已存在
3. `evidence_gate.md` 已存在
4. 所有关键 `A#` 为 `PASS`
5. Session A 读取 `evidence_gate.md` 后，明确说明哪些结论已经验证、哪些仍是残余风险
6. 对运行时敏感方案，`evidence_gate.md` 必须记录 `Observed Proof Signals`，并明确排除了主要假阳性路径

---

## 10. 返工路径

### 从 Evidence Gate 失败回流

- 事实问题 / 验收问题：回到 Phase A5 或 C4
- 方案结构问题：回到 Phase A3
- 根本前提错误：回到 Phase A0 / A1，并必要时重新触发 Session B

### 返工原则

- 不允许用聊天补充说明代替 Artifact 修订
- 不允许跳过 `baseline.md` 更新
- 不允许把失败的 `A#` 静默删除
- 不允许把“模型这次答对了”当成通过理由写进 ADR 或 Evidence Gate

---

## 11. 收口规则

`harness_heavy` 的最终产物是：

- `adr_candidate.md`
- `evidence_plan.md`
- `evidence_gate.md`

如果后续需要真正编码，请再切换到 `execute_phase.md`。  
Heavy 的职责是**把大决策压到足够清楚、足够可验证**，不是直接开始施工。
若 Heavy 的输出要进入正式 ADR 或 `execute_phase`，必须已经把 runtime 前提、proof signal、假阳性反例和 Evidence Plan 写清；否则它只能算讨论草稿，不能算可执行决策。
