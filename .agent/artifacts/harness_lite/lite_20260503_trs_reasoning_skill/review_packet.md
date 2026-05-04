# Review Packet

## Findings

### F1 [Critical] Draft V1 depends on an extraction pipeline that is not evidenced by the named code
Evidence: `draft_v1.md:17` says the upcoming Phase 65 L2 `.agent/scripts/auto_reviewer.py` will identify successful execution traces, distill them into `ReasoningSkill` JSON, and place them in the Knowledge Graph for HITL review. But `.agent/scripts/auto_reviewer.py:5-6` defines itself as an automated L2 review script, and `.agent/scripts/auto_reviewer.py:365-464` shows a CLI that builds a git diff, sends it to a review model, and prints review output. In the inspected interface there is no execution-trace capture, no success scoring contract, no JSON emission path, no Knowledge Graph write path, and no approval handoff.

Impact: This is not a small implementation gap. The draft treats the hardest half of the system as if it were an incremental reuse of an existing component, but the named component is a diff reviewer, not a reasoning-trace distiller. Given the project boundary in `problem_statement.md:5,16-19`, this missing contract is a blocker to accepting the design direction as written.

### F2 [High] `nanobot/agent/skills.py` is not the evidence-backed home for the proposed `ReasoningSkill` schema
Evidence: `problem_statement.md:13` and `draft_v1.md:5,31` treat `nanobot/agent/skills.py` as a schema layer. The inspected file shows a filesystem-oriented loader: `nanobot/agent/skills.py:57-63` defines `SkillsLoader`; `nanobot/agent/skills.py:70-100` enumerates skill directories containing `SKILL.md`; `nanobot/agent/skills.py:103-143` loads markdown skill content for prompt inclusion; `README.md:64` describes the skill system as hardened config/hooks/registry lifecycle, not as a store for structured reasoning records.

Impact: Adding a Python `ReasoningSkill` dataclass here does not automatically integrate with the existing discovery, retrieval, or injection behavior. The draft says it is extending the existing architecture, but the proposed storage choice actually creates a parallel mechanism unless it also defines persistence, indexing, and prompt-loading semantics.

### F3 [High] The prompt-budget claim relies on IFCC in a way the inspected code does not support
Evidence: `draft_v1.md:19,27` says `context.py` will inject a top-1 reasoning template under `[Cognitive Strategy]`, heavily guided by IFCC to ensure budget compliance. In the code, `nanobot/agent/context.py:85-90` shows IFCC as a prompt instruction asking the model to emit `<mem>` summaries after a step is resolved. That is not a budgeting or truncation subsystem for newly injected reasoning templates. The actual prompt assembly path at `nanobot/agent/context.py:259-296` already appends vector RAG and Knowledge Graph context directly to the system prompt. Aside from the small Task Tracker size check at `nanobot/agent/context.py:252-254`, there is no shown cap, selector, or conflict-resolution rule for an extra reasoning block.

Impact: The draft names context overflow as a risk, but the mitigation is currently asserted rather than evidenced. Without an explicit pre-call budget rule, the new strategy payload can crowd out existing RAG/KG/skills context or make prompt behavior harder to reason about.

### F4 [Medium] The draft has no single source of truth for storage, retrieval, and ranking
Evidence: `draft_v1.md:17` stores the output in the Knowledge Graph, `draft_v1.md:18` says the 5-layer hybrid retrieval system matches `trigger_condition`s, and `draft_v1.md:19` adds a new direct prompt injection lane in `context.py`. Meanwhile `README.md:59-64` confirms the repo already has separate concepts for hybrid retrieval, Knowledge Graph with MDER-DR, and a hardened skill system.

Impact: The design spreads one feature across three subsystems without naming the authoritative representation or ranking owner. That increases the chance of duplicated logic, stale copies, and negative-transfer bugs when retrieval confidence is weak.

## Must Keep

- Keep the boundary from `problem_statement.md:5,16-19`: reduce reasoning-token cost without changing model weights or weakening single-agent/HITL/security constraints.
- Keep the reuse-first instinct from `baseline.md:7-12` and `README.md:48,59-64`: prefer extending existing retrieval / KG / skill infrastructure over inventing a new autonomous executor.
- Keep the framing in `draft_v1.md:7-14` that a reasoning skill is advisory cognitive guidance, not an executable tool.
- Keep the explicit risk register in `draft_v1.md:25-28`: negative transfer and prompt growth are real first-class risks, not edge cases.

## Weak Claims / Unverified Claims

- `baseline.md:8-12` treats TRS results as enough evidence that this repo will benefit similarly. That is enough to justify exploration, not enough to validate this integration path.
- `problem_statement.md:13` refers to `nanobot/agent/skills/` schema, while the inspected code exposes `nanobot/agent/skills.py` as a loader. The target abstraction is still ambiguous.
- `draft_v1.md:17` assumes `auto_reviewer.py` can become a reasoning-skill extractor with HITL review, but the named file currently exposes a diff-review contract, not a trace-distillation contract.
- `draft_v1.md:22` claims a rough `~200-500` input-token spend and `thousands` of output tokens saved, but no repo-specific budget method or benchmark plan is given.
- `draft_v1.md:28` assumes the existing retrieval stack can match `trigger_condition`s accurately enough, but no confidence threshold or safe fallback behavior is specified in the inspected files.
- `draft_v1.md:31` proposes a specialized `MDER-DR` node as an option, but the permitted source files here do not establish what KG schema change would be required.

## Acceptance Checklist

| A# | Claim | Evidence Method | Expected Result | If Fail |
| --- | --- | --- | --- | --- |
| A1 | The extraction path does not bypass current HITL/single-agent boundaries. | Name the exact file(s), interface(s), and state transitions that capture candidate traces, distill them, hold them for review, and prevent activation before approval. | Each stage has an explicit owner and blocking gate; no hidden autonomous promotion path exists. | The design is still relying on an unevidenced trust-boundary change. |
| A2 | There is one authoritative representation of a `reasoning_skill`. | Point to the exact persistence location and exact read/write functions for `trigger_condition`, `reasoning_template`, and `pitfalls`. | Storage and retrieval are anchored to one subsystem instead of split across `skills.py`, KG, and ad-hoc prompt text. | Divergence and ranking ambiguity remain open. |
| A3 | Prompt injection is budgeted before the model call. | Show the exact code path that measures and limits the reasoning payload relative to the existing system prompt, RAG, KG, and history budget. | A concrete truncation/selection rule exists in code or in the accepted design contract; IFCC is not used as a hand-wave. | Context overflow/crowding remains unresolved. |
| A4 | Retrieval misfires degrade safely. | Define the confidence/ranking threshold and the behavior when no strong match exists or when a matched strategy conflicts with the task. | The agent can skip injection and fall back to normal behavior without forcing a bad cognitive path. | Negative transfer remains a known but uncontrolled failure mode. |
| A5 | The chosen insertion point is actually compatible with the current code. | Identify the exact functions to extend in `nanobot/agent/context.py` and/or `nanobot/agent/skills.py`, and explain why that path does not bypass the current progressive-loading pattern. | Modification scope is narrow, evidence-backed, and consistent with the current architecture. | The draft is still mixing incompatible abstractions. |
