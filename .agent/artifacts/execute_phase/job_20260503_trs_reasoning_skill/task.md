# Task

- [ ] T01 Add red tests that lock the ReasoningSkill KG schema contract and the 1000-character reasoning-template prompt budget.
- [ ] T02 Preserve Knowledge Graph entity `type` metadata so manually curated `reasoning_template` entities survive reload and reindex flows.
- [ ] T03 Implement type-aware KG injection in `context.py` so only retrieved `reasoning_template` entries are truncated to a strict 1000-character budget before prompt append.
- [ ] T04 Run focused regressions plus the required Zone A baseline, then write back results to `.agent/artifacts/execute_phase/job_20260503_trs_reasoning_skill/codex_result.md`.
