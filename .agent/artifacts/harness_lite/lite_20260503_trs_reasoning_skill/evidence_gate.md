# Evidence Gate

| A# | Status | Evidence | Meaning |
| --- | --- | --- | --- |
| **A1 (HITL Boundaries)** | PASS | The final candidate abandons `auto_reviewer.py` autonomous extraction. We rely exclusively on the existing `KnowledgeGraph` manual curation or explicit agent tool calls to add knowledge. No new autonomous promotion paths are introduced. | Security boundaries and single-agent constraints are perfectly preserved. |
| **A2 (Authoritative Storage)** | PASS | `ReasoningSkill` is defined strictly as a standard entity in the Knowledge Graph with `type="reasoning_template"`. Read/write functions are the existing `KnowledgeGraph` methods. `skills.py` is untouched. | Divergence and ranking ambiguity are eliminated. |
| **A3 (Pre-call Budget)** | PASS | The injection occurs during the existing `kg_context` generation in `nanobot/agent/context.py:273-298`. We apply an explicit 1000-character truncation for reasoning templates before adding them to `system_prompt`, bypassing the IFCC hand-wave. | Context crowding is deterministically prevented. |
| **A4 (Safe Degradation)** | PASS | By using the existing `KnowledgeGraph` retrieval, it inherently uses the same confidence/ranking thresholds as normal RAG. If no strong match exists, no template is retrieved, and the model relies on its base capabilities safely. | Negative transfer is minimized and managed by existing thresholds. |
| **A5 (Insertion Compatibility)** | PASS | We reuse the exact `kg.get_entity_context()` call path in `context.py:290`. No new injection lanes are created; it perfectly conforms to the current progressive loading pattern. | Modification scope is practically zero for architectural paths, only adding a new entity type convention. |

## Decision: PASS
All critical findings from the Critic have been addressed. The candidate leverages existing, evidence-backed systems (Knowledge Graph, Hybrid Retrieval) without inventing unevidenced pipelines or violating the prompt budget. The design is safe to implement.
