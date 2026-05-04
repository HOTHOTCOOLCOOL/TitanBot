# Evidence Gate

## A# / Status / Evidence / Meaning

| A# | Status | Evidence | Meaning |
| --- | --- | --- | --- |
| A1 | PASS | `candidate.md` 已把 Phase 1 收敛为 lite-only，并把唯一合法路径锁定为 `.agent/artifacts/harness_lite/<job_id>/`；同时要求 `--mode heavy` 显式拒绝，不再允许 `harness_<mode>` 泛化路径。 | 计划层面已消除路径与 workflow 契约的直接冲突。 |
| A2 | PASS | `candidate.md` 的 `Scope` 与 `Decision Summary` 明确写死 Phase 1 = lite-only MVP，`heavy` 延后；`Evidence Plan` 也不再把 heavy 放进本期完成定义。 | MVP 边界已收敛成单一结论，不再悬空。 |
| A3 | PASS | `candidate.md` 的 `Adopted Criticisms` 与 `Ready Rules` 已将 Evidence Gate 的最小结构抬升到 `A# / Status / Evidence / Meaning` + 总结果，不再只看 `PASS / FAIL / BLOCKED`。 | 计划层面的 ready 检查已与 Lite workflow 契约对齐。 |
| A4 | PASS | `candidate.md` 的 `Launcher Contract` 明确把 launcher 视为 exact literal protocol，并要求 golden/snapshot tests 验证逐字输出。 | 计划层面已经把 launcher 从“语义近似文案”提升为可验证契约。 |
| A5 | PASS | `candidate.md` 的 `Root Policy` 明确采用 repo-marker + hard-fail 规则，拒绝 workspace fallback；repo 外或分离场景必须显式 `--root`。 | 默认 root 的错误风险从“静默写错位置”收敛为“显式失败并提示修正”。 |
| A6 | PASS | `candidate.md` 的 `State Model` 与 `Evidence Plan` 明确规定 `status/advance` 必须先扫文件系统、再刷新 `state.json`，并要求 stale snapshot 负向测试。 | `state.json` 已被锁定为诊断性快照，而不是第二真相源。 |

## PASS / FAIL / BLOCKED

PASS

## Decision

本次 `harness_lite` 针对“Phase 1 Harness Orchestration 计划”这一**设计 Artifact** 的综合与核验已通过。  
含义是：

- `candidate.md` 已经把 Critic 的五个主 findings 收敛为一套更可执行的计划契约
- 当前通过的是**计划门禁**，不是代码已实现
- 若下一步要真正落地代码，应切换到 `execute_phase`，并以 A1-A6 作为实现阶段的退出条件
