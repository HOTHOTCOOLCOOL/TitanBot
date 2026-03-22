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
- `nanobot/config/`: Configuration management (`~/.nanobot/config.json` — sole config source).

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
- [x] **Knowledge Workflow Refactoring (Phase 19+ Remaining) (Completed):** Extracted user command recognition, prompt formatting, KB management commands, and outcome tracking out of `knowledge_workflow.py` into separate modules (`command_recognition.py`, `prompt_formatter.py`, `kb_commands.py`, `outcome_tracker.py`), significantly slimming it down from ~805 lines. Further decomposed by extracting `key_extractor.py` (85 lines) and `knowledge_judge.py` (273 lines), reducing the main file from 595→350 lines as a thin facade, strictly enforcing single-responsibility while maintaining 100% backward API compatibility. New tests: `test_knowledge_decomposition.py` (18 tests).

## 6. Phase 20: AI Memory Architecture Enhancement ✅

Inspired by *"Survey on AI Memory: Theories, Taxonomies, Evaluations, and Emerging Trends"* (Ting Bai et al., 2026). All 7 items completed. Post-Phase 20 comprehensive code audit identified 32 issues (6 P0, 13 P1, 13 P2) — see Phase 21 for remediation plan.

- [x] **20A: Evicted Context Buffer** | **20B: CLS Slow-Path Consolidation** | **20C: Time-Decay Retrieval**
- [x] **20D: Metacognitive Reflection Memory** | **20E: Entity-Relation Graph**
- [x] **20F: Multi-Agent Shared Memory** | **20G: Visual Memory Persistence** | **20H: web_fetch PDF Support**

## 7. Phase 21: Post-Audit Hardening & System Robustness (Next)

Comprehensive code audit (post Phase 20) identified **32 issues** across 7 dimensions. Phase 21 consolidates all audit fixes + existing backlog items into 5 sub-phases.

### Phase 21A — P0 Security & Critical Fixes ✅

| ID | Issue | File(s) | Fix Summary |
|----|-------|---------|-------------|
| S1 | Shell `..` bypass | `shell.py` | Added deny patterns for `cd ..`, `cd..`, `%2e` (URL-encoded traversal) |
| S2 | Shell deny-list bypass via interpreters | `shell.py` | Added deny patterns for `python -c`, `python3 -c`, `node -e`, `ruby -e`, `perl -e` |
| B1 | Concurrent tool exception loop | `loop.py` | Circuit breaker: breaks after 3 consecutive all-exception turns |
| L1 | Implicit feedback false positives | `outcome_tracker.py` | Word-boundary regex for English, ≤30 char limit for Chinese, negated-positive phrase check |
| L2 | Pending state edge cases | `session/manager.py`, `loop.py` | Added `Session.clear_pending()`, called before setting any new pending state |
| D1 | Memory features lack on/off switches | `config/schema.py`, `loop.py`, `context.py` | Added `MemoryFeaturesConfig` with 4 boolean flags, gated all 4 memory features |

New tests: `test_phase21a_fixes.py` (27 tests). **Regression baseline: 647 passed, 0 failed.**

### Phase 21B — P1 Security & Bug Fixes ✅

| ID | Issue | File(s) | Fix Summary |
|----|-------|---------|-------------|
| S3 | WebSocket input validation | `dashboard/app.py` | Added 10KB message limit + 30 msgs/min per-connection sliding window rate limit |
| S4 | Memory import path traversal | `commands.py` | Added workspace `is_relative_to()` guard before file access |
| B2 | Fire-and-forget task error swallowing | `commands.py`, `loop.py`, `memory_manager.py` | Added `_safe_create_task()` helper with done-callback error logging |
| B3 | SubagentManager `Config()` per-iteration | `subagent.py` | Cached Config() before the loop |
| B4 | VLM routing no fallback | `loop.py` | Falls back to default model when VLM provider config missing |
| L3 | `_workflow_succeeded` keyword false negative | `loop.py` | Removed overly generic `"no results"` from `_FAIL_INDICATORS` |
| L4 | Consolidation async race condition | `memory_manager.py` | Added `asyncio.Lock` serializing consolidation tasks |
| D2 | ReflectionStore/KG re-instantiated per call | `loop.py`, `context.py` | Lazy-cached at AgentLoop level, injected into ContextBuilder |
| D3 | System prompt unbounded injection | `loop.py` | Added 8000-char `_INJECTION_BUDGET` cap on RAG/KG/reflection/experience |
| C1 | Memory store vs. consolidation race | `memory_manager.py` | Shared `_consolidation_lock` between regular and deep consolidation |

New tests: `test_phase21b_fixes.py` (19 tests). **Regression baseline: 666 passed, 0 failed.**

### Phase 21C — P2 Quality & Robustness ✅

| ID | Issue | File(s) | Fix Summary |
|----|-------|---------|-------------|
| S5 | JSON file no atomic write/lock | `reflection.py`, `knowledge_graph.py` | Temp file + `os.replace()` atomic write in `_save()` |
| S6 | `<think>` tag strip unreliable | Multiple (7 call sites) | New `think_strip.py` utility handles unmatched tags; replaced all inline regex |
| B5 | Consolidation empty-slice API waste | `memory_manager.py` | Early-return guard when conversation text is empty |
| B6 | Session JSONL no UTF-8 encoding | `session/manager.py` | Explicit `encoding="utf-8"` + `ensure_ascii=False` on all file I/O |
| L5 | KB substring match threshold too low | `knowledge_workflow.py` | Raised threshold from 0.50→0.65, added 4-char minimum key length guard |
| C2 | Deep consolidation vs regular race | `memory_manager.py` | Already resolved by C1 shared lock — verified with test |
| C3 | Visual Memory duplicate persistence | `context.py` | Content hash dedup via `_persisted_visual_hashes` set |
| I3 | Tool output no global size limit | `tools/registry.py` | `MAX_TOOL_OUTPUT = 50,000` chars with `[TRUNCATED]` marker |
| I4 | Session JSONL full-rewrite I/O | `session/manager.py` | Extracted `_full_rewrite()` helper with proper UTF-8 encoding |
| E3 | Query rewrite always calls LLM | `vector_store.py` | Pronoun-based short-circuit (19 EN/ZH pronouns checked first) |
| E4 | Error messages i18n incomplete | `commands.py`, `i18n.py` | 8 new i18n keys, 7 hardcoded string replacements |

New tests: `test_phase21c_fixes.py` (21 tests). **Regression baseline: 704 passed.**


### Phase 21D — Architecture & Config Improvements ✅

| ID | Issue | File(s) | Resolution |
|----|-------|---------|------------|
| I1 | Config singleton inconsistency | `loader.py`, `subagent.py`, `loop.py`, `litellm_provider.py` | `get_config()` / `invalidate_config()` singleton factory; 4 call sites updated |
| I2 | Dashboard missing KB/Reflection/Graph APIs | `dashboard/app.py` | 4 new endpoints: `/api/reflections`, `/api/knowledge_graph`, `/api/knowledge_base`, `/api/background_tasks` |
| D4 | No unified async task manager | `utils/task_manager.py`, `commands.py` | `BackgroundTaskManager` class with spawn, cancel, list, concurrency limit (10); `_safe_create_task` delegates to it |
| E1 | Knowledge matching precision | `knowledge_workflow.py` | Adaptive threshold (scales 0.60–0.75 with KB size), LRU cache for key extraction (128 entries), `_match_confidence` score on all results |
| E2 | Memory capacity management | `reflection.py`, `knowledge_graph.py` | Auto-pruning: ReflectionStore max 100, KnowledgeGraph max 500 triples; public `prune()` API |

New tests: `test_phase21d_fixes.py` (21 tests). **Regression baseline: 86 passed across Phases 21A–21D.**

### Phase 21E — Feature Enhancements ✅ *(From existing backlog)*

| ID | Feature | File(s) | Summary |
|----|---------|---------|---------|
| F1 | Streaming Response Delivery | `base.py`, `litellm_provider.py`, `events.py`, `queue.py`, `loop.py`, `app.py`, `schema.py` | `stream_chat()` async generator on all providers (LiteLLM uses native `stream=True`), `StreamChunk` / `StreamEvent` dataclasses, `MessageBus` stream pub/sub, `AgentLoop._stream_llm_call()` integration, Dashboard `/ws/stream` WebSocket endpoint, `StreamingConfig` config flag |
| F2 | Embedding Model Upgrade | `vector_store.py`, `schema.py`, `context.py`, `loop.py` | Upgraded default embedding from `paraphrase-multilingual-minilm-l12-v2` (384-dim) to `BAAI/bge-m3` (1024-dim, 100+ languages). Configurable model path via `agents.defaults.embeddingModel`. Dimension introspection property on `_SentenceTransformerEmbedding`. Automatic ChromaDB collection migration on dimension mismatch (peek → detect → delete → recreate). Kept `local_files_only=True` for offline-first operation. |
| F3 | Vision-Language Feedback Loop | `vlm_feedback.py`, `rpa_executor.py`, `schema.py` | `VLMFeedbackLoop` engine with before/after screenshot VLM comparison. `VerificationResult` / `FeedbackLoopResult` dataclasses. `verify` + `expected_outcome` RPA parameters. Configurable retry loop (`VLMFeedbackConfig`: enabled, max_retries, verification_delay). Structured JSON VLM prompt with `json_repair` + heuristic fallback parsing. Graceful degradation when VLM not configured. |

New tests: `test_phase21e_streaming.py` (20 tests), `test_phase21e_embedding.py` (18 tests), `test_phase21e_vlm_feedback.py` (30 tests). **Regression baseline: 793 passed.**

### Phase 21F — Production Hotfix (Model-Switch Regressions) ✅

Post-model-switch production debugging session. 5 bugs identified from live gateway logs, all causing user-visible symptoms: repeated answers, slowness, broken email, and mixed simplified/traditional Chinese.

| ID | Bug | File(s) | Fix Summary |
|----|-----|---------|-------------|
| H1 | Infinite message loop | `loop.py` | Removed `"message"` from `_CONTINUE_TOOLS` (terminal action, not intermediate). Added `_MAX_MESSAGE_CALLS=3` flood guard |
| H2 | Verbose key extraction | `key_extractor.py` | Take last line of LLM output + enforce 50/200 char limits. Handles reasoning models without `<think>` tags |
| H3 | Vector dimension migration failure | `vector_store.py` | `peek()` → `get()` for dimension probe — `peek(include=)` not supported in installed ChromaDB version |
| H4 | Outlook send silently fails | `outlook.py` | Error prefix standardized to `"Error: "`, recipient validation, explicit `CoInitialize()` in thread |
| H5 | Simplified/Traditional Chinese mixing | `context.py` | Language instruction now explicitly requires 简体中文 with character examples (执行 vs 執行) |

Created `LESSONS_LEARNED.md` documenting 6 lessons (L1–L6) from this incident for future reference.

Updated tests: `test_phase21e_embedding.py` (mock `get()` instead of `peek()`), `test_loop_cleanup.py` (assert `message` NOT in `_CONTINUE_TOOLS`). **Regression baseline: 735+ passed.**

### Phase 21G — Production Hotfix: Recurring Bug Remediation ✅

Four bugs from Phase 21F recurred in production because previous fixes were incomplete/superficial. See `LESSONS_LEARNED.md` L7–L10 for detailed root cause analysis.

| ID | Bug | File(s) | Fix Summary |
|----|-----|---------|-------------|
| H5 | Dimension migration error silently caught | `vector_store.py` | Error handler now checks for `"dimension"` in error message and forces collection recreation instead of silent skip (L7) |
| H6 | `<think>` tags not stripped in agent loop | `loop.py` | `strip_think_tags()` applied to `final_content` in `_execute_with_llm()` BEFORE `_FAIL_INDICATORS` check — the most critical missing call site from S6 (L8) |
| H7 | Outlook `mail.To` fails for external addresses | `outlook.py` | `Recipients.Add()` + `Resolve()` instead of `mail.To` — proper COM API for external SMTP addresses outside Exchange GAL (L9) |
| H8 | Key extractor reasoning detection too weak | `key_extractor.py` | Added `_is_reasoning_text()` with 15+ prefix patterns, prompt echo detection, multi-sentence guard. Reduced English limit 200→100 chars (L10) |

New/updated tests: 7 new test cases across `test_save_prompt_condition.py` (5 think-tag tests) and `test_phase21e_embedding.py` (2 dimension probe error tests). **Regression baseline: 793 passed.**

### Phase 21H — Production Hotfix: Dimension Probe + Feishu Image Support ✅

Two issues from production log analysis: (1) vector dimension migration failing for the third time (L11), (2) Feishu images arriving as `[image]` placeholder text.

| ID | Issue | File(s) | Fix Summary |
|----|-------|---------|-------------|
| H9 | Dimension probe numpy ndarray truthiness | `vector_store.py` | `probe.get("embeddings")` returns numpy ndarray — `bool(ndarray)` raises ValueError, silently skipping migration. Fixed: `embeddings is not None and len(embeddings) > 0`. Upgraded else-branch from `debug` to `warning` (L11) |
| F4 | Feishu images arrive as `[image]` text | `feishu.py`, `image_downloader.py` | New `_download_image()` method using `GetMessageResourceRequest` API. Shared `image_downloader.py` utility for saving image bytes. Image files passed via `media` parameter to VLM pipeline |

New tests: `test_channel_image_support.py` (7 tests), `TestDimensionMigration` in `test_vector_store.py` (1 test). **Regression baseline: 0 failures (4 pre-existing import errors).**

#### Remaining Backlog (Phase 22+)
- [x] **Embedding Model Upgrade** — BAAI/bge-m3 (1024-dim, 100+ languages) ✅
- [x] **Vision-Language Feedback Loop** — Tighter VLM ↔ RPA integration for self-correcting UI automation ✅
- [x] **Dashboard PWA** — Progressive Web App install support, offline caching ✅
- [x] **Feishu Image Support** — Channel-level image download + VLM pipeline integration ✅
- [ ] **Multi-Channel Image Support** — Extend image download to MoChat, Slack, DingTalk channels

## 8. Phase 22: Skill System Hardening & Architecture Refinement

> Inspired by @trq212's "Lessons from Building Claude Code: How We Use Skills" (Anthropic). See `ARCHITECTURE_LESSONS.md` for the community article capturing our own lessons.

### Phase 22A — Skill Trigger & Discovery Optimization (P0/P1) ✅

| ID | Item | File(s) | Description |
|----|------|---------|-------------|
| SK1 | AI-First Skill Descriptions | All 11 `SKILL.md` files | Rewrote all skill `description` fields as model-optimized trigger specs. Moved "When to use" trigger phrases from body → description. Description is the **only** trigger mechanism — multi-line YAML `>` syntax with both EN/ZH triggers. |
| SK2 | Skill Taxonomy & Categories | `SKILL.md` frontmatter, `skills.py`, `context.py` | Added standardized `category` field (9 categories: library_api, code_quality, frontend_design, business_workflow, product_verification, content_generation, data_fetching, service_debugging, infra_ops). `build_skills_summary()` now groups skills by category in XML output. New `list_skills_by_category()` method. Improved YAML parser handles multi-line `>` syntax. `save_skill.py` includes `category` parameter for new skills. |
| SK3 | Skill-Level Memory | `skills.py`, skill dirs | Each skill directory supports `memory/executions.jsonl`. `log_execution()` records input/output/duration/success per execution. `get_recent_executions()` retrieves recent N records. `format_execution_context()` formats for prompt injection. `build_skills_summary()` includes recent execution summary in XML. FIFO cap at 100 entries. |

New tests: `test_phase22a_skills.py` (27 tests). **Regression baseline: 811 passed (2 pre-existing env-dependent failures).**

### Phase 22B — Skill Configurability & Hooks (P2) ✅

| ID | Item | File(s) | Description |
|----|------|---------|-------------|
| SK4 | Configurable Skill Behavior | `skills.py`, skill dirs | Per-skill `config.json` overlay system. `load_skill_config()`, `save_skill_config()` (atomic write), `get_effective_config()` merges `config.defaults.json` + `config.json`. XML summary includes `<config_keys>`. SaveSkillTool emits `config.defaults.json`. |
| SK5 | Dynamic Hooks System | `skills.py` | `pre_execute` / `post_execute` hooks. Sources: SKILL.md frontmatter (`hooks_pre`/`hooks_post`) + `hooks.py` scripts (importlib with error isolation). 3 built-in hooks: `confirm_destructive`, `log_execution`, `notify_completion`. `HookResult` dataclass. |
| SK6 | Tool Design Audit | `TOOLS.md` | Audit of 18 tools across 6 dimensions. All 18/18 compliant. |
| SK7 | Skill Registry & Versioning | `skills.py`, `save_skill.py` | `skills_registry.json` tracks version, usage_count, last_used, dependencies. `check_dependencies()` via `importlib.util.find_spec()`. SaveSkillTool adds `version`, `pip_dependencies` params. |

New tests: `test_phase22b_skills.py` (36 tests). **Regression baseline: 847 passed (4 pre-existing env-dependent collection errors).**

### Phase 22C — Multi-Modal & Channel Extension

- [ ] **Multi-Channel Image Support** — Extend image download to MoChat, Slack, DingTalk channels
- [ ] **Unified speech-to-text pipeline** — extend voice input beyond Telegram to all channels
- [ ] **Image generation tool** — integrate DALL-E / Stable Diffusion as a built-in creative tool

### Phase 22D — Architecture Evolution ✅

| ID | Item | File(s) | Description |
|----|------|---------|-------------|
| AE1 | Event-Driven Architecture Enhancement | `bus/events.py`, `bus/queue.py`, `bus/__init__.py`, `agent/loop.py`, `dashboard/app.py`, `cli/commands.py` | Extended `MessageBus` with typed domain events (`DomainEvent` base + 6 subclasses: `ToolExecutedEvent`, `KnowledgeMatchedEvent`, `MemoryConsolidatedEvent`, `SessionLifecycleEvent`, `SkillTriggeredEvent`, `CronJobEvent`). Topic-based pub/sub via `subscribe_event(topic, cb)` with wildcard `"*"` support. 3 emitters wired in agent loop. Dashboard WebSocket forwarding for real-time observability. Zero overhead — pure in-memory callback dispatch. |
| AE2 | Session Save Optimization | `session/manager.py`, `agent/loop.py`, `agent/state_handler.py` | Added `_metadata_dirty` flag to `Session`. When only new messages are added (no pending state changes), `SessionManager.save()` uses append-only mode (O(1) per new message) instead of full O(n) rewrite. All metadata mutation points wire `mark_metadata_dirty()`. SQLite migration evaluated and deferred — JSONL is sufficient for current workloads. |

- ~~Consider async generator pattern for streaming LLM responses end-to-end~~ ✅ *Done — Phase 21E*

New tests: `test_phase22d_architecture.py` (35 tests, 1 skipped). **Regression baseline: 847 passed.**

### Phase 24 — Knowledge Graph Evolution (MDER-DR) ✅

> Inspired by MDER-DR paper (arXiv 2603.11223): "Move multi-hop reasoning complexity from query-time to index-time."

| ID | Item | File(s) | Description |
|----|------|---------|-------------|
| KG1 | Triple Description Enrichment | `knowledge_graph.py` | `description` field on every triple preserving time/conditions/scope context. Prompt updated to request descriptions. |
| KG2 | Entity Disambiguation | `knowledge_graph.py` | Substring + length-ratio heuristic. Auto-merges "David" → "David Liu". `aliases` map in `graph.json`. Manual `add_alias()`. |
| KG3 | Entity-Centric Summaries | `knowledge_graph.py`, `context.py`, `memory_manager.py` | Per-entity LLM summaries in `entities` index. `get_entity_context()` replaces `get_1hop_context()` as primary injection. |
| KG4 | Query Decomposition (DR) | `knowledge_graph.py` | `_is_complex_query()` heuristic, `decompose_query()`, `resolve_multihop()` for multi-hop Q&A. |
| KG5 | Semantic Chunking | `knowledge_graph.py` | `_semantic_chunk()` splits long texts at paragraph/sentence boundaries before extraction. |

New tests: `test_phase24_knowledge_graph.py` (31 tests). **Regression: 979 passed** (2 pre-existing env-dependent failures).

### Deferred / Upcoming

#### Phase 26 — Playwright Browser Automation 🔜 (Next)

> **架构决策**: Skill + Tool Hybrid（按需加载）。详见 `implementation_plan.md`。

| Sub-Phase | Scope | Est. |
|---|---|---|
| **26A** | Plugin Dependency Management — SK7 `install_dependencies()` + `BrowserConfig` schema | 0.5d |
| **26B** | Playwright Skill (`skills/browser-automation/`) + `BrowserTool` Plugin (`plugins/browser.py`) — 11 actions, dual-layer SSRF, progressive trust | 1-2d |
| **26C** | Session encryption (DPAPI) + `TrustManager` + TTL auto-cleanup | 1d |

Design decisions (confirmed):
- Skill layer for AI trigger/config/hooks + Plugin Tool layer for execution
- Progressive trust: first navigation prompts user, then remembers permanently; sub-requests pass unless internal IP
- DPAPI-encrypted cookie/storage persistence with domain isolation and TTL
- Complements desktop RPA: `browser` for Web apps, `rpa` for Win32 apps

#### Plugin Marketplace *(P3 — after Phase 26)*
- Browsable registry of community-contributed skills
- JSON registry + GitHub-hosted skill packages

> **Note:** Tool extensions (SqlQueryTool, CreateExcelTool, etc.) remain deprioritized — `ExecTool` + Knowledge Workflow covers these via Python libraries with automatic skill learning.

> **Note:** **Data Pipeline & Complex Contract Parsing** is an independent project with separate planning.


## 9. Phase 23: Security Audit Remediation ✅

> Full-spectrum security/architecture audit identified **16 risk items** across 3 priority levels. All remediated in 3 sub-phases.

### Phase 23A — P0 Security Hardening ✅

| ID | Risk | File(s) | Fix Summary |
|----|------|---------|-------------|
| R1 | Dashboard POST no input validation | `dashboard/app.py` | 1 MB body size limit on POST endpoints (HTTP 413) |
| R2 | hooks.py arbitrary code execution | `skills.py` | Workspace-only path, 50 KB size limit, static scan blocking dangerous imports |
| R4 | SSRF DNS rebinding bypass | `web.py` | `_SSRFSafeTransport` validates IPs at connect time, closing TOCTOU |
| R5 | Token logged in plaintext | `dashboard/app.py` | Masked to first 8 chars + `***` |

New tests: 14 passed. **Regression: 924+ passed.**

### Phase 23B — P1 Data Integrity & Architecture ✅

| ID | Risk | File(s) | Fix Summary |
|----|------|---------|-------------|
| R3 | Session non-atomic write | `session/manager.py` | Temp file + `os.replace()` for both append and full-rewrite modes |
| R7 | Cron non-atomic write + truncated UUID | `cron/service.py` | Atomic write + full 36-char UUID |
| R8 | Config singleton bypass | `context.py` | All call sites use `get_config()` singleton |
| R9/R15 | WebSocket dead connection accumulation | `dashboard/app.py` | Failed WS removed on send error |
| R10 | Key extraction cache FIFO not LRU | `knowledge_workflow.py` | `OrderedDict`-based true LRU (cap=128) |
| R13 | Session key restore breaks on underscores | `session/manager.py` | `original_key` persisted in JSONL metadata |

New tests: 15 passed. **Regression: 948 passed.**

### Phase 23C — P2 Architecture Polish & Edge Hardening ✅

| ID | Risk | File(s) | Fix Summary |
|----|------|---------|-------------|
| R11 | Image no size limit | `context.py` | 20 MB cap; oversized files skipped with warning |
| R6 | Write file no size limit | `filesystem.py` | 10 MB cap; rejects before disk write |
| R14 | VLM env `setdefault` ignores override | `litellm_provider.py` | Direct assignment for VLM dynamic route |
| R16 | MD5+12 visual hash collision risk | `context.py` | SHA256+16 chars |
| R12 | Outlook state shared across sessions | `outlook.py` | Documented per-instance scope; future isolation path noted |

New tests: 7 passed. **Regression: 948 passed** (2 pre-existing failures unrelated).
