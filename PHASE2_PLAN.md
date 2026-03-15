# Phase 2: True Asynchronous Compute Offloading

## Problem Description

Nanobot is built on Python's `asyncio` event loop. While `asyncio` works great for I/O bound tasks (like waiting for API responses from vLLM/Ollama), it completely fails when faced with **CPU-bound tasks**. 
When a CPU-bound task runs inside an `async def` function, it holds the Global Interpreter Lock (GIL) and blocks the entire event loop. During this time:
1. The bot cannot respond to Discord/Telegram messages.
2. The heartbeat cron timer stops ticking.
3. Health checks fail.
4. The system feels "frozen" to the user.

**Known CPU-Bound bottlenecks in Nanobot:**
1. Text extraction from massive PDFs or intricate `.xlsx`/`.docx` files (`attachment_analyzer.py`).
2. Heavy Pandas DataFrame manipulations or CSV crunching.
3. Complex SSRS Report HTML parsing and `fpdf2` PDF generation.
4. Local small embedding model inferences (if run directly in python rather than via API).

## Proposed Solution: True Offloading

We need to offload these heavy parsing workloads entirely outside the main `asyncio` event loop.

### Option A: `concurrent.futures.ProcessPoolExecutor` (Preferred for Zero-Dependency)
- We spin up a lightweight, long-lived `ProcessPoolExecutor` inside the main process manager (e.g. `loop.py` or a dedicated `ComputeManager`).
- When `attachment_analyzer.py` is asked to parse a 50MB PDF, it uses `await asyncio.get_running_loop().run_in_executor(process_pool, extract_pdf_sync, file_bytes)`.
- **Pros:** Built into Python, zero external dependencies. Bypasses the GIL entirely.
- **Cons:** Shared memory is tricky; we must pass only serializable primitive data (e.g., bytes in, raw text out).

### Option B: Redis + Celery / RQ (Enterprise grade)
- Decouple the worker completely into a separate background service.
- **Pros:** Extremely scalable, highly resilient.
- **Cons:** Overkill for a local-first Nanobot application; requires Windows users to install Redis and spin up a Celery worker. (Contradicts our "Single-Agent Routing... zero framework bloat" philosophy).

### Recommended Implementation (Zero-Bloat Process Pool)

#### 1. Implement a Global `ComputeBroker`
- Create `nanobot/compute.py` containing a `ProcessPoolExecutor` singleton.
- Expose a clean async API: `await run_cpu_heavy(func, *args)`.

#### 2. Refactor `attachment_analyzer.py`
- Abstract the core parsing logic (e.g., `PyPDF2` extraction, `openpyxl` looping) into pure, synchronous functions that take bytes/paths and return strings.
- Wrap these synchronous functions with calls to `ComputeBroker`.

#### 3. Refactor SSRS PDF Generation (`fpdf2`)
- The `ssrs` tool's HTML-to-PDF conversion is notoriously CPU heavy. Move this pure synchronous operation into the `ProcessPoolExecutor`.

## Status
**COMPLETED (2026-03-01)**
- `ComputeBroker` singleton implemented and integrated into the core `AgentLoop` shutdown sequence.
- `attachment_analyzer.py` refactored to offload CPU-heavy parsing (`PdfReader`, `pandas`, `docx`) to the process pool.
- Validated via `test_compute_broker.py` that the event loop heartbeat remains perfectly unblocked during massive dummy data processing.

> [!NOTE]
> SSRS HTML-to-PDF (`fpdf2`) optimization: Since `fetch_report.py` is invoked via `ExecTool` (which uses `asyncio.create_subprocess_shell`), it already runs in a separate OS process and does not block the bot's GIL. Converting this to use `ComputeBroker` natively was deferred to a later phase per user request.
