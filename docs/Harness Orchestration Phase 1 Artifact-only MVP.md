# Harness Orchestration Phase 1: Artifact-only MVP

This document outlines the architecture and implementation plan for Phase 1 of the Harness Orchestration Blueprint. The goal is to build a robust, file-based state machine in Python that manages Harness jobs, scaffolds artifacts, and tracks progress without automatically dispatching workers yet. 

Antigravity has prepared this plan. **Codex will execute the code generation**, and Antigravity will serve as the reviewer upon completion.

## User Review Required

> [!IMPORTANT]
> **Codex Handoff**: Please review this plan. If approved, you can pass this `implementation_plan.md` to Codex to generate the code. Once Codex finishes, I will review its PR/commit against this contract.

## Proposed Architecture

We will create a new Python package `nanobot.agent.harness` to encapsulate the orchestration logic.

### 1. Core State Management & Scaffold

#### [NEW] `nanobot/agent/harness/job.py`
- Defines the `HarnessJob` class.
- Handles generating UUID-based or timestamp-based `job_id`s.
- Responsible for atomic reads/writes to `.agent/artifacts/harness_<mode>/<job_id>/state.json`.
- State fields should include: `job_id`, `mode`, `status`, `current_stage`, `goal`, `created_at`, `last_transition_at`.

#### [NEW] `nanobot/agent/harness/scaffold.py`
- Responsible for setting up the directory structure when a job starts.
- Writes boilerplate Markdown files (e.g., `draft_v1.md`, `review_packet.md`, `validation_packet.md`) with basic headers so the worker has a target to fill out.

### 2. State Machine & Rules

#### [NEW] `nanobot/agent/harness/state_machine.py`
- Implements the stage transitions.
- **Lite Mode Stages**: `INIT` -> `BASELINE_READY` -> `DRAFT_V1_READY` -> `REVIEW_PACKET_READY` -> `CANDIDATE_READY` -> `EVIDENCE_GATE_READY` -> `DONE`
- **Heavy Mode Stages**: `INIT` -> `BASELINE_READY` -> `DRAFT_V1_READY` -> `CRITIQUE_READY` -> `DRAFT_V2_READY` -> `VALIDATION_PACKET_READY` -> `ADR_CANDIDATE_READY` -> `EVIDENCE_GATE_READY` -> `DONE`
- **Gate Check Logic**: The `advance_state()` method must physically check the file system (e.g., "Does `review_packet.md` exist and is it non-empty?") before allowing a transition from `DRAFT_V1_READY` to `REVIEW_PACKET_READY`.

#### [NEW] `nanobot/agent/harness/prompts.py`
- A dictionary or registry of "Thin Prompts".
- When a job transitions to a new state, this module returns the exact prompt text the user should copy-paste to the worker (e.g., "Please read `state.json` and fulfill the `DRAFT_V1_READY` requirement by modifying `draft_v1.md`").

### 3. CLI Entry Point

#### [NEW] `nanobot/agent/harness/cli.py`
Provides the `argparse` command-line interface with three main sub-commands:
1. `start --mode <lite|heavy> --goal "<text>"`
   - Creates the job, scaffolds directories, sets state to `INIT`, prints the first prompt.
2. `status --job <job_id>`
   - Reads `state.json`, checks the file system, and prints whether the current stage's required artifacts are fulfilled.
3. `advance --job <job_id>`
   - Invokes the state machine check. If files are ready, advances the state, updates `state.json`, and prints the prompt for the next stage. If files are missing, it blocks and prints an error.

#### [NEW] `nanobot/agent/harness/__init__.py`
- Exposes core classes (`HarnessJob`, `HarnessCLI`).

## Verification Plan

Antigravity will verify Codex's implementation by:
1. **Executing the CLI**: Running `python -m nanobot.agent.harness.cli start --mode lite --goal "Test"` and verifying the `.agent/artifacts/` directory is properly created with `state.json` and empty Markdown files.
2. **State Transition Test**: Attempting to run `advance` immediately and ensuring the CLI strictly blocks the transition because the required artifacts are empty/missing.
3. **Mocking Artifacts**: Touching/writing mock content to the required markdown files and verifying that `advance` successfully updates the state machine to the next phase.
