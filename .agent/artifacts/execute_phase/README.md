# Execute Phase Artifacts

Each `execute_phase` job should create its own subdirectory here:

`.agent/artifacts/execute_phase/<job_id>/`

One Phase may own multiple sibling `job_id`s, including concurrent jobs.
Keep each job in its own directory and enumerate the relevant `job_id`s explicitly in phase-level docs or acceptance notes.

Recommended contents:

1. `implementation_plan.md`
2. `task.md`
3. `codex_handoff.md`
4. `codex_result.md`
5. `codex_feedback.md`
