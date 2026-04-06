# TitanBot Architectural Migration Plan (Final)

This plan outlines the refactoring of TitanBot's `loop.py` (God Object) into a modular, maintainable architecture based on the upstream HKUDS/nanobot `Hook/Runner` pattern. It addresses critical feedback regarding execution dependencies, hook limitations, and the decomposition of the massive `_process_message` method.

## User Review Required

> [!WARNING]
> This plan proposes modifying the `AgentHook` API to support control-flow interruptions (necessary for HITL and Circuit Breakers), which diverges slightly from upstream. Please review Phase 2 closely.

> [!CAUTION]
> The synchronous message consumption model will be replaced with an async task dispatcher (Phase 1). This is a foundational change that modifies how messages are queued and locked.

## Proposed Changes

---

### Phase 1: 异步调度基石与 Message Pipeline 重构 (Routing & Dispatch)

**Objective**: Resolve the Phase Order Inversion by establishing the async dispatch model and decomposing `_process_message` before introducing the Runner.

#### [MODIFY] `nanobot/agent/loop.py` -> `nanobot/agent/pipeline.py` (New)
* **Async Dispatcher**: Refactor the main `run()` method from a simple `while` loop to an `asyncio.create_task` dispatcher.
* **Message Pipeline**: Decompose the 470-line `_process_message` into a chain of Middlewares (Pipeline Pattern):
    * `SystemMessageMiddleware`
    * `CommandRouterMiddleware` (Using upstream's `CommandRouter` and `/stop`)
    * `ChitchatBypassMiddleware` (Phase 39 Fast Intent Routing)
    * `KnowledgeMatchMiddleware` (Implicit feedback & exact match handling)
    * `HITLApprovalMiddleware` (Remote & Local HITL routing)
    * `RunnerDelegationMiddleware` (Passes control to AgentRunner)
* **Concurrency Control**: Introduce `_session_locks` and `_concurrency_gate` (Semaphore) around the execution of the Pipeline to ensure thread-safety and bound concurrent LLM calls.

---

### Phase 2: 定制化 Runner 与 Hook API 升级 (Execution Engine)

**Objective**: Adapt the upstream Runner/Hook pattern to support TitanBot's advanced termination rules (HITL, Circuit Breaker).

#### [NEW] `nanobot/agent/runner.py` & `nanobot/agent/hook.py`
* **Hook API Upgrade**: Modify the `AgentHook` API to allow returning a `ControlFlow` object (e.g., `Continue`, `BreakLoop(reason, content)`, `Suspend(state)`).
    * `before_execute_tools` can return `Suspend` (for HITL).
    * `before_iteration` can return `BreakLoop` (for Circuit Breakers).
* **Token-Budget Snip reconciliation**: Implement `_snip_history` inside `Runner` but add logic to disable our hardcoded `max_messages=10` or sync them safely (e.g. use token budget globally, dropping the fixed message count).

---

### Phase 3: 安全层与鲁棒性机制的 Hook 化 (Security & Verification)

**Objective**: Migrate TitanBot's 4-layer verification into the new Hook architecture.

#### [MODIFY] `nanobot/agent/verification.py` -> Hooks
* **`SecurityHook` (L1)**: Injects rigid rule checking into `before_execute_tools`. If it fails, modifies the LLM context and prevents execution.
* **`HITLHook`**: Evaluates tool risk. If manual approval is required, returns `Suspend(short_id)` to pause the Runner.
* **`LoopDiagnosticHook`**: Tracks `_recent_call_sigs` across iterations (stored in `AgentHookContext` or custom state object) to detect infinite and fuzzy loops. Triggers Trace extraction on failure.

---

### Phase 4: 记忆系统与知识流重构 (Memory & Context)

**Objective**: Integrate memory systems without introducing heavy, incompatible dependencies like GitStore.

#### [MODIFY] `nanobot/agent/memory.py` (Upstream)
* **Refined Dream Process**: Port upstream's `Consolidator` trigger by Token Budget instead of fixed message counts, but pipe it into our native `ReflectionStore` and `ExperienceBank` instead of upstream's simple textual memory.
* **Drop GitStore**: We explicitly reject `dulwich` / GitStore. Our DB and JSON stores (Vector/KG) will handle their own state/backups without file-level git tracking.
* **L0 Context Enrichment Hook**: Move `verification.py`'s `enrich_context` (injecting experiences and reflections) into a `PrecognitiveHook` triggered at `before_iteration`.

---

### Phase 5: API Gateway 与边缘收尾 (Ecosystem)

**Objective**: Only after the core is stable, expose the API and unify configs.

#### [NEW] `nanobot/api/server.py`
* Port upstream's OpenAI-compatible HTTP server, pointing it to our newly stabilized `AgentRunner`.

#### [MODIFY] `nanobot/config/schema.py`
* Refactor channel configs to use strongly typed dynamic module loading instead of upstream's generic `extra="allow"` to maintain strict validation while supporting modular channel adapters.

## Verification Plan

### Automated Tests
* Execute the full `pytest` suite focusing on `test_pipeline.py`, `test_runner.py`, and `test_hooks.py` once created.
* Ensure L1 Sandboxing strictly rejects destructive commands in CI.

### Manual Verification
* Trigger a fast Chitchat bypass to ensure L0 Routing works sub-second.
* Trigger a high-risk command to verify the HITL Hook correctly suspends the Runner, sends a remote approval, and resumes effectively.
* Run a complex RPA task that fails repeatedly to verify the `LoopDiagnosticHook` breaks the loop and extracts a Post-Mortem.
