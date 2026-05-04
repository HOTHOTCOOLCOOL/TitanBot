# Candidate

## Adopted Criticisms

- **F1 (Unevidenced Extraction)**: Adopted. We abandon the idea of using `auto_reviewer.py` for autonomous trace distillation. This violates the single-agent rule and relies on non-existent code.
- **F2 (Incompatible schema in skills.py)**: Adopted. `skills.py` is a filesystem-loader for executable tools and markdown playbooks. Adding a parallel schema there fractures the design.
- **F3 (IFCC hand-wave)**: Adopted. IFCC handles output condensation (`<mem>`), not pre-call input budgeting. We must define a concrete budget rule.
- **F4 (Split source of truth)**: Adopted. Spreading retrieval logic across `skills.py`, KG, and custom prompts guarantees negative transfer.

## Rejected Criticisms
None. The Critic correctly identified that Draft V1 mixed incompatible abstractions and relied on unevidenced future systems.

## Final Candidate

**1. Storage & Schema (Single Source of Truth)**
A "reasoning skill" will be stored natively in the Knowledge Graph as a standard MDER-DR entity:
- `name`: The trigger condition or problem domain (e.g., "Reasoning: Parsing Legacy Binary Format")
- `description`: The reasoning template and pitfalls.
- `type`: `"reasoning_template"`
This utilizes the exact same persistence (`nanobot/agent/knowledge_graph.py`) as all other knowledge.

**2. Retrieval & Safe Degradation**
No changes to retrieval logic. The existing `KnowledgeGraph.get_entity_context` (which uses the 5-layer hybrid retrieval) will naturally retrieve these templates if the user's prompt matches the `name` or `description`. If the confidence is below the existing threshold, nothing is retrieved, and the agent safely falls back to standard CoT.

**3. Prompt Injection & Budgeting**
In `nanobot/agent/context.py`, the existing Knowledge Graph injection block (around line 290) handles the payload. To resolve F3, we establish an explicit cap: the system will enforce a strict 1000-character truncation on any retrieved entity of type `reasoning_template` before it is appended to the `system_prompt`. This guarantees the reasoning block cannot crowd out essential context.

**4. Extraction (HITL / Manual Only)**
Reasoning templates will be manually curated by human operators or explicitly created by the agent via standard `execute_phase` (using `write_file` or KG update tools to add the entity). No background, unattended distillation loop will exist. 

## Residual Risks
- The LLM might ignore the injected reasoning template if its internal weights strongly favor a different approach (Base Model alignment clash).

## Evidence Plan
- **A1**: Verify extraction is entirely manual/HITL (Knowledge Graph manual updates).
- **A2**: Verify the KG is the only storage layer, keeping `skills.py` untouched.
- **A3**: Verify `context.py` handles the budget directly via explicit truncation, avoiding IFCC.
- **A4**: Verify fallback behavior relies on existing KG confidence thresholds.
- **A5**: Verify insertion reuses `kg_context`.
