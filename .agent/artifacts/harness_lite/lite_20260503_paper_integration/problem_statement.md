# Problem Statement

- **Job ID**: `lite_20260503_paper_integration`
- **Goal**: Re-evaluate the P0 feature (Pseudo-Plan Guided Skill Retrieval via `<think>` tag) under `harness_lite`, with a strict focus on its Observability Contract and Allowed Write Set.
- **Source Context**: 
  - Previous implementation plan: `.agent/artifacts/execute_phase/lite_20260503_paper_integration/implementation_plan.md`
  - Paper Analysis context.
- **In Scope**:
  - Validating the mechanism that enforces the `<think>` tag usage.
  - Defining the strict observable signals that prove the pseudo-plan is generated *before* any tool execution.
  - Defining the "Allowed Write Set" (what state or files the agent is allowed to write to during or after the pseudo-planning phase) and how it is enforced at the runtime level.
- **Out of Scope**:
  - P1 (Skill Dependency Graph) which was already covered or is independent of this specific re-evaluation.
- **Expected Output**:
  - A hardened design for the P0 feature, documenting false-positive risks and a concrete Evidence Gate checklist for the Observability Contract and Allowed Write Set.
