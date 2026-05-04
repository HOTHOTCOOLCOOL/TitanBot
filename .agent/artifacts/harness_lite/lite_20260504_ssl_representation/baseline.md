# Baseline

## Claim / Evidence / Status
- **Claim 1**: SSL representation improves pre-execution risk assessment by explicitly exposing Structural and Logical boundaries (action/resource limits). 
  - **Evidence**: Paper 2604.24026v3 evaluations. 
  - **Status**: Externally validated, needs internal mapping to Nanobot's architecture.
- **Claim 2**: Nanobot relies heavily on AST-level Pre-flight Skill Verifier (ADR-56) but lacks structured index-time boundaries. 
  - **Evidence**: `docs/adr/ADR-56-preflight-skill-verifier.md` defines zero-capability execution environment. 
  - **Status**: Fact.
- **Claim 3**: Nanobot's Knowledge Graph supports `reasoning_template` entities and can be extended with new entity types. 
  - **Evidence**: Recent Phase 68/Job 20260503 `ReasoningSkill KG Prompt Budget` integration. 
  - **Status**: Fact.

## Source of Truth Files
- `nanobot/agent/skills.py` (Skill loading & registration logic)
- `nanobot/agent/verification.py` (PSV and security boundaries)
- `nanobot/agent/context.py` (Prompt budget and ContextBuilder)

## Runtime Artifacts / Hidden Runtime States
- Knowledge Graph persistent storage (JSON/Vector representations of the entities).
- Memory Manager state tracking the registration pipeline of a new skill.
- Token budget counters in `ContextBuilder`.

## Observable Proof Signals
1. During skill registration, logs confirm: `L0: Normalizing SKILL.md to SSL graph...`
2. KG storage explicitly writes a `skill_ssl` entity with the 3 layers (`Scheduling`, `Structural`, `Logical`).
3. During runtime, `verification.py` queries the SSL graph: `L1: Validating against SSL boundary...`

## Unknowns
- Exact token cost and latency of running the LLM normalizer for every skill upon registration/update.
- Mechanism to synchronize SSL graphs if the underlying Python code is modified but the `SKILL.md` is not updated.

## Questions the Critic Must Attack
1. Does relying on an LLM normalizer to build the SSL graph introduce a new prompt injection vulnerability where malicious `SKILL.md` text can trick the normalizer and bypass PSV?
2. If the SSL logical layer contradicts the AST execution layer (e.g., normalizer says "safe", AST says "uses os.system"), how do we ensure "fail-closed" behavior?
3. Is this mechanism creating "security theater" if the LLM normalizer hallucination rate is high?
