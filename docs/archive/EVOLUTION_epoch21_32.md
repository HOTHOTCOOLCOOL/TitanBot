# Nanobot 演进历程: Epoch 21-32

## Phase 22: Skill System Hardening & Architecture ✅

> 受 Anthropic 工程师 @trq212 的文章 "Lessons from Building Claude Code: How We Use Skills" 启发，
> 我们将 Skill 系统的最佳实践融入了 Phase 22 路线图。
> 
> 详见：
> - `ARCHITECTURE_LESSONS.md` — 我们自己的 10 条架构经验总结（社区分享文章）
> - `PROJECT_STATUS.md` § Phase 22 — Skill System Hardening & Architecture Refinement

### Phase 22D — Architecture Evolution ✅

- **AE1: Event-Driven Architecture Enhancement** — Extended `MessageBus` with typed domain events (`DomainEvent` base + 6 subclasses). Topic-based pub/sub with wildcard `"*"` support. Dashboard WebSocket forwarding for real-time observability.
- **AE2: Session Save Optimization** — Added metadata dirty flag to `Session`. Append-only save mode when only new messages are added. SQLite evaluated and deferred — JSONL is sufficient.
- New tests: 35 passed, 1 skipped. **Regression: 847 passed.**

## Phase 23A — P0 Security Hardening ✅

- **R1: Dashboard POST Input Validation** — Added 1MB body size limit to `POST /api/memory` and `POST /api/tasks` to prevent DoS via oversized payloads (HTTP 413).
- **R2: hooks.py Sandbox Hardening** — Three security layers: workspace-only path restriction, 50KB file size limit, and static scan blocking dangerous imports (`os`, `subprocess`, `shutil`, `sys`).
- **R4: SSRF DNS Rebinding Fix** — Replaced pre-flight `_is_internal_address()` check with `_SSRFSafeTransport` (custom `httpx.AsyncBaseTransport`) that validates resolved IPs at connect time, closing TOCTOU vulnerability.
- **R5: Token Log Masking** — Dashboard auto-generated token now masked in logs (shows only first 8 chars + `***`).
- New tests: 14 passed. **Regression: 924+ passed.**

### Config Cleanup (2026-03-21) ✅

- Removed redundant `.env` overlay — `~/.nanobot/config.json` is now the **sole** configuration source.
- Changed `Config` from `pydantic_settings.BaseSettings` to `pydantic.BaseModel`.
- Removed `pydantic-settings` dependency.
- Created `config.sample.json` (Git-tracked template, replaces `.env.example`).
- Deleted `.env.example`.

## Phase 23B — P1 Data Integrity & Architecture Fixes ✅

- **R3: Atomic Writes** — Session and Cron stores use temp-file + `os.replace()`.
- **R7: Cron Full UUID** — Cron job IDs use full 36-char UUID instead of truncated 8-char.
- **R8: Config Singleton** — Ensured single `Config` instance across all modules via `get_config()`.
- **R9/R15: Dead WebSocket Cleanup** — Failed WebSocket connections removed on send error.
- **R10: LRU Key Extraction Cache** — True LRU eviction via `OrderedDict` (cap=128).
- **R13: Session Key Restoration** — Original key persisted in JSONL metadata; `list_sessions()` uses it.
- New tests: 15 passed. **Regression: 948 passed.**

## Phase 23C — P2 Architecture Polish & Edge Hardening ✅

- **R11: Image Size Limit** — `_build_user_content()` skips images >20 MB with warning log.
- **R6: Write File Size Limit** — `WriteFileTool` rejects content >10 MB to prevent disk exhaustion.
- **R14: VLM Env Override** — VLM dynamic route uses direct assignment (`os.environ[key] = value`) instead of `setdefault`.
- **R16: SHA256 Visual Hash** — Visual memory dedup hash upgraded from MD5+12 chars to SHA256+16 chars.
- **R12: Outlook State Docs** — Documented per-instance state scope and future isolation path.
- New tests: 7 passed. **Regression: 948 passed** (2 pre-existing failures unrelated).

## Phase 24 — Knowledge Graph Evolution (MDER-DR) ✅

> 受 MDER-DR 论文 (arXiv 2603.11223) 启发："将多跳推理的复杂性从查询时移到索引时"

| ID | Item | File(s) | Description |
|----|------|---------|-------------|
| KG1 | Triple Description Enrichment | `knowledge_graph.py` | 每个三元组附带自然语言 `description` 字段，保留提取时的时间、条件、范围等上下文信息。`extract_triples` LLM prompt 同时请求描述。`get_1hop_context` 输出包含描述。 |
| KG2 | Entity Disambiguation | `knowledge_graph.py` | 轻量级实体消歧：子串包含 + 长度比例守卫（>30%）。自动合并 "David" → "David Liu" 等等价实体，存储 `aliases` 映射。支持手动 `add_alias()`。 |
| KG3 | Entity-Centric Summaries | `knowledge_graph.py`, `context.py`, `memory_manager.py` | 为每个实体预生成 LLM 聚合摘要，存储在 `graph.json` 的 `entities` 索引中。`get_entity_context()` 替代 `get_1hop_context()` 作为首选注入方式。深度整合后自动重新生成摘要。 |
| KG4 | Query Decomposition (DR) | `knowledge_graph.py` | `_is_complex_query()` 启发式检测多跳查询（中英文模式）。`decompose_query()` 将复杂查询分解为子查询链。`resolve_multihop()` 迭代解析并收集上下文。 |
| KG5 | Semantic Chunking | `knowledge_graph.py` | `_semantic_chunk()` 在三元组提取前按段落和句子边界切分长文本（支持中英文），无需 embedding 调用。 |

- `knowledge_graph.py` 从 216 行扩展至 ~450 行，保持轻量。
- `context.py` 更新为优先使用实体摘要注入（KG3），无摘要时回退到 1-hop。
- `memory_manager.py` 在深度整合后链式触发 `extract_triples()` → `generate_entity_summaries()`。
- New tests: `test_phase24_knowledge_graph.py` (31 tests). **Regression: 979 passed** (2 pre-existing env-dependent failures).

## Phase 25 — Project Retrospective & Hardening ✅

> 系统性代码审查（15+ 核心模块），识别并修复 7 个 bug / 健壮性 / 安全边缘问题。

| ID | Severity | File(s) | Description |
|----|----------|---------|-------------|
| F1 | P1-Bug | `dashboard/app.py` | WebSocket 断连异常处理覆盖：新增 `except Exception` 兜底，防止非 `WebSocketDisconnect` 异常导致 `_active_websockets` 残留 |
| F2 | P1-Bug | `session/manager.py` | 追加模式下 `updated_at` 不更新：在 append-only 路径更新时间戳，每 10 条消息标记 metadata dirty |
| F3 | P2-Robustness | `dashboard/app.py` | POST 接口 JSON 解析：`update_memory` / `update_tasks` 新增 `json.JSONDecodeError` 捕获，返回 400 而非 500 |
| F4 | P2-Robustness | `config/loader.py` | `save_config` 原子写入：统一使用 tempfile + `os.replace()` 防止进程崩溃时配置文件损坏 |
| F5 | P2-Performance | `knowledge_graph.py` | 移除 `_add_triple` 中的单次 `_save()` 调用，消除批量提取时 N 次冗余磁盘写入 |
| F7 | P3-Security | `web.py` | `WebSearchTool` 统一使用 `_SSRFSafeTransport`，与 `WebFetchTool` 保持一致 |
| F8 | P3-Robustness | `cron/service.py` | `_load_store` 显式指定 `encoding="utf-8"`，修复 Windows 非 ASCII 路径潜在问题 |

- 无新增测试文件（修复均为防御性改进，已被现有 979 个测试覆盖）。**Regression: 979 passed.**

## Phase 26 — Playwright Browser Automation

> 完整 Web RPA 方案，与桌面 RPA (UIA/OCR/YOLO) 互补。架构：Skill + Tool Hybrid 按需加载。

### Phase 26A — Plugin Dependency Management ✅

- **BrowserConfig Schema** — New `BrowserConfig` Pydantic model in `config/schema.py` with 10 fields (enabled, headless, timeout, viewport, max_pages, session_ttl, trusted_domains, block_internal_ips). Wired into `AgentsConfig.browser`.
- **`_check_requirements()` pip support** — Extended to check `requires.pip` packages via `importlib.util.find_spec()`. Skills with unmet pip deps are now correctly filtered from `list_skills()` and shown as `available="false"` in XML summary.
- **`_get_missing_requirements()` pip reporting** — Extended to report missing pip packages as `"PIP: package_name"` in `<requires>` XML tag.
- **`install_dependencies(skill_name)`** — New method that checks and reports missing pip deps without auto-installing. Returns `(False, description)` with package list for LLM to present to user.
- **`do_install_dependencies(packages)`** — New static method that runs `pip install` via subprocess with 5-minute timeout. Never called silently — requires user confirmation.
- New tests: `test_phase26a_deps.py` (16 tests). **Regression: 992 passed** (5 pre-existing env-dependent failures).

| Sub-Phase | Scope | Status |
|-----------|-------|--------|
| **26A** | Plugin Dependency Management — SK7 扩展 + `BrowserConfig` | ✅ |
| **26B** | Playwright Skill + BrowserTool Plugin — 11 action + 双层 SSRF + 渐进信任域名 | ✅ |
| **26C** | Session 加密持久化 (DPAPI) + Trust Manager + TTL | ✅ |

关键设计：
- `skills/browser-automation/SKILL.md` (Skill 层) + `plugins/browser.py` (Tool 层)
- 渐进信任：主导航首次授权 → 永久记住，子请求仅阻断内网 IP
- DPAPI 加密 Cookie 持久化，域名隔离，TTL 过期
- `browser` 管 Web 应用，`rpa` 管桌面应用，LLM 自动路由

### Phase 26B — Playwright Skill + BrowserTool Plugin ✅

- **SKILL.md** — New `skills/browser-automation/SKILL.md` with AI-first EN/ZH triggers, `requires.pip: ["playwright"]`, and guidance on `browser` vs `rpa` vs `web_fetch` tool selection.
- **BrowserTool Plugin** — New `plugins/browser.py` (~400 lines) with:
  - 11 actions: navigate, click, fill, type, select, screenshot, content, evaluate, wait, login, close
  - Graceful degradation: `HAS_PLAYWRIGHT` guard — zero-impact when playwright not installed
  - Lazy browser launch: Chromium only started on first `navigate`, not at import
  - Dual-layer SSRF: pre-navigation `socket.getaddrinfo()` IP check + `page.route("**/*")` request interception
  - Progressive trust: new domain → user confirmation prompt → persist to `~/.nanobot/browser_sessions/trusted_domains.json` with atomic writes
  - Evaluate whitelist: only 6 pre-approved JS patterns allowed (document.title, querySelector.textContent, etc.)
  - Page pool with configurable `max_pages` limit
- **`login` action** — accepts `save_session` param (no-op in 26B, wired in 26C)
- New tests: `test_phase26b_browser.py` (54 tests). **Regression: 1046 passed** (5 pre-existing env-dependent failures).

### Phase 26C — Session Encrypted Persistence + Trust Manager ✅

- **BrowserSessionStore** — New `plugins/browser_session.py` (~280 lines):
  - Three-tier encryption: Windows DPAPI (`win32crypt`) → `cryptography.Fernet` → base64 obfuscation
  - `save_session(domain, cookies, local_storage)` — serialize + encrypt + atomic-write to `~/.nanobot/browser_sessions/{domain}/session.enc`
  - `load_session(domain)` — TTL check via metadata + decrypt; returns None if expired
  - `clear_session(domain)` / `clear_expired(ttl_hours)` — cleanup per-domain or batch expired
  - `list_sessions()` — enumerate all saved sessions with metadata
  - Dual-file storage: `session.enc` (encrypted data) + `session.meta.json` (plaintext TTL metadata)
  - Domain isolation: separate directories per domain, no cross-domain leakage
- **TrustManager extraction** — New `plugins/trust_manager.py` (~130 lines):
  - Extracted from inline `_TrustManager` in `browser.py` to standalone public module
  - New methods: `remove_trusted(domain)`, `clear_all()` for runtime trust management
  - Same wildcard matching, atomic persistence, and config-level trust support
- **Browser integration wiring**:
  - `_action_login` with `save_session=True`: extracts cookies via `context.cookies()` + localStorage via `page.evaluate()`, encrypts and persists
  - `_action_navigate`: automatically restores saved session cookies before page load via `context.add_cookies()`
  - Cookie values never appear in LLM-facing tool output (only `"session_saved": true`)
  - No new hard dependencies — encryption backends gracefully degrade
- New tests: `test_phase26c_sessions.py` (28 tests). Combined 26B+C: **82 passed**. **Regression: 1074 passed** (5 pre-existing env-dependent collection errors).

## Phase 27 — Security & Stability Hardening ✅

> Critical hardening phase targeting SSRF, Sandbox Escape, and Windows File I/O resilience.

- **SSRF TOCTOU Remediation** — Eradicated Time-of-Check to Time-of-Use race conditions in `web.py` and `browser.py` by implementing dynamic pre-connection DNS resolution pinning via an intercepted `_SSRFSafeTransport` and Playwright route overrides.
- **Skill Sandbox Escape Fix** — Replaced weak string-matching in `skills.py` with rigorous Abstract Syntax Tree (AST) visitor analysis (`ast.parse`) that statically blocks all dynamic imports (`__import__`, `importlib`) and standard blocklisted modules (`os`, `subprocess`) prior to execution.
- **Windows Atomic Write Resilience** — Implemented a globally resilient `safe_replace` utility wrapping `os.replace` with a 5-iteration exponential backoff, effectively mitigating common `PermissionError` crashes induced by Windows Defender / Antivirus locks on rapidly replaced SQLite/JSONL and config stores.

## Phase 28A — OpenClaw Optimization: Provider Abstraction & Plugin Lifecycle ✅

> First half of Phase 28 OpenClaw Architectural Optimization targeting dynamic abstractions.

- **ProviderFactory Abstraction** — Replaced direct instantiations of `LiteLLMProvider` for dynamic VLM requests in the main agent loop with a generic `ProviderFactory.get_provider()` interface. Restored deterministic registry-matching precedence.
- **Formal Plugin Lifecycle** — Implemented natively asynchronous `setup()` and `teardown()` core lifecycle hooks in the `Tool` base class. Rewrote the `AgentLoop.run()` execution boundary with `try/finally` logic to guarantee that all loaded plugins deterministically discover, initialize, and gracefully unload resources across sessions.
- New tests: Unit tests added for ProviderFactory (`test_provider_factory.py`) and Plugin Lifecycle hook states (`test_plugin_lifecycle.py`). **Regression: 1088 passed.**

## Phase 28B — OpenClaw Optimization: Execution Layer Sandboxing ✅

> Second part of Phase 28 targeting security and isolation boundaries.

- **Python Sandbox (`sandbox.py`, `sandbox_worker.py`)** — Executed Python plugin scripts via `sys.executable -I` with a restricted `sys.addaudithook` to silently block dangerous functions like process spawning (`os.system`), network I/O (`socket.bind`), and out-of-workspace writes.
- **Shell Sandbox (`shell.py`)** — Re-architected command execution using `asyncio.create_subprocess_shell` with a heavily stripped process environment, removing sensitive keys and blocking potential shell escape vectors. Timeout enforcement added.
- **Plugin Execution Refactoring (`skills.py`)** — Shifted AST scanning security checks out of the main loop. Python hooks execution now wholly delegated to `PythonSandbox.run_hook`, ensuring crashes/leaks never impact the primary agent thread.

New tests: `test_phase28b_sandbox.py` (5 tests). **Regression: 1093 passed.**

## Phase 28C: OpenClaw Memory Architecture ✅

- **Three-Tier Memory Architecture**: Formalized the memory hierarchy (Context Window -> JSONL Session -> Vector DB + KG) by integrating a dedicated Vector Database layer (ChromaDB) into the existing Knowledge Graph. Enabled hybrid exact+semantic search for entity contexts.

New tests: `test_phase28c_knowledge_graph.py` (3 tests). **Regression: 1097 passed.**

## Phase 29: Paper-Inspired Enhancements (论文借鉴) ✅

> 源自 2026-03-25 对 5 篇前沿顶会论文的系统性对比分析，成功通过 1210 项回归测试，正式集成。详见 `paper_analysis_report.md`。

| ID | Item | Source | Details |
|----|------|--------|---------|
| P29-1 | Directive Signal → 修正记忆 | OpenClaw-RL | `outcome_tracker` 检测反馈，生成 Tactical Prompt 存入战术经验库 |
| P29-2 | System Reminders & 模型认知路由 | OPENDEV | `loop.py` 动态诸如对话总结提醒；支持配置 `workflow_models` 独立字典 |
| P29-3 | 离线 Bridging Facts 生成 | IndexRAG | `generate_bridging_facts` 于图谱闲时生成多跳隐式关联事实 |
| P29-4 | Knowledge Completion（知识补全） | QChunker | `VectorMemory.search_with_completion` 实时补全 Context 盲区 |
| P29-5 | 错误信号 → 自动经验 | OpenClaw-RL | 连续工具失败时自动提取并存储 Error Recovery Experience |
| P29-6 | 知识溯源链 | Dual-Tree | `task_knowledge.py` 支持树状 `derived_from` 血缘追踪 |

## Phase 30: 弱模型防护 (Weak Model Safety Guards) ✅

> Added multi-layered execution safeguards against hallucination loops and context bloat when using weaker language models. Fixed critical medium-priority bugs and enhanced the agent pipeline.

- Fixed Phase 30 medium issues (8 items: E3-E10 testing mocks and logic bugs).
- Fixed Phase 30 remaining layer bugs (7 items: BUG/SEC/DESIGN items).
- New tests: 20 new test cases added. **Regression: 1209 passed.**
