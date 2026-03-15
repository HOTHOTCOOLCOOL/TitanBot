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
- [ ] **Human-in-the-Loop Web Dashboard:** Build a modern, lightweight Web UI (React/Vue) over a unified database to visualize Agent activity logs, manage pending Save/Upgrade approvals, manually edit the Knowledge Base (`tasks.json`), and monitor active Cron jobs.
- [ ] **Multi-Modal Vision & Hybrid RPA Architecture:** Expand the toolset to parse image attachments, UI screenshots, and automate apps.
  - *Completed (Short-Term):* "Text-matching" RPA implementation via `ui_name` parameter, allowing the LLM to directly click named UI elements discovered by UIAutomation without invoking expensive VLM APIs.
  - *Completed (Mid-Term):* Integrated `PaddleOCR` and a 3-layer perception architecture as a fallback when Accessibility API fails to extract text.
  - *Completed (Fix):* Added absolute-to-relative coordinate translation in `screen_capture.py` / `ui_anchors.py` to support multi-monitor RPA Set-of-Marks UI element clicking.
  - *Long-Term (Completed):* Integrated YOLO UI element detection (Layer 3) via `yolo_detector.py` with Salesforce GPA-GUI-Detector model. Auto-downloads model from HuggingFace, deduplicates against UIA/OCR elements, renders green Set-of-Marks annotations. Config: `agents.vision.yolo_enabled`.
- [ ] **Multi-user Concurrency & Context Isolation:** Upgrade `SessionManager` and `TaskKnowledgeStore` to safely isolate memory and thread state across multi-tenant chat environments (e.g., WebSockets, Feishu, Slack).

> **Note:** **Data Pipeline & Complex Contract Parsing** has been moved out of the core Nanobot backlog as an independent project requiring separate refinement and integration testing.
