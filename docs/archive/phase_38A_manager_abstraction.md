# Phase 38A: Manager Base Abstraction & JSON-RPC Standardization

**Date**: 2026-04-11  
**Status**: Archived  

## Overview
Phase 38A targeted the unification of the `SubagentManager` (coroutine-based) and `CoordinatorManager` (subprocess-based) into a common abstraction (`BaseWorkerBridge`), preventing context sprawl and duplicate boilerplate inside the worker initialization process.

## Technical Details
1. **BaseWorkerBridge (`nanobot/agent/worker/bridge.py`)**:
   - Extract `_announce_result()` out of the two managers into a single inherited method.
   - Extract the restrictive proxy logic `build_worker_toolset()` to securely spawn worker agents devoid of `spawn`, `message`, `exec`, and `coordinator` rights.

2. **Heterogeneous Model Support via JSON-RPC**:
   - Upgraded `CoordinatorManager.spawn` POST payload from a simple `{task, task_id}` to fully encapsulate context metadata: `model`, `temperature`, `max_tokens`, `brave_api_key`.
   - Before Phase 38A, the `WorkerNode` would load the static `defaults.model` in its constructor, causing heterogeneous routing instructions to be lost upon reaching the Worker boundary.
   - Refactored `WorkerNode._execute_agent_loop` to dynamically load `ProviderFactory.get_provider()` and `AgentLoop()` **per-request**, safely tearing down state parameters without leaking context into subsequent polling bounds.

3. **Decoupled Tools**: 
   - `SpawnTool` (which triggers child tasks) is now loosely coupled against `BaseWorkerBridge` instead of the rigid `SubagentManager` type, allowing future replacement using True Process-Level Coordinator.

## Results
- Cleaned technical debt around the dual implementation of workers.
- Addressed `AsyncMock` vs `__aenter__` mocking failure in tests that resulted from HTTP context propagation.
- System is now fully prepared for Phase 38B: outcome-refining pipelines and IPC-based SubAgents.
