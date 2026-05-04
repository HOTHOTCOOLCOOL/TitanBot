# Draft V1: Reasoning Skill Distillation

## 1. Summary of Proposed Solution

We propose integrating TRS-style reasoning distillation into Nanobot by adding a `ReasoningSkill` schema to `nanobot/agent/skills.py`. 

Instead of traditional executable tools, a `ReasoningSkill` acts as a cognitive template:
```python
class ReasoningSkill:
    skill_id: str
    trigger_condition: str  # e.g., "When asked to write a parser for a legacy binary format"
    reasoning_template: str # The distilled step-by-step logic to avoid detours
    pitfalls: list[str]     # Known dead-ends or common errors to avoid
```

**Workflow:**
1. **Extraction (Offline)**: We rely on the upcoming Phase 65 L2 `auto_reviewer.py` to identify highly successful execution traces. When a task completes efficiently, the L2 Codex distills the trace into a `ReasoningSkill` JSON and places it in the Knowledge Graph for HITL review.
2. **Retrieval (Online)**: During a user query, Nanobot's 5-Layer Hybrid Retrieval system matches the user's intent against `trigger_condition`s.
3. **Injection**: `nanobot/agent/context.py` injects the top-1 matching `reasoning_template` and `pitfalls` into the System Prompt under a new section `[Cognitive Strategy]`, heavily guided by IFCC to ensure budget compliance.

## 2. Key Trade-offs
- **Input Tokens vs. Output Tokens**: We increase input prompt size (spending ~200-500 input tokens on the template) to save thousands of expensive output "thinking" tokens.
- **Generalization vs. Specificity**: A highly specific template might mislead the agent on a slightly different task (negative transfer). We trade broad adaptability for specific efficiency.

## 3. Risks & Assumptions
- **Risk**: The retrieved reasoning skill might force the model into an inappropriate cognitive path (Hallucination/Misdirection). 
- **Risk**: Context overflow if `reasoning_template`s are too long, potentially violating IFCC bounds.
- **Assumption**: The existing 5-Layer Hybrid Retrieval is accurate enough to match `trigger_condition`s without generating false positives.

## 4. Still Needs Verification
- Should `ReasoningSkill` be a standalone class in `skills.py`, or simply a specialized `MDER-DR` node in the Knowledge Graph?
- How to structure the L2 Codex prompt to reliably output the `pitfalls` array without human intervention.
