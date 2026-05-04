# Baseline

**Job ID**: `heavy_20260503_eywa_mcp`
**Session**: A — Lead / Synthesizer
**Phase**: A0 — Fact Baseline

---

## Claims, Evidence & Status

| # | Claim | Evidence | Status |
|---|-------|----------|--------|
| C1 | Nanobot already has an MCP client implementation | `nanobot/agent/tools/mcp.py` — `MCPToolWrapper` + `connect_mcp_servers()` | ✅ Confirmed |
| C2 | MCP tools are already registered dynamically into `ToolRegistry` | `mcp.py` L82: `registry.register(wrapper)` | ✅ Confirmed |
| C3 | Current `config.sample.json` has no MCP server configuration key | Inspected `config.sample.json` — `tools` section only has `web` and `copilotStudio` | ✅ Confirmed |
| C4 | `MCPToolWrapper` assigns capability tags `UNTRUSTED_EXTERNAL \| INFO_RETRIEVAL` to all MCP tools | `mcp.py` L30: `return CapabilityTag.UNTRUSTED_EXTERNAL \| CapabilityTag.INFO_RETRIEVAL` | ✅ Confirmed |
| C5 | MCP tool names are namespaced as `mcp_{server_name}_{tool_name}` | `mcp.py` L20: `self._name = f"mcp_{server_name}_{tool_def.name}"` | ✅ Confirmed |
| C6 | There is no sanitization of MCP tool descriptions before LLM injection | `mcp.py` L21: `self._description = tool_def.description or tool_def.name` — raw passthrough | ✅ Confirmed |
| C7 | `connect_mcp_servers()` is the public API — how/when it is called is unknown | No call site found in the tools directory; must be called from agent setup | ⚠️ Unverified |
| C8 | Tool registry global output cap is 50,000 chars | `registry.py` L19: `MAX_TOOL_OUTPUT = 50_000` | ✅ Confirmed |
| C9 | MCP tool execution timeout inherits the 120s base class default | `MCPToolWrapper` does not override `execution_timeout`; base class returns 120 | ✅ Confirmed |
| C10 | TOOLS.md lists `mcp.py` as compliant (#15) but lacks detailed security audit | `TOOLS.md` L188-195: listed with minimal detail — "Passes through MCP server response" | ✅ Confirmed |

---

## Source of Truth Files

- `nanobot/agent/tools/mcp.py` — MCP client implementation
- `nanobot/agent/tools/registry.py` — ToolRegistry, MAX_TOOL_OUTPUT
- `nanobot/agent/tools/base.py` — Tool base class, CapabilityTag, execution_timeout
- `config.sample.json` — canonical config schema
- `TOOLS.md` — tool audit record
- `progress_report.md` — phase history
- `docs/antigravity_architecture_reference.md` — ADR-59 decisions

---

## Operational Constraints

1. **Single Host Agent philosophy** — cannot introduce autonomous peer-to-peer multi-agent communication
2. **ARCHITECTURE.md single-loop commandment** — no new event loops or blocking constructs
3. **UNTRUSTED_EXTERNAL tag is mandatory** for any MCP tool (already in place)
4. **Verification layer (ADR-66)** — any new external integration must pass L1 path/boundary checks
5. **Zero extra infrastructure** principle — MCP server connections must be opt-in via config, not auto-discovered

---

## Unknowns

| # | Unknown | Impact |
|---|---------|--------|
| U1 | Where does `connect_mcp_servers()` get called? (agent startup, tool_setup, loop init?) | High — determines lifecycle and failure blast radius |
| U2 | Does the MCP session remain alive for the full agent lifetime or reconnect per call? | Medium — affects resource leak risk |
| U3 | Can a malicious MCP server inject a tool description that manipulates LLM behavior (prompt injection)? | High — security concern |
| U4 | Is there a formal `mcp_servers` config key anywhere, or is it only referenced in code? | Medium — determines if any MCP server is actually connectable today |
| U5 | Does TOOLS.md audit `#15` reflect a real security review or just existence check? | Medium — determines if current audit is sufficient |

---

## Questions the Critic Must Attack

1. **Is MCP adoption actually needed?** Nanobot already wraps external capabilities as native tools (e.g., `ConsultCopilotTool`). Does MCP add genuine value, or is it over-engineering?
2. **Is the current `UNTRUSTED_EXTERNAL` tag sufficient?** Or does the raw passthrough of tool descriptions create a prompt-injection surface that the tag doesn't mitigate?
3. **Lifecycle ambiguity (U1, U2)** — can the current implementation survive agent restarts or connection drops?
4. **Config gap (C3, U4)** — if `config.sample.json` has no `mcp_servers` key, is MCP actually usable by anyone today?
5. **MCP vs. custom bridge code** — is a standardized MCP client actually simpler than the current `ConsultCopilotTool` pattern? What is the real maintenance delta?
