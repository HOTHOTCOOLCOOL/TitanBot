# Phase 38B: Manager-SubAgent Orchestration

**Date**: 2026-04-11  
**Status**: Archived  

## Overview
Phase 38B executed the transition from a monolithic executing agent to a robust **Manager-SubAgent** architectural paradigm. We addressed critical scalability issues including long-text context bloat from subagent output reporting and background worker interactive hangs during HITL (Human-in-the-Loop) safety blocks.

## Technical Details

1. **Outcome-Refining Pipeline (`BaseWorkerBridge`)**:
   - `SubagentManager` and `CoordinatorManager` were refactored to accept an `LLMProvider` injection throughout their lifecycles.
   - Refined `BaseWorkerBridge._announce_result()`: If the subtask is successful and its returned output length exceeds 500 characters, it triggers an intermediary LLM call. This distillation layer compresses raw script output into an ultra-concise summary (`Refined Synthesis`).
   - This fixes the primary limitation of multi-agent designs: raw diagnostic log chaining collapsing the context window of the master agent within 2-3 hops.

2. **Cross-Process Capability Inheritance & HITL Enforcement**:
   - When a worker (whether a coroutine in `SubagentManager` or RPC subprocess in `CoordinatorManager`) loads an isolated `AgentLoop`, its `chat_id` assumes the `worker:xxx` marker.
   - For legacy loops: Evaluates `str(chat_id).startswith("worker:")` during HITL gating. If true, the loop is intercepted natively via `messages.append(Error...)`, blocking high-risk requests while instructing the LLM to resume without dropping execution.
   - For V2 Middleware loops (`hitl.py`): Explicit usage of `ctx.abort("l1_violation", ...)` forces a self-correcting error without interactive prompting.
   - This ensures non-interactive, stateless worker processes don't permanently hang demanding approval input that can't be routed from a user UI.

## Results
- Context window explosion when chaining sub-agent outcomes has been prevented.
- The `hitl.py` intercept rule acts as a strict sandbox boundary guaranteeing no uncontrolled downstream actions from rogue worker instructions.
- Architecture correctly inherits safety profiles while enabling async/background orchestration to parallelize independent subtasks automatically.
