# Nanobot Project Tracker & Architecture Guide

**🚨 LLM Instructions:** Read this document to rapidly understand the system state, architecture rules, and the ultimate roadmap. **Keep answers concise and prioritize the "Ultimate Goal/Next Steps" when taking on new tasks.**

## 1. Ultimate Vision & Core Philosophy

**Goal:** Build a robust, enterprise-grade, localized, autonomous Personal AI Assistant capable of seamless cross-channel automation without complex intermediate framework overhead.

- **Single-Agent Routing:** One core loop (`loop.py`), zero framework bloat. Equips the LLM with robust Python tools to make autonomous decisions.
- **Knowledge Workflow (`knowledge_workflow.py`):** 
  - User Request -> Lightweight Key Extraction -> Local JSON Similarity Match -> Few-Shot Injection. 
  - Records high-quality implicit feedback directly from users. 
  - **Auto-Sublimation:** Automatically prompts to upgrade a successful workflow pattern (used ≥3 times) to a standalone Python Skill.
- **Proactive Execution Constraints:** 
  - Strictly enforces tool usage and auto-recovers from LLM "fake completion" or "pure wait" hallucination loops.
  - Requires the LLM to read `SKILL.md` before executing new skills (prevents hallucinated scripts and blind trial/error).

## 2. Directory Structure & Key Components

- `nanobot/agent/`: Core LLM interactions (`loop.py`), Knowledge Workflow, and Tool executions.
- `nanobot/agent/tools/`: Core built-in tools (`exec`, Python execution, `outlook.py`, `ssrs`, `attachment_analyzer.py`).
- `nanobot/plugins/`: **Dynamic plugin directory.** Drop any `.py` file containing a `Tool` subclass here — it will be auto-discovered at startup or via `/reload`. Use `python -m nanobot.onboard <skill>` to install from `resources/`.
- `nanobot/bus/`: Internal Event/Message Bus handling decoupled asynchronous routing.
- `nanobot/channels/`: I/O interfaces (`ChannelManager`, Email IMAP/SMTP, Discord, Telegram, Whatsapp, CLI). **Crucial for multi-platform reach.**
- `nanobot/cron/`: Background scheduled task engine (`service.py`). Manages recurrent jobs and triggers the agent automatically.
- `nanobot/session/`: Chat history management, caching, and state tracking per channel/user.
- `resources/`: Mature, portable Skills stored here as verifiable backups and templates (e.g., `ssrs-report`, `outlook-email-analysis`). Use `onboard.py` to install into `plugins/`.
- `nanobot/config/`: Configuration management (`.env` -> `config.json` cascading overlay).

## 3. Current System Capabilities (Production Ready)

* **Model Agnosticism (`registry.py`):** Unified provider backend (vLLM, Ollama, OpenRouter). Full support for reasoning models (e.g., DeepSeek-R1) with built-in `<think>` tag extraction/filtering that prevents JSON parsing breaks.
* **Outlook & System Automation:** 
  - Fully isolated Python COM threading (`asyncio.to_thread` + `CoInitialize`) guaranteeing sub-second responsiveness, preventing Windows Explorer UI lag, and eliminating MAPI memory leaks.
  - Sub-second email/attachment querying, reading, document filtering, and email sending.
* **Complex File Parsing (`attachment_analyzer.py`):** 
  - Universal text extraction across PDF, docx, xlsx, txt, and CSV to feed data directly into the LLM context.
* **SSRS Internal Reporting:** 
  - Configuration-driven (`reports_registry.json`) automated extraction of Windows SSPI-authenticated SQL Server reports.
  - Smart parsing of HTML4.0/CSV and immediate `fpdf2` PDF generation.
* **Cron Scheduling & Daily Memory:**
  - Automated recurrent job scheduling directly requested via natural language.
  - Memory system that natively logs daily activities (`MEMORY.md` & `YYYY-MM-DD.md`) and passes them into context for strong temporal awareness.
* **Proactive Skill Harvesting:** Auto-utilizes `npx clawhub` or similar native scripts to seek community extensions when built-in tools fall short.

## 4. Porting Skills (The `resources/` Pool)

When instructed to replicate or expand capabilities, **DO NOT reinvent the wheel**. Copy existing patterns:
*   `ssrs-report`: For reporting and PDF generation.
*   `outlook-email-analysis`: For extracting and parsing email attachments.
*   `outlook-email-search`: For filtered querying.

*Guideline:* E.g., if extending SSRS capabilities, prioritize editing `reports_registry.json` rather than hacking core Python scripts.

## 5. Strategic Roadmap & Next Steps (Active Backlog)

To realize the enterprise-level Ultimate Goal, maintain momentum on these core feature epics:

- [x] **Cron Fault Tolerance (Completed):** Enhanced the cron scheduler with a robust heartbeat timer (bypassing PC sleep freezes) and hard persistency logs to ensure missed jobs are perfectly recovered and executed without double-triggering.
- [x] **True Asynchronous Compute Offloading (Phase 2):** Moved heavy CPU-bound tasks (e.g., complex PDF/Excel text extraction via `attachment_analyzer.py`) to a separate OS process via `ComputeBroker` (`concurrent.futures.ProcessPoolExecutor`) to completely prevent the async event loop and heartbeat from stuttering.
  - *Note: SSRS HTML-to-PDF (`fpdf2`) optimization (native conversion to `ComputeBroker` instead of `ExecTool` shell) is deferred to a later phase.*
- [x] **Dynamic Skill Hot-Loading (Phase 3):** Implemented a true plug-and-play architecture via `plugin_loader.py` that dynamically discovers and registers `Tool` subclasses from the `nanobot/plugins/` directory at startup. Includes `/reload` chat command for hot-reloading without restart, `onboard.py` utility for installing skills from `resources/`, and full error isolation (bad plugins cannot crash the bot).
- [x] **Vector Store for Long-Term Memory (RAG):** Integrated local `ChromaDB` and `sentence-transformers` (`all-MiniLM-L6-v2`) to retrieve historical context via semantic search, avoiding LLM token bloat. Fully offline and privacy-first model loading.
- [x] **Personalized Long-Term Memory (Memory Distiller):** Extracted L1 core preferences via asynchronous LLM distillation (`preferences.json`) to aggressively optimize the System Prompt context, keeping bulk knowledge cleanly isolated in L2 RAG.
- [x] **Knowledge Skill Evolution (Phase 9):** Versioned knowledge entries, automatic merge for similar tasks, silent step updates on success, `/kb` management commands, and ChromaDB semantic fallback (>100 entries). Turns Nanobot's existing Knowledge→Skill pipeline into a true lifelong learning system. (40 tests, all pass)
- [x] **Code Quality & Maintainability Optimization:** Unified logging framework (loguru), removed debug file dumps, fixed bare exception handling, added 46 new tests (Config schema validation, SessionManager CRUD, LiteLLM provider parsing), SessionManager LRU cache (maxsize=128), Config instance caching, lightweight performance metrics collector (`utils/metrics.py`), and structured LLM/Tool timing logs. Regression baseline: 397 passed.
- [x] **Deep Optimization (Phase 11):** Removed dead code from `loop.py` (-77 lines), extracted inline constants to module-level, added cumulative LLM token usage tracking to metrics (`/stats` command), and implemented exponential backoff retry (max 2 retries) for transient LLM errors (timeout/5xx/connection). 29 new tests. Regression baseline: 460 passed.
- [x] **Multi-Modal Vision & Hybrid RPA Architecture:** Expand the toolset to parse image attachments, UI screenshots, and automate apps.
  - *Completed (Short-Term):* "Text-matching" RPA implementation via `ui_name` parameter, allowing the LLM to directly click named UI elements discovered by UIAutomation without invoking expensive VLM APIs.
  - *Completed (Mid-Term):* Integrated `PaddleOCR` and a 3-layer perception architecture as a fallback when Accessibility API fails to extract text.
  - *Completed (Fix):* Added absolute-to-relative coordinate translation in `screen_capture.py` / `ui_anchors.py` to support multi-monitor RPA Set-of-Marks UI element clicking.
  - *Completed (Long-Term):* Integrated YOLO UI element detection (Layer 3) via `yolo_detector.py` with Salesforce GPA-GUI-Detector model. Auto-downloads model from HuggingFace, deduplicates against UIA/OCR elements, renders green Set-of-Marks annotations. Config: `agents.vision.yolo_enabled`.
- [x] **Memory System Enhancement (mem9-inspired):** Unified `memory` CRUD tool (store/search/delete with tags), session-end summary hook, memory intent detection ("记住"/"remember" trigger phrases), `/memory export/import` commands, and memory storage strategy injection into system prompt. (33 tests, all pass)
- [x] **Knowledge System Upgrade (Phase 12 — AutoSkill + XSKILL inspired) (Completed):** Structured knowledge representation (triggers/tags/description/anti_patterns/confidence), Dense+BM25 hybrid retrieval replacing pure jieba+Jaccard, Experience Bank dual-stream design (Skill = task-level workflows, Experience = action-level tactical prompts), and Knowledge Management Judge (add/merge/discard decisions). Inspired by AutoSkill (ECNU, 2603.01145v2) and XSKILL (HKUST, 2603.12056v1).
- [x] **Retrieval Enhancement (Phase 13):** Query rewriting for multi-turn coreference resolution, retrieval-time adaptation (pruning/rewriting retrieved knowledge to fit current context before injection).
- [x] **Engineering Hygiene (Phase 14):** Root directory cleanup (archive 90+ `llm_payload_*.json`, consolidate test files into `tests/`), `loop.py` further modularization (target <700 lines), comprehensive type hints for core modules.
- [x] **Human-in-the-Loop Web Dashboard (Phase 15):** Built a lightweight Web UI (FastAPI + HTML/JS) to visualize Agent activity logs in real-time via WebSockets, manually edit the Knowledge Base (`tasks.json`) and `MEMORY.md`, and view system metrics.
- [x] **Unified Master Identity & Security (Phase 15):** Pivoted from enterprise multi-tenancy to an Ultra-Lightweight Personal AI Assistant model. Implemented `master_identities` mapping to link cross-channel sessions and deeply enforced `allowFrom` strictly across channels.
- [x] **Bug Fixes & Modularization (Phase 16):** Fixed 2 P0 runtime bugs: `match_experience()` undefined-variable crash (Experience Bank silently non-functional), `context.py` `asyncio.run()` inside running loop (Query Rewriting never executed). Extracted shared BM25+Dense hybrid retrieval engine (`hybrid_retriever.py`), Mochat pure helpers (`mochat_utils.py`), made embedding model path configurable (`agents.defaults.embeddingModel`), and internationalized 3 hardcoded Chinese agent-loop prompts via `i18n.py`. Regression: 474 passed.
- [x] **Root Cleanup & Architecture Enhancement (Phase 17):** Archived 23 stale root files (8 docs, 10 logs, 5 scripts → `archive/`). Added `get_metrics()` export to `metrics.py` (fixes Dashboard `/api/stats`). Added error recovery counters (`metrics.increment`) in 4 critical catch blocks across `knowledge_workflow.py` and `loop.py`. Created Dashboard API test suite (`test_dashboard_api.py`, 10 tests covering all 8 endpoints). Expanded Experience Bank tests with 5 edge cases. Regression: 495 passed.
- [x] **P0 Critical Security Fixes (Phase 18A):** Fixed 6 critical vulnerabilities from security audit: (S1) removed real API key from `.env`, (S2+S5) added Bearer Token authentication to all Dashboard endpoints + WebSocket, (S3) added 14 shell deny patterns for network exfiltration/encoded PowerShell/pipe-to-shell/reverse shells + default `restrict_to_workspace=True`, (S4) fixed path traversal via `is_relative_to()`, (S6) changed gateway default binding from `0.0.0.0` to `127.0.0.1`. New tests: `test_dashboard_auth.py` (13 tests), `test_shell_hardening.py` (20 tests). Regression: 529 passed.
- [x] **P1 Medium Security Fixes (Phase 18B):** Fixed 4 medium-priority security issues: (S7) one-time startup warning when `allowFrom` is empty, (S8) cached `master_identities` at class level to eliminate per-call `load_config()` I/O, (S9) sanitized error messages (generic user-facing message, full traceback to logs only), (S10) SSRF protection blocking RFC1918/loopback/link-local/metadata IPs in `web_fetch`. New tests: `test_ssrf_protection.py` (12 tests), `test_channel_security.py` (7 tests). Regression: 549 passed.
- [x] **P2 Code Quality & Bug Fixes (Phase 18C):** Fixed critical `/reload` command bug (`commands.py` called non-existent `agent._register_dynamic_tools()` → now imports module function from `tool_setup.py`). Hoisted per-call `_MEMORY_TRIGGERS` to module constant, fixed shadowed walrus variable in `memory_manager.py`, moved late `import re` to module top in `personalization.py`, removed redundant assignment in `state_handler.py`, added `__all__` exports to `tool_setup.py` and `hybrid_retriever.py`. New tests: `test_code_quality.py` (17 tests). Regression: 566 passed.
- [x] **P3 Architecture Improvements (Phase 18D):** Refactored `ChannelManager._init_channels()` from 9 repetitive if/try/except blocks into a data-driven `_CHANNEL_REGISTRY` list with single loop (-80 lines). Replaced brittle `isinstance` checks in `_set_tool_context()` with duck-typed dispatch over `_CONTEXTUAL_TOOLS` tuple. Added `__all__` exports to 6 public modules (`context.py`, `commands.py`, `state_handler.py`, `session/manager.py`, `channels/manager.py`, `metrics.py`). Added `uptime_seconds()` metric to `MetricsCollector`, included in `report()`/`get_metrics()` output. New tests: `test_architecture.py` (33 tests). Regression: 599 passed.
- [x] **Performance & Experience Optimization (Phase 19+):** Async parallel tool execution via `asyncio.gather` in `loop.py` (multi-tool turns now run concurrently). Context window optimization with character-budget history trimming in `context.py` (120K char default, keeps ≥4 recent messages). Dashboard v2 mobile-responsive UI with hamburger sidebar, stat cards, toast notifications, and XSS-safe rendering. Proactive cron failure notification system — `CronService.notification_callback` pushes alerts to dashboard WebSocket and the job's configured channel on failure. New tests: `test_phase19_optimizations.py` (10 tests). Regression: 602 passed.
- [ ] **Knowledge Workflow Refactoring (Phase 19+ Remaining):** Extract user command recognition, prompt formatting, KB management commands, and outcome tracking out of `knowledge_workflow.py` into separate modules to slim it down from ~695 lines.

## 6. Phase 20: AI Memory Architecture Enhancement (Next)

Inspired by *"Survey on AI Memory: Theories, Taxonomies, Evaluations, and Emerging Trends"* (Ting Bai et al., 2026). The paper's 4W taxonomy validates Nanobot's lifecycle/content-type coverage; the following 7 improvements target identified gaps.

### P0 — High Priority (Low effort, high ROI)

- [ ] **20A: Evicted Context Buffer (MemGPT-style Virtual Paging)** — When `_trim_history()` drops old messages, auto-summarize them into an "evicted context" buffer instead of discarding. Re-inject the summary as an extra context block on the next LLM call. Forms a Working Memory ↔ Evicted Buffer dual-tier. Files: `context.py`, `memory_manager.py`.
- [ ] **20B: CLS Slow-Path Memory Consolidation** — Add a Cron job (e.g., daily 02:00) that runs deep consolidation on `HISTORY.md` + `MEMORY.md`: dedup repeated patterns, generalize into higher-level abstractions, demote/archive stale entries, and re-distill L1 preferences. Complements the existing fast-path session-end consolidation. Files: `memory_manager.py`, `cron/service.py`.
- [ ] **20C: Time-Decay Retrieval Scoring** — Add a configurable time-decay factor (`0.99^days`) to `vector_store.py` search results. Prevents stale memories from dominating retrieval. Files: `vector_store.py`.

### P1 — Medium Priority (Moderate effort, significant value)

- [ ] **20D: Metacognitive Reflection Memory** — When tools fail or user gives negative feedback, auto-generate a structured reflection entry `{trigger, failure_reason, corrective_action, timestamp}`. Inject matching reflections as negative few-shot examples on subsequent similar tasks. Enhances the current `record_outcome()` which only increments a counter. Files: `knowledge_workflow.py`, new `reflection.py`.
- [ ] **20E: Lightweight Entity-Relation Graph** — Extract `(subject, predicate, object)` triples during slow-path consolidation via LLM. Store as JSON. On query, do entity lookup + 1-hop traversal before vector search. No external graph DB needed. Files: new `knowledge_graph.py`, `memory_manager.py`.

### P2 — Low Priority (Future direction)

- [ ] **20F: Multi-Agent Shared Memory** — If subagent parallelism expands, share context via EventBus whiteboard pattern. Currently N/A for single-agent architecture.
- [ ] **20G: Visual Memory Text Persistence** — After VLM analyzes a screenshot, persist the image description (not the image) into HISTORY + vector index. Enables "visual memory" recall via text search. Files: `context.py`.
- [ ] **20H: web_fetch PDF Support** — Enhance `WebFetchTool` to detect `Content-Type: application/pdf` responses, download the binary stream, and pipe it through the existing `attachment_analyzer` PDF text extraction pipeline. Enables the agent to read PDFs directly from URLs without a browser. Files: `tools/web.py`, `tools/attachment_analyzer.py`.

## 7. Future Directions (Phase 21+)

### A. Performance & Retrieval
- **Streaming response delivery** — forward LLM tokens to user in real-time instead of waiting for full completion
- **Embedding model upgrade** — evaluate larger/multilingual models for improved Chinese semantic retrieval

### B. Multi-Modal Enhancement
- **Vision-Language feedback loop** — tighter VLM ↔ RPA integration for self-correcting UI automation sequences
- **Unified speech-to-text pipeline** — extend voice input beyond Telegram to all channels
- **Image generation tool** — integrate DALL-E / Stable Diffusion as a built-in creative tool

### C. Plugin Ecosystem
- **Plugin marketplace** — browsable registry of community-contributed skills
- **Plugin dependency management** — auto-install pip dependencies declared in plugin metadata
- **Plugin-level configuration** — per-plugin `config.json` merged into the main configuration hierarchy

### D. User Experience
- **Mobile-friendly dashboard enhancements** — Progressive Web App (PWA) install support, offline caching

### E. Architecture Considerations
- Evaluate event-driven architecture for better decoupling between agent and channels
- Review session persistence strategy (currently in-memory + JSON serialization)
- Consider async generator pattern for streaming LLM responses end-to-end

### F. Playwright Browser Automation *(⚠️ Heavy — discuss after urgent items complete)*
- **Headless browser agent** — integrate Playwright (Chromium) as a plugin-level tool for full browser automation: JS-rendered page scraping, form filling, session-based login, PDF online preview extraction
- **Primary use case:** Legacy ERP system automation — the company's ERP is browser-based and outdated; Playwright can navigate, extract data, and submit forms programmatically, complementing the existing UIAutomation + OCR RPA stack
- **Considerations:** ~150MB Chromium download, 200-500MB per instance memory, potential overlap with existing RPA tools — evaluate as a standalone Plugin to avoid core architecture bloat

> **Note:** Tool extensions (SqlQueryTool, CreateExcelTool, etc.) have been deprioritized — the existing `ExecTool` + Knowledge Workflow pipeline already covers these use cases via `exec` + Python libraries with automatic skill learning.

> **Note:** **Data Pipeline & Complex Contract Parsing** has been moved out of the core Nanobot backlog as an independent project requiring separate refinement and integration testing.
