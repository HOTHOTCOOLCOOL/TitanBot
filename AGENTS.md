# Codex Project Entry

This repository uses **Artifact-first workflows** for structured multi-session work.  
Do not improvise cross-session process from memory when a workflow already exists.

## Workflow Router

When the user explicitly mentions one of these workflow names, **read the file first** before doing anything else:

- `harness_lite` -> `.agent/workflows/harness_lite.md`
- `harness_heavy` -> `.agent/workflows/harness_heavy.md`
- `execute_phase` -> `.agent/workflows/execute_phase.md`

If the user asks for a structured design / ADR / review workflow without naming one:

- Prefer `harness_lite` for small or medium design tasks, local trade-offs, and quick ADR candidates.
- Prefer `harness_heavy` for architecture changes, security boundaries, schema migrations, or high-blast-radius decisions.

If the user asks to implement code **after** a harness decision is complete, switch to `execute_phase`.

## Harness Rules

When running `harness_lite` or `harness_heavy`:

1. Treat the workflow file as the source of truth for stage order, session ownership, and blocked conditions.
2. Use **thin launcher, fat artifact** behavior:
   - launcher message = short
   - real context = files in `.agent/artifacts/...`
3. Do not rely on free-form chat recap as cross-session truth.
4. If a required Artifact is missing, unclear, or contradictory, output `BLOCKED` and stop.
5. Do not silently promote a candidate to `Accepted` before the workflow's Evidence Gate says it is allowed.

## Session Discipline

For harness workflows, respect role separation:

- A lead session may synthesize, but not fake independent critique.
- A critic / validator session must read only the allowed Artifacts and named repo files.
- Do not use prior chat history as a substitute for required Artifact files.

If the current conversation is clearly only one session in a multi-session harness:

- perform only that session's role
- write the required Artifact(s)
- give the next exact launcher message if the workflow requires one

## Artifact Paths

Default artifact roots:

- Lite: `.agent/artifacts/harness_lite/<job_id>/`
- Heavy: `.agent/artifacts/harness_heavy/<job_id>/`
- Execute phase: `.agent/artifacts/execute_phase/<job_id>/`

Always prefer exact paths over bare filenames when instructing another session.

## Practical Defaults

- For simple bug fixing or fact-checking, do **not** force a harness unless the user asks for it.
- For design work, avoid dumping long prose into chat when an Artifact should hold the contract.
- For cross-session work, the user is a supervisor, not a human message bus.
