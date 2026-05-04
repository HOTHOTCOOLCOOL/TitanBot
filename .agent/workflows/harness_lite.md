---
description: 双会话、Artifact-first 的半自动 Harness，用于简单任务、局部设计与低中风险决策
---

# Harness Lite

`harness_lite` 是 `harness.md` 的**具体落地版**：它不是泛泛而谈的辩证提示词，而是一套**双会话、半自动、Artifact-first** 的执行协议。

它的目标不是让两个会话都“更自由”，而是：

1. 让事实基线先于方案；
2. 让批判和作者分离；
3. 让用户只负责**固定启动语**和会话切换；
4. 让上下文通过 Artifact 传递，而不是靠口头转述；
5. 让结束条件由 Evidence Gate 决定，而不是由会话自我感觉决定。

---

## 1. 适用范围

### 适合使用

- 小到中等规模的代码改动前讨论
- Bug 修复方案审查
- 单模块或局部接口调整
- ADR / 设计记录的快速 Candidate 产出
- 需要“有人拆台”，但不值得开三会话的任务

### 不适合使用

- 大规模架构迁移
- 安全边界重构
- 跨多个系统 / 多个团队接口的重大决策
- 任何“一次判断错误就会带来高代价返工”的任务

这些任务请使用 `harness_heavy.md`。

---

## 2. 双会话拓扑

### Session A：Lead

负责：

- 建立事实基线
- 产出 `Draft V1`
- 读取 Critic 的审查结果后综合收敛
- 产出 `candidate.md`
- 执行最终 Evidence Gate

### Session B：Critic

负责：

- 只基于指定 Artifact 做独立拆台
- 指出逻辑漏洞、事实假设、遗漏风险
- 给出“必须保留”的正确部分
- 给出最小验收清单 `A#`

### 角色铁律

- Session A 不能假装自己是独立审查员。
- Session B 不能顺手接管规划，也不能直接写最终方案。
- 用户不是消息总线；用户只转交**固定启动语**。

---

## 3. Phase 62 / 59 反自欺护栏

Lite 虽然轻量，但只要任务涉及运行时注入、审批链路、后台任务、工具路由、缓存、workspace 资源、Prompt 注入或“模型推荐某条路径”这类易出现假阳性的场景，必须遵守下面三条：

1. **回答像对，不算机制生效**：不能因为模型回复看起来合理，就认定 KI 注入、Planning Gate、TaskTracker、Cron 熔断等机制真的工作了。
2. **设计阶段先问反例**：每个 Candidate 都必须回答“如果底层机制根本没触发，外部表现是否仍可能看起来像成功？”；答不出来就说明设计还不够实。
3. **Evidence Gate 看硬信号**：日志、状态迁移、持久化文件、审批态、禁用标记、探针输出优先于自然语言表象。没有硬信号，就不能宣称通过。

若任务的目标是产出 ADR 候选、或后续要进入 `execute_phase`，这些护栏必须直接写进 Artifact，而不是留在聊天里口头提醒。

---

## 4. Artifact 目录

固定目录：

`.agent/artifacts/harness_lite/<job_id>/`

`job_id` 规则：

1. 优先使用稳定、ASCII、无空格名称。
2. 推荐格式：`lite_<YYYYMMDD>_<topic>`。
3. 若用户未提供，Session A 必须生成，并在阶段结束时明确写给用户。

### 必备文件

1. `problem_statement.md`
2. `baseline.md`
3. `draft_v1.md`
4. `review_packet.md`
5. `candidate.md`
6. `evidence_gate.md`

### 文件职责

#### `problem_statement.md`

至少包含：

- `Job ID`
- `Goal`
- `Source Context`
- `In Scope`
- `Out of Scope`
- `Expected Output`

#### `baseline.md`

这是**事实真值表**。至少包含：

- `Claim / Evidence / Status`
- `Source of Truth Files`
- `Runtime Artifacts / Hidden Runtime States`
- `Observable Proof Signals`
- `Unknowns`
- `Questions the Critic Must Attack`

#### `draft_v1.md`

至少包含：

- 当前方案摘要
- 关键 trade-off
- 风险与假设
- `False Positive Success Paths`（哪些情况下外部表现会像成功，但机制其实没触发）
- 仍待验证的点

#### `review_packet.md`

由 Session B 写入。至少包含：

- `Findings`：按严重度排序
- `Must Keep`
- `Weak Claims / Unverified Claims`
- `False Positive Risks`
- `Acceptance Checklist`：`A# / Claim / Evidence Method / Proof Signal / Expected Result / If Fail`

#### `candidate.md`

由 Session A 写入。至少包含：

- `Adopted Criticisms`
- `Rejected Criticisms`
- `Final Candidate`
- `Runtime Preconditions / Parity Assumptions`
- `Residual Risks`
- `Evidence Plan`

#### `evidence_gate.md`

由 Session A 写入。至少包含：

- `A# / Status / Evidence / Meaning`
- `Observed Proof Signals`
- `PASS / FAIL / BLOCKED`
- `Decision`

---

## 5. 上下文管理铁律

- Session B **只允许**读取：
  - `problem_statement.md`
  - `baseline.md`
  - `draft_v1.md`
  - 这些文件中明确点名的 repo 文件
- Session B **禁止**读取：
  - Session A 的完整聊天记录
  - 用户对方案的自由转述
  - 任何“我们其实更倾向于 xxx”的口头提示
- Session A 可以读取全部 Lite Artifacts 与必要 repo 文件，但仍然禁止把“未验证猜测”写成既成事实。
- 任一关键 Artifact 缺失、路径不清、内容互相冲突，当前会话必须立刻输出 `BLOCKED` 并停止。

---

## 6. 标准流程

### Phase A0：启动与事实基线

由 Session A 执行：

1. 创建 `job_id`
2. 创建 Artifact 目录
3. 写入 `problem_statement.md`
4. 写入 `baseline.md`
5. 若任务涉及运行时敏感机制，必须在 `baseline.md` 中写清 repo / runtime 落点、隐藏运行时状态、以及可观测硬信号。
6. 若事实基线无法建立，直接 `BLOCKED`

### Phase A1：Draft V1

由 Session A 执行：

1. 基于 `baseline.md` 写入 `draft_v1.md`
2. 明确哪些结论是事实，哪些只是方案假设
3. 若方案声称某机制会生效，必须明确写出“若机制没触发，外部仍可能像成功的路径”。
4. 结束时只能给用户一段固定启动语，送去 Session B

### Phase B2：Critic Review

由 Session B 执行：

1. 只读指定 Artifact
2. 写入 `review_packet.md`
3. 必须优先攻击“回答看起来正确，但机制并未生效”的假阳性路径
4. 不给最终方案
5. 不替 Session A 做综合

### Phase A3：Candidate Synthesis

由 Session A 执行：

1. 读取 `review_packet.md`
2. 产出 `candidate.md`
3. 必须逐条回应 `review_packet.md` 中的主要 findings
4. 必须写清运行时前提、repo / runtime 一致性假设与 Proof Plan
5. 不能跳过 “Rejected Criticisms” 部分

### Phase A4：Evidence Gate

由 Session A 执行：

1. 逐条执行 `review_packet.md` 中的 `Acceptance Checklist`
2. 写入 `evidence_gate.md`
3. 对运行时敏感任务，若没有命中 `Proof Signal`，即使方案文字上看起来合理，也必须记为 `FAIL` 或 `BLOCKED`
4. 若任一关键 `A#` 为 `FAIL` 或 `BLOCKED`，不得宣称完成

---

## 7. 固定启动语

### 6.1 启动 Lite

在 Session A 原样发送：

```text
请按 harness_lite 工作流启动任务。
job_id: <可留空，让会话生成>
source: <issue / ADR / 文档 / 文件路径>
goal: <一句话目标>
```

### 6.2 送往 Session B

当 Session A 完成 `draft_v1.md` 后，必须让用户原样发送：

```text
请按 harness_lite 的 Critic 阶段执行。
先读取 `.agent/artifacts/harness_lite/<job_id>/problem_statement.md`
再读取 `.agent/artifacts/harness_lite/<job_id>/baseline.md`
再读取 `.agent/artifacts/harness_lite/<job_id>/draft_v1.md`
必要时只额外读取上述 Artifact 中明确点名的 repo 文件。
不要读取其他聊天历史，不要润色，不要替作者圆方案。
把结果写入 `.agent/artifacts/harness_lite/<job_id>/review_packet.md`
如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。
```

### 6.3 返回 Session A 做综合与核验

当 Session B 完成后，回到 Session A 原样发送：

```text
继续 harness_lite 综合与核验，job_id=<job_id>
请先读取 `.agent/artifacts/harness_lite/<job_id>/review_packet.md`
然后写出 `candidate.md` 并执行 Evidence Gate，结果写入 `evidence_gate.md`。
若有关键项 FAIL 或 BLOCKED，不得宣称完成。
```

---

## 8. BLOCKED 条件

以下任一命中，必须停止：

- Artifact 目录不存在
- `problem_statement.md` / `baseline.md` / `draft_v1.md` 缺失
- Session B 被要求读聊天而不是读 Artifact
- `review_packet.md` 没有 `Acceptance Checklist`
- Evidence Gate 没有给出 `A# / Status / Evidence / Meaning`
- 运行时敏感任务的 `baseline.md` 缺少 `Runtime Artifacts / Hidden Runtime States` 或 `Observable Proof Signals`
- 运行时敏感任务的 `draft_v1.md` 没有说明 `False Positive Success Paths`

---

## 9. 通过条件

只有同时满足下面条件，`harness_lite` 才算完成：

1. `candidate.md` 已存在
2. `evidence_gate.md` 已存在
3. 所有关键 `A#` 为 `PASS`
4. `evidence_gate.md` 明确说明哪些点已验证，哪些仍为剩余风险
5. 对运行时敏感任务，`evidence_gate.md` 必须明确记录 `Observed Proof Signals`，并能区分“机制已触发”与“只是回答像对”

---

## 10. 失败回路

若 Evidence Gate 未通过：

1. Session A 必须在 `candidate.md` 中追加 `Revision Notes`
2. 若变更是**实质性改写**，必须重新生成 `draft_v1.md` 或覆盖其内容
3. 用户再次把固定启动语发送到 Session B

不要使用“口头解释一下我们后来改了什么”的方式跳过 Artifact。

---

## 11. 收口规则

`harness_lite` 只负责：

- 事实基线
- 拆台
- 方案收敛
- Evidence Gate

若后续需要真正编码，请切换到 `execute_phase.md`。  
不要把 Lite 当成编码工作流本身。
若 Lite 的产物将进入 ADR 或 `execute_phase`，必须确保 Candidate 已经把 runtime 前提、proof signal、假阳性路径写清，否则不能把它当成“可执行设计”。
