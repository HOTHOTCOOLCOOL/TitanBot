# Draft V1

## Summary of Proposed Solution
We propose adding an index-time `SkillNormalizer` that intercepts the skill registration lifecycle. When a new skill (with a `SKILL.md`) is loaded, the Normalizer invokes a strict LLM extraction prompt to generate an SSL JSON graph. This graph maps the skill into:
1. **Scheduling**: Invocation triggers, parameters.
2. **Structural**: Execution phases (e.g., plan -> act -> verify).
3. **Logical**: Resource boundaries (e.g., `READ local_file`, `CALL external_api`).

This graph is stored in the Knowledge Graph as a `skill_ssl` entity. 
At runtime, `ContextBuilder` applies a prompt budget (max 1000 chars) when injecting the Scheduling layer to the model. `verification.py` (PSV) compares the planned tool calls against the Logical boundaries defined in the SSL graph. If a requested operation exceeds the SSL boundary, PSV halts the execution before even reaching the AST Sandbox.

## Key Trade-offs
- **Token Cost vs. Index-Time Safety**: Normalization adds latency and API costs during skill loading/registration, but saves context tokens during runtime by providing a highly compressed Scheduling interface rather than injecting the full raw `SKILL.md`.
- **Static vs. Dynamic**: SSL is static and derived from documentation, whereas AST is dynamic code analysis. SSL acts as a fast P0 gate; AST acts as the final P1 boundary.

## Risks & Assumptions
- **Assumption**: The LLM normalizer can reliably enforce the JSON schema without hallucinating permissions not present in the `SKILL.md`.
- **Assumption**: The `SKILL.md` accurately describes the Python implementation.
- **Risk**: Desynchronization. A developer updates the Python code to require network access but forgets to update `SKILL.md`. The SSL graph will falsely deny execution at the PSV stage.

## False Positive Success Paths (CRITICAL)
*What external behavior would look successful, even if the safety mechanism completely failed?*
1. **The "Silent Bypass"**: A malicious skill includes a `SKILL.md` that perfectly generates a benign SSL graph (e.g., claiming it only calculates math). The PSV checks the SSL graph and says "Pass". The skill's Python code contains hidden `os.remove()` calls. If the AST Sandbox is inadvertently bypassed or relaxed, the system logs would show "SSL Validation Passed" while the system is actively compromised. *This means SSL must strictly remain an L0/L1 supplement, NEVER a replacement for the Phase 64 AST Sandbox.*
2. **The "Hallucinated Constraint"**: The system logs `L1: Validating against SSL boundary...` but the actual verification logic uses `str.contains()` instead of strict JSON path matching, allowing broad regex bypasses.

## Still to Verify
- The exact prompt injection constraints for the Normalizer to prevent malicious `SKILL.md` from overriding the JSON schema instructions.
- How to force the normalizer to fail-closed if it cannot parse the skill.
