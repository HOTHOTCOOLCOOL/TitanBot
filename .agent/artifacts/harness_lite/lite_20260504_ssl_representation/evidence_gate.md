# Evidence Gate

*Note: As this is a `harness_lite` pre-code design phase, the Evidence Gate evaluates whether the Candidate architecture structurally fulfills the Proof Signals required by the Critic.*

| A# | Status | Evidence / Meaning | Observed Proof Signals (Design Guarantee) | Decision |
| --- | --- | --- | --- | --- |
| A1 | **PASS** | SSL is no longer a security boundary. | Design explicitly removes SSL from `verification.py` and AST Sandbox. It is impossible for SSL to override a code-level deny because they are no longer connected. | **PASS** |
| A2 | **PASS** | `verification.py` structured matching requirement is bypassed via pivot. | By removing SSL from the security boundary, we no longer pretend that `L1 SSL validation` is a mechanism. Thus, A2's premise (that we need to prove structured capability matching) is resolved by abandoning the flawed claim. | **PASS** (Pivoted) |
| A3 | **PASS** | Token compression is structurally mandated. | `candidate.md` mandates `ContextBuilder` to inject ONLY the `Scheduling` layer (max 1000 chars). The dual-injection risk is explicitly eliminated in the design preconditions. | **PASS** |
| A4 | **PASS** | Invalidations cover all code files. | `SkillsLoader` is mandated to use a composite hash of all `.py` and `.md` files in the skill directory, rather than just `SKILL.md` mtime. | **PASS** |
| A5 | **PASS** | Normalizer fail-closed behavior defined. | If normalizer fails, no `skill_ssl` entity is created, and the system falls back to truncated raw `SKILL.md`. Malicious SKILL.md cannot generate a wide-open SSL boundary because SSL is ignored for authorization. | **PASS** |
| A6 | **PASS** | Single source of truth for dependencies. | `depends_on` config array remains the absolute source of truth. SSL Structural layer is purely for observability logging and is not consumed by the loader. | **PASS** |
| A7 | **PASS** | KG entity consumption. | `ContextBuilder` is designed to explicitly query and consume the `Scheduling` subset of the `skill_ssl` KG entity. | **PASS** |

## Final Decision
**PASS**. The Candidate ADR resolves the Critic's security and synchronization concerns by pivoting SSL from a "Security Boundary" to an "Observability and Context Optimization" layer. 

**Next Steps**: Switch to `execute_phase.md` to begin actual implementation and runtime validation.
