# Phase 3: Dynamic Skill Hot-Loading

## Problem Description

Currently, Nanobot's tool architecture requires **hardcoding**. When a new skill is developed (or grabbed from the `resources/` directory or community), a developer must:
1. Manually copy the `.py` tool file into `nanobot/agent/tools/`.
2. Open `nanobot/agent/loop.py` and manually import the new tool class.
3. Add it to the `_register_default_tools` method to register it with the `ToolRegistry`.
4. Restart the Nanobot process.

This is a **monolithic approach** that prevents Nanobot from easily acquiring new skills autonomously or letting non-technical users install community skills out-of-the-box. It also makes updating built-in skills difficult.

## Proposed Solution: True Plug-and-Play Architecture

We need to implement a dynamic skill auto-loader that can import and register tools at runtime, paired with a command to easily "onboard" new skills.

### 1. The Dynamic Tool Loader (Runtime Import)
- **Directory Scanning**: Introduce a designated `nanobot/plugins/` (or `nanobot/agent/tools/custom/`) directory.
- **Dynamic Module Import**: Modify the `ToolRegistry` or `loop.py` startup sequence to use `importlib` and `inspect`. It will scan all `.py` files in the plugin directory, find any classes that inherit from `Tool` (and aren't base classes), and automatically instantiate and register them.
- **Hot-Reloading**: Introduce a `/reload` chat command (and potentially a filesystem watchdog) that can clear the dynamic portion of the registry and re-scan without restarting the core `asyncio` event loop.

### 2. The `onboard` Mechanism
- Create an onboarding utility (e.g. via CLI `python main.py onboard <skill>` or an internal `InstallSkillTool`) that:
  - Locates the skill from the `resources/` folder (e.g., `ssrs-report`, `outlook-email-analysis`) or eventually a remote repository.
  - Copies the necessary `.py` files and associated assets into the active `plugins/` directory.
  - Automatically provisions required `pip` dependencies if a `requirements.txt` is present.

### 3. Verification & Safety
- **Conflict Resolution**: Ensure dynamically loaded tools don't override core built-in tools (like `exec`, `read_file`) unless explicitly allowed.
- **Error Isolation**: If a dynamic tool has a syntax error or missing dependency, the loader should catch the exception, log a warning, and continue loading other tools, ensuring the main bot doesn't crash on startup.

## Status
**COMPLETED (2026-03-07)**
- `plugin_loader.py` implemented with `scan_plugins()`, `load_plugin()`, and `unload_plugins()` using `importlib` + `inspect`.
- Integrated into `loop.py` via `_register_dynamic_tools()` with built-in tool conflict protection.
- `/reload` slash command added for hot-reloading plugins without process restart.
- `onboard.py` utility created for installing skills from `resources/` with auto-dependency management.
- Error isolation: syntax errors, missing imports, and instantiation failures in plugins are caught and logged without crashing the bot.
- 10 dedicated tests in `test_plugin_loader.py` covering discovery, isolation, conflict, and unload scenarios.

> [!NOTE]
> Also fixed 5 audit issues during this phase: ComputeBroker graceful shutdown fallback, Cron comment accuracy, Excel multi-sheet parsing, proper pytest for compute broker, and PyPDF2→pypdf migration.
