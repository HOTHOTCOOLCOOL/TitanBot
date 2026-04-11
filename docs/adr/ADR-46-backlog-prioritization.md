# ADR-46: H2 Backlog Prioritization & Phase 38 Refactoring Plan

**Date**: 2026-04-11
**Status**: Accepted

## Context
Following the completion of Phase 44 (Cron Retry Engine) and Phase 45 (Dynamic Sandbox & Capability Tags), establishing a secure and stable execution baseline, an evaluation of the remaining backlog items (Phase 36, 37, 38) was necessary to determine the next immediate focus and avoid over-engineering. The evaluation was conducted through the 5-stage Harness Dialectic Method.

## Decision

### 1. Phase 37 (Execution Trace Archive) - ✅ Completed / Removed from Backlog
The core value of Trace Archives and Meta-Harness has been fully delivered by the existing JSON append-only logger (`trace_archive.py`) acting in tandem with the Verification Layer's L3 Post-Mortem extraction into the Experience Bank. Introducing SQLite or `TraceQueryTool` into the runtime would violate the "zero runtime pollution" contract and risk infinite recursive loops.
**Action**: Marked as completed/delivered.

### 2. Phase 36 (OS Sandbox via Bubblewrap) - 🔵 Downgraded & Rescoped
The proposal to build cross-platform OS-level isolation (e.g., Bubblewrap) was identified as significant over-engineering for the current scope. A robust L1/L2 capability tag sandbox currently exists. Additionally, Docker remains the primary unbypassed OS boundary.
**Action**: Scoped down from "OS Sandboxing" to "Worker Process Security Hardening v2 (Docker seccomp)". Priority reduced to P3 Backlog, strictly coupled to potential Linux production deployments, and no longer applicable to Windows.

### 3. Phase 38 (Coordinator Mode) - 🚀 Elevated to Highest Priority & Split
Moving from monolith execution to a Manager-SubAgent paradigm is the strategic breakthrough needed to combat context bloat and enable parallel tasks. However, code inspection revealed deep fragmentation between `SubagentManager` (tasks via coroutines) and `CoordinatorManager` (tasks via subprocesses RPC) that must be unified first. Furthermore, safe propagation of HITL logic and LLM model initialization must be established.
**Action**: Split into two structured phases:
- **Phase 38A**: Unify Manager abstractions (`BaseWorkerBridge`, `WorkerToolset`). Repay technical debt and standardize the JSON-RPC interface to support heterogeneous models and trace contexts.
- **Phase 38B**: Manager-SubAgent orchestration. Implement outcome-refining pipelines (compressing subagent outputs using lightweight LLMs) and cross-process capability inheritance (withholding High-Risk actions from workers instead of propagating full HITL dialogues).

## Consequences
- The development roadmap is strictly refocused away from unnecessary security overkill towards scalable task orchestration.
- Phase 38A will require brief internal refactoring before new multi-agent features are introduced. 
