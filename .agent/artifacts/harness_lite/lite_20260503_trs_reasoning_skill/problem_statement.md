# Problem Statement

**Job ID**: `lite_20260503_trs_reasoning_skill`

**Goal**: Implement `reasoning_skill` distillation and retrieval (inspired by the TRS paper) to reduce token-heavy Chain-of-Thought (CoT) reasoning costs on complex tasks, while maintaining Nanobot's single-agent philosophy and HITL security boundaries.

**Source Context**: 
- `paper_analysis_report.md` (Artifact from previous session)
- TRS Paper: "Thinking with Reasoning Skills" [2604.21764v2]

**In Scope**:
- Extending the existing `AutoSkill` or Knowledge Graph architecture to support a new `reasoning_skill` format.
- Modifying the `nanobot/agent/skills/` schema to handle triggers, templates, and pitfalls.
- Updating `nanobot/agent/context.py` or the IFCC (In-Flight Context Condensation) mechanism to retrieve and inject these traces at inference time.

**Out of Scope**:
- Training, fine-tuning, or modifying the weights of the base LLM.
- Implementing an unattended autonomous harness evolution agent (AHE).
- Modifying the core Zone A/B/C security boundaries or `Pre-flight Skill Verifier (PSV)`.

**Expected Output**:
A clear design draft (Draft V1) detailing the schema for `reasoning_skill` and the retrieval/injection mechanism within Nanobot's existing architecture.
