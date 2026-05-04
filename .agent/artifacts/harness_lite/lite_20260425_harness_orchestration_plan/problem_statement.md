# Problem Statement

## Job ID

`lite_20260425_harness_orchestration_plan`

## Requested Label

`Harness Orchestration Plan`

## Session Role

`Session A (Lead), Phase A0-A1`

## Goal

把 `docs/Harness Orchestration Phase 1 Artifact-only MVP.md` 收敛成一份与当前仓库约束一致、后续可继续走 Critic 审查的可实施计划草案。

## Source Context

- Primary source under review: `docs/Harness Orchestration Phase 1 Artifact-only MVP.md`
- Active workflow contract for this session: `.agent/workflows/harness_lite.md`
- Repo constraints and supporting evidence are established in `baseline.md`

## In Scope

- 审视原计划与当前 repo 约定、CLI 技术栈、Artifact 路径约定、既有 ADR 的一致性
- 明确 Phase 1 MVP 的最小可交付边界
- 形成一个可供 Critic 拆台的 `draft_v1.md`
- 只完成 Lite 工作流的 A0/A1，不越过 Critic 阶段

## Out of Scope

- 直接编写 `nanobot.agent.harness` 代码
- 执行 Session B Critic、Session A3 收敛、或 Evidence Gate
- 重写现有 `harness_lite` / `harness_heavy` / `execute_phase` 工作流文档正文
- 处理所有实现期细节，只锚定 MVP 级别的方案边界

## Expected Output

- `baseline.md`: 基于 repo 现状的事实真值表、未知项、Critic 攻击面
- `draft_v1.md`: 一个比原文更可落地的 MVP 计划草案
- 一个可直接发送给 Session B 的固定启动语
