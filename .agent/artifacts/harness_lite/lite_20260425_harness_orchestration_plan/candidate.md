# Candidate

## Adopted Criticisms

### F1: Artifact 路径必须与 workflow 契约完全一致

采纳。  
Phase 1 不再使用抽象写法 `.agent/artifacts/harness_<mode>/<job_id>/`。  
本次候选方案把已支持模式收敛为 `lite-only`，因此唯一合法的 Artifact 目录是：

` .agent/artifacts/harness_lite/<job_id>/ `

同一条路径必须同时用于：

- `start` 创建目录
- `status/advance` 定位 job
- launcher 输出
- `state.json` 所在目录

### F2: MVP 范围必须收敛为单一结论

采纳。  
Phase 1 明确为 **Lite-only MVP**。

- `lite`：本期正式支持
- `heavy`：本期不支持，不生成目录，不生成 launcher，不进入测试矩阵

CLI 可以保留 `--mode` 参数以降低未来扩展时的接口破坏，但在 Phase 1 中：

- `--mode lite`：正常执行
- `--mode heavy`：明确报错并提示“heavy deferred to later phase”

### F3: Evidence Gate 检查必须抬升到 workflow 契约强度

采纳。  
Phase 1 的 ready 判定不再把 `evidence_gate.md` 简化成“包含 `PASS / FAIL / BLOCKED` 即可”。  
对于 Lite：

- 文件必须存在
- 文件不得保留 stub 哨兵
- 文件必须包含 `A#`
- 文件必须包含 `Status`
- 文件必须包含 `Evidence`
- 文件必须包含 `Meaning`
- 文件必须包含总结果 `PASS` / `FAIL` / `BLOCKED`

少任何一项，都只能判定为 not ready / blocked。

### F4: Launcher 必须被锁成可验证协议

采纳。  
Phase 1 把 launcher 视为协议正文，而不是“语义相近的 UI 文案”。

实现约束如下：

- `prompts.py` 存放逐字模板
- 输出文本必须保持 workflow 规定的路径、读取顺序、限制语句
- 为每个支持阶段增加 exact-output golden test / snapshot test
- 若 workflow 契约变更，代码模板与测试快照必须在同一提交中同步更新

### F5: 默认 root 必须 fail-closed，而不是静默猜测

采纳。  
Phase 1 不做 workspace fallback。

默认 root 规则改为：

1. 若显式传入 `--root`，使用该路径
2. 否则从 `cwd` 向上搜索，只有在找到 repo marker
   - `.agent/workflows/harness_lite.md`
   时，才认定该 repo root
3. 若未找到 marker，则硬失败，并提示：
   - 请在仓库内运行命令，或
   - 显式传入 `--root <repo_root>`

这样可以避免把 Artifact 静默写入错误树。

## Rejected Criticisms

没有拒绝五个主 findings。  
唯一没有完全采纳的隐含推论是：**不需要删除“向上搜索 repo marker”这项便利能力本身**。  
保留它是合理的，但必须置于 fail-closed 规则之下，不能再伴随任何 workspace-first 的静默回退。

## Final Candidate

### Decision Summary

本次最终候选方案是一个 **repo-local、Artifact-first、Lite-only 的 Harness Phase 1 MVP**。  
它不是第二个 Agent runtime，也不是新的 planning state machine，而是一个围绕现有 workflow 契约构建的辅助层。

### Scope

Phase 1 只交付以下能力：

1. 创建 Lite Harness job 目录与模板文件
2. 生成并刷新 `state.json` 诊断快照
3. 基于文件系统派生当前阶段与 blockers
4. 输出固定 launcher
5. 为关键 ready 判定提供最小结构化校验

Phase 1 不交付：

1. `heavy` 模式支持
2. 自动派工
3. 运行时级别的 agent state machine
4. workflow 文档解析器

### CLI Shape

命令集仍集成到现有 `Typer` 主入口：

```text
nanobot harness start --mode lite --goal "..." --source "..."
nanobot harness status --job <job_id>
nanobot harness advance --job <job_id>
```

若用户执行：

```text
nanobot harness start --mode heavy ...
```

应立即得到显式拒绝，而不是隐式创建 `harness_heavy` 目录。

### Artifact Contract

Phase 1 只有一个支持的 Artifact 根路径：

` .agent/artifacts/harness_lite/<job_id>/ `

Lite 模式最低必备文件仍与 workflow 保持一致：

- `problem_statement.md`
- `baseline.md`
- `draft_v1.md`
- `review_packet.md`
- `candidate.md`
- `evidence_gate.md`
- `state.json`

其中 `state.json` 是新增辅助文件，但不能替代上述 Markdown Artifact。

### Root Policy

Root 解析采用 repo-marker + hard-fail 模式：

- 在 repo 根或其子目录内运行：自动解析
- 在 repo 外运行：报错
- 安装态 / repo-workspace 分离：要求显式 `--root`

不允许出现以下行为：

- 自动回退到 `Config.workspace_path`
- 在未知目录默默创建 `.agent/artifacts/...`

### State Model

`state.json` 只保存：

- job 元数据
- 最近一次检查时间
- 最近一次派生阶段
- 最近一次 blockers 快照

禁止把它当作权威阶段真相源。  
`status` 和 `advance` 每次都必须：

1. 先扫描文件系统
2. 重新计算阶段
3. 再覆盖写回 snapshot

### Stage Definition

Phase 1 只实现 Lite 阶段集。  
`heavy` 不进入 `stages.py` 的正式可执行矩阵；若为了未来演进保留内部数据结构占位，也不得对外暴露为已支持能力。

### Ready Rules

所有由脚手架生成的模板文件都带统一 stub 哨兵，例如：

`<!-- HARNESS:STUB -->`

通用 ready 判定：

1. 文件存在
2. 移除空白后仍有正文
3. 不再包含 stub 哨兵

关键文件额外规则：

- `review_packet.md` 必须包含 `Acceptance Checklist`
- `candidate.md` 必须包含 `Adopted Criticisms`、`Rejected Criticisms`、`Final Candidate`
- `evidence_gate.md` 必须包含 `A# / Status / Evidence / Meaning`

### Launcher Contract

Launcher 模板必须逐字锁定。  
Phase 1 不采用“语义相近即可”的策略。

最低要求：

1. `prompts.py` 中维护 exact literal templates
2. 测试覆盖 start 后给出的下一步 launcher
3. 测试覆盖 advance 后给出的下一步 launcher
4. 对路径、读取顺序、`BLOCKED` 条件提示做 exact match

### Verification Boundary

本候选方案的通过含义是：**计划已经被收敛成可执行契约**。  
真正的代码实现与运行时验证，应进入 `execute_phase` 完成。

## Residual Risks

- workflow 文档与 launcher 模板之间仍存在双份维护成本，但 golden test 会让漂移可见
- repo marker 搜索在复杂 monorepo 中仍可能需要用户显式 `--root`
- `heavy` 被延期后，未来扩展时需要一次新设计，而不是无缝开启
- `state.json` 的“快照而非真相源”需要靠测试持续防止回潮

## Evidence Plan

| A# | Implementation Proof Required |
| --- | --- |
| A1 | `CliRunner` 测 `start --mode lite` 创建 `.agent/artifacts/harness_lite/<job_id>/`；`start --mode heavy` 明确拒绝；输出 launcher 路径与目录一致。 |
| A2 | 帮助文案、实现计划、测试清单都明确声明 Phase 1 为 lite-only；不存在“heavy 也支持”的模糊表述。 |
| A3 | 为缺少 `A# / Status / Evidence / Meaning` 的 `evidence_gate.md` 写负向测试，结果必须 not ready / blocked。 |
| A4 | 为每个已支持阶段写 exact-output launcher golden test；路径、读取顺序、限制语句必须逐字一致。 |
| A5 | 覆盖 repo 根、子目录、repo 外、repo/workspace 分离四类 root 场景；除预期 repo 外均需显式成功或显式失败。 |
| A6 | 人工篡改 `state.json` 的 `derived_stage` 后运行 `status/advance`，结果仍必须以当前 Artifact 现状为准并刷新快照。 |
