# Epoch 51 & 52: M-RAG & GroupRAG Integration (Phase 51-52)

**Date**: 2026-04-16
**Phases Completed**: Phase 51 (K-V Decoupled Indexing), Phase 52 (Group-Aware Parallel Reasoning)

## Technical Summary

This epoch successfully landed the core patterns necessary for scaling Nanobot's knowledge base and tackling complex arbitrary analysis:

### M-RAG (Phase 51)
- Implemented `MarkerExtractor` which queries the LLM to generate `MetaMarker` entries (Key, Value, Paragraphs) from raw document text.
- Introduced strict SHA256-based caching in `.marker_cache/` to avoid massive recurrent token costs.
- Modified `VectorMemory` to accept `markers` and store the `value` in ChromaDB metadata, while emitting the `key` as the indexable vector document.
- Overhauled `hybrid_retrieve` to strictly decouple `bm25_text_field` ("value") and `dense_key_field` ("key"), normalizing the score fusion.

### GroupRAG (Phase 52)
- Implemented `ComplexityDetector` to deterministically sniff complicated prompts using heuristic rules (Token threshold > 500, Entity count > 8, predefined keywords, or `/parallel` manual trigger).
- Developed `GroupAwareOrchestrator` in `subagent.py` to utilize `asyncio.gather` for spawning parallel `SubagentManager` instances. By wrapping within asyncio tasks, `ContextVar`-based trace isolation was natively maintained.
- Built-in conflict detection: Used a basic keyword overlap / LLM arbitration hook to bubble up `CONFLICTING_CONCLUSIONS` and demand a Human-in-the-Loop decision rather than forcing an artificial consensus.
- Updated `CoordinatorManager.spawn` to conditionally short-circuit to GroupRAG if the prompt triggers high complexity metrics.

## Lessons Learned
*(Note: Active lessons are consolidated into `docs/rules/ARCHITECTURE.md`)*
- `asyncio.gather` is structurally sound for isolating `ContextVar` traces, inherently averting cross-contamination logic inside the agent trace tracker.
- Safely modifying `VectorMemory` for Dense-BM25 decoupling requires the Dense vector to represent the *Key* (so it is embedded and spatially matched) while moving the *Value* to metadata, not vice versa.
