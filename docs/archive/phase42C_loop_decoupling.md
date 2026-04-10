# Phase 42C Epoch: Loop.py God Class Decoupling [首批]

## Goal
To aggressively refactor the monolitic `nanobot/agent/loop.py` towards a modular pluggable architecture by decoupling the Intent Classification and target VLM Routing into their own static isolation module (`nanobot/agent/routing.py`).

## Changes
- **Extracted VLM Routing**: Removed duplicate ~60 lines of logic handling `target_model_override`, LRU Provider Caching (`_vlm_provider_cache`), and VLM recency bounding window checking from `_run_agent_loop` and `_call_llm_for_turn`. 
- **Centralized ModelRouter**: Abstracted into `nanobot.agent.routing.ModelRouter.determine_target_model()`, ensuring the cache dictates execution.
- **Extracted Intent Classifier**: Moved `_CHITCHAT_REGEX` away from the loop root into `nanobot.agent.routing.IntentClassifier.detect_intent()`, reducing redundant text-parsing execution in both `_process_message` and `_execute_with_llm`.
- **Decoupled Tests**: Resolved an environmental ghost failure in `test_architecture.py` due to implicit dependency changes out of nowhere.

## Issues Identified & Resolved
- **LRU Implicit Side Effects**: Identified that `OrderedDict` (`_vlm_provider_cache`) relies fundamentally on `move_to_end()` mutating state inside the decoupled function. We resolved this via `OrderedDict` pass-by-reference mutation and documented it in `ARCHITECTURE.md` to prevent subsequent logic extractions from silently suppressing the LRU behaviors.
- **Architectural Debt Tidy-Up**: Brought green status back to out-of-date P3 Channel tests that had disconnected registries.

## Future Recommendations
- Pushing further into God Class refactoring: `_execute_with_llm` and `ToolExecutor` still handle massive responsibilities. Phase 43 should push them completely out to standalone onion-middleware intercepts.
