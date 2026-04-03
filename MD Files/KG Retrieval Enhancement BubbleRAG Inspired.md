# Phase 34: KG Retrieval Enhancement (BubbleRAG-Inspired)

This plan implements three lightweight, high-ROI retrieval enhancements drawn from the BubbleRAG Paper Analysis report, focusing on increasing multi-hop recall and precision without adding architectural/graph-database overhead.

## User Review Required

> [!IMPORTANT]
> Since this modifies core retrieval logic (`hybrid_retriever.py`, `knowledge_graph.py`, `loop.py`, `context.py`), please review the approach for passing implicit concepts and applying coverage penalties.

## Proposed Changes

---

### Knowledge Graph Context (P34-1 & P34-3)

#### [MODIFY] [knowledge_graph.py](file:///d:/Python/nanobot/nanobot/agent/knowledge_graph.py)
1. **P34-1 (Implicit Concepts Extraction):** Add a new `async def infer_implicit_concepts(self, provider, model, query) -> list[str]` method. This lightweight LLM call will infer necessary but unstated background contexts (e.g., "1921 Nobel" -> ["Einstein", "Physics"]).
2. **P34-1 & P34-3 (Semantic Anchor Grouping & Relaxation):** Update `get_entity_context(self, query: str, implicit_concepts: list[str] = None)`:
   - Apply matching scores not just to `query_words` but also to `implicit_concepts`.
   - **Schema Relaxation:** If the vector database top results (from `semantic_boost`) heavily feature multiple keyword occurrences, scale the confidence multipliers up slightly, allowing partial string matches to succeed and lowering the threshold (simulating schema/constraint relaxation).

---

### Hybrid Retrieval (P34-2)

#### [MODIFY] [hybrid_retriever.py](file:///d:/Python/nanobot/nanobot/agent/hybrid_retriever.py)
1. **P34-2 (Coverage Penalty):** BubbleRAG uses an exponential penalty for structurally incomplete evidence graphs. We will apply this to task/experience matching:
   - Tokenize the query into `query_words` and item text into `item_words`.
   - Calculate `coverage = len(query_words & item_words) / len(query_words)`.
   - Introduce an exponential decay penalty: `penalty = math.exp(coverage_penalty_alpha * (1.0 - coverage))`.
   - Update the combined score: `final_score = combined_raw_score / penalty`.
2. Add `coverage_penalty_alpha = 1.0` as a configurable parameter to `hybrid_retrieve`.

---

### Agent Loop Injection Pipeline

#### [MODIFY] [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py)
1. In `_execute_with_llm`, asynchronously invoke `infer_implicit_concepts` to get background context before building the system prompt.
2. Specifically, near line 1173 (where query rewriting happens), add:
   ```python
   # Phase 34: Semantic Anchor Grouping (Implicit concepts)
   implicit_concepts = []
   if config.agents.memory_features.knowledge_graph_enabled:
       kg = self._get_knowledge_graph()
       implicit_concepts = await kg.infer_implicit_concepts(self.provider, self.model, search_query)
   ```
3. Pass `implicit_concepts` kwargs down to `self.context.build_messages()`.

#### [MODIFY] [context.py](file:///d:/Python/nanobot/nanobot/agent/context.py)
1. Update `build_messages` signature to accept `implicit_concepts: list[str] | None = None`.
2. Update the `KnowledgeGraph` invocation logic near line 248:
   ```python
   kg_context = kg.get_entity_context(kq_query, implicit_concepts=implicit_concepts)
   ```

## Open Questions

> [!NOTE]  
> Are there specific domains/topics where you expect **Schema Relaxation** to be most helpful during daily usage? I will add debug logs when it activates so we can monitor its behavior over time.

## Verification Plan

### Automated Tests
- Run `pytest tests/knowledge/test_hybrid_retrieval.py` (if coverage exists) to confirm no breaking changes.
- Ensure `test_experience_bank` passes.

### Manual Verification
- Ask the agent a multi-hop query (e.g., "What is the capital of the country where the author of BubbleRAG is located?") using the dashboard UI.
- Verify through console logs that `infer_implicit_concepts` successfully extracts latent entities ("HKUST-GZ" / "China" / "Beijing") and injects them into the KG context assembly.
