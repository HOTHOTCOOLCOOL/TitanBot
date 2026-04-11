# Phase 45C: Execution Policy & Coordinator Sandbox (Archive)

**Date**: 2026-04-11
**Status**: Completed

## Objectives
- Integrate `ExecutionPolicy` into `PythonSandbox` for granular control.
- Enforce basic security restrictions on `Coordinator Worker` processes running via `worker_process.py`.
- Add tool-specific sandbox overrides to configuration (`SandboxConfig`).

## Design Adjustments from ADR-45
During implementation, a fatal architectural pitfall in the ADR was identified and mitigated:
- **The Pitfall**: The ADR specified adding a strict `--disable-network-socket` via `sys.addaudithook` to `worker_process.py`. However, `worker_process.py` initializes an `aiohttp` web server (requiring `socket.bind` for IPC) and runs the entire AgentLoop that requires accessing LLM provider APIs over the network. Strict socket interception at the top of the worker wrapper would have instantly crashed the Windows `ProactorEventLoop` and blinded the agent.
- **The Mitigation**: The network socket block was explicitly removed from `worker_process.py`'s sys audit hook. The hook now focuses robustly on blocking unprotected raw shell execution methods (`os.system`, `os.exec`), ensuring the worker delegates shell operations exclusively to the isolated `ShellSandbox`.

## Code Changes
1. **`schema.py`**: Added `capability_overrides` field to `SandboxConfig`.
2. **`sandbox.py`**: Refactored `run_hook` to accept and prioritize `ExecutionPolicy` flags (timeout, networking) over global defaults.
3. **`coordinator.py`**: Injected the `-I` isolation flag and the configured `--timeout` into the worker `subprocess.Popen` constructor.
4. **`worker_process.py`**: Added an isolated `_bootstrap_security` step before async loop creation to aggressively block direct OS process mutations, alongside updated argparse defaults for dynamic idle timeouts. 
5. **`ARCHITECTURE.md`**: Enshrined the socket-blocking architecture pitfall as Rule #15.
