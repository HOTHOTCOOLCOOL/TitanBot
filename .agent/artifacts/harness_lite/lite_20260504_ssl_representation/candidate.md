# Candidate

## Adopted Criticisms
1. **信任边界倒置 (High)**: Fully adopted. The SSL representation will **NOT** be used as a security boundary. `verification.py` and the AST Sandbox will remain the sole source of truth for execution authorization. The SSL JSON graph will be strictly used for Observability and Prompt Budgeting.
2. **`verification.py` 运行时接线点 (High)**: Adopted by pivoting. Since SSL is removed from the security boundary, we drop the claim that `verification.py` uses SSL for interception. `verification.py` continues using its existing Python rules.
3. **Prompt budget 现状不一致 (High)**: Fully adopted. `ContextBuilder` will be explicitly refactored so that when `skill_ssl` exists, it injects ONLY the `Scheduling` layer (max 1000 chars) instead of the raw 8000-char `SKILL.md`. This realizes the true token-saving benefit.
4. **Index-time lifecycle (Medium)**: Fully adopted. `SkillsLoader` will be enhanced to compute a composite hash of (`SKILL.md` + `validator.py` + `hooks.py` + `*.py`). The Knowledge Graph `skill_ssl` entity will be keyed to this hash. If any code changes, the graph is invalidated. Furthermore, `depends_on` will remain the single source of truth for dependency resolution; the SSL `Structural` layer will strictly act as an observability map, not a dependency resolver.

## Rejected Criticisms
- None. The Critic correctly identified that the original draft attempted to elevate an LLM-parsed document to a security boundary, which is fundamentally flawed and violates Nanobot's zero-trust execution model.

## Final Candidate (Revised Architecture)
The SSL representation is integrated strictly as an **Observability and Context Optimization** layer.
1. **Skill Normalizer**: An index-time LLM normalizer parses `SKILL.md` into a 3-layer JSON graph (Scheduling, Structural, Logical).
2. **Knowledge Graph**: Stored as a `skill_ssl` entity, keyed by a composite hash of all skill source files to prevent desynchronization.
3. **Context Builder**: During runtime, `ContextBuilder` queries the KG and injects ONLY the `Scheduling` layer (capped at 1000 chars) instead of the raw `SKILL.md`.
4. **Security**: `verification.py` and AST Sandbox remain untouched and completely ignore the SSL graph for authorization.

## Runtime Preconditions / Parity Assumptions
- `ContextBuilder` must be able to query the KG synchronously.
- `SkillsLoader` must have access to compute hashes of skill directory contents efficiently.
- If normalizer parsing fails (fail-closed), the system logs a warning, skips creating the `skill_ssl` entity, and `ContextBuilder` falls back to the legacy `SKILL.md` injection but applying a strict manual truncation.

## Residual Risks
- The LLM normalizer may hallucinate the `Scheduling` layer. If it does, the agent might receive incorrect instructions on how to call the skill. (Mitigated by: The agent will simply fail to execute the tool correctly, but it cannot bypass security limits).

## Evidence Plan
The design structurally guarantees the Acceptance Checklist by:
1. Hard-decoupling SSL from `verification.py`.
2. Hard-wiring `ContextBuilder` to exclusively use the Scheduling layer.
3. Keying KG cache to composite file hashes.
(Actual runtime validation will be performed in `execute_phase`).
