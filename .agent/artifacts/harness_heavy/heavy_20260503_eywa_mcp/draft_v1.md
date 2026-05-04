# Draft V1

**Job ID**: `heavy_20260503_eywa_mcp`
**Session**: A — Lead / Synthesizer
**Phase**: A1 — Initial Technical Draft

---

## Context

Based on the `baseline.md` audit and direct code inspection, this draft evaluates whether Nanobot should **formalize MCP as a first-class integration pattern** and, if so, what the minimum viable upgrade looks like.

---

## Finding: MCP Is Already Partially Implemented

Nanobot already has a working MCP client (`mcp.py`). The critical gap is not "should we adopt MCP" — it already exists — but rather **whether the current implementation has sufficient hardening to be safely exposed to operators and external servers**.

### What exists today (confirmed via code)
| Component | State |
|-----------|-------|
| `MCPToolWrapper` — wraps FM tools as native Nanobot tools | ✅ Exists |
| `connect_mcp_servers()` — connects via stdio or HTTP | ✅ Exists |
| Dynamic registration into `ToolRegistry` | ✅ Exists |
| `UNTRUSTED_EXTERNAL \| INFO_RETRIEVAL` capability tags | ✅ Exists |
| Namespaced tool names (`mcp_{server}_{tool}`) | ✅ Exists |
| Lazy lifecycle via `_connect_mcp()` in `loop.py` | ✅ Exists |
| Persistent `AsyncExitStack` for session management | ✅ Exists |

### Critical gaps identified

| Gap | Risk | Severity |
|-----|------|----------|
| **G1**: No `mcp_servers` key in `config.sample.json` | MCP is effectively undocumented and un-configurable for users | 🟡 Medium |
| **G2**: Raw passthrough of MCP tool descriptions to LLM | A malicious MCP server can inject adversarial prompt content into the agent's system context | 🔴 High |
| **G3**: No reconnection on session drop | If an MCP server crashes mid-session, tools fail silently with generic errors; `_mcp_connected = True` flag prevents retry | 🟡 Medium |
| **G4**: `TOOLS.md` audit for tool #15 (`mcp.py`) is superficial | Security posture is listed as "passes through MCP server response" with no adversarial analysis | 🟡 Medium |
| **G5**: No length cap on tool descriptions from MCP | An MCP server could return a 100KB tool description, inflating LLM context unexpectedly | 🟡 Medium |

---

## Proposed Decision

**Formalize MCP as a first-class integration pattern** with targeted hardening. This is not a major architecture change — it is a security and documentation upgrade to an existing capability.

### Option A: Description Sanitization + Config Schema (Recommended)

**What changes:**
1. **Add `mcp_servers` to `config.sample.json`** with a clear schema (stdio or HTTP, env vars)
2. **Sanitize MCP tool descriptions** before LLM injection: truncate at a safe length (e.g., 500 chars) and strip any content that matches known prompt injection patterns
3. **Add reconnection guard** to `_connect_mcp()`: catch `CancelledError` and re-raise, catch other exceptions and attempt one reconnect before marking the server as failed
4. **Update `TOOLS.md`** security assessment for tool #15 to reflect the actual security review

**What does NOT change:**
- `CapabilityTag.UNTRUSTED_EXTERNAL` assignment (already correct)
- `ToolRegistry.MAX_TOOL_OUTPUT = 50,000` cap (already correct)
- Tool name namespacing (already correct)
- Single Host Agent architecture (unchanged — MCP servers are remote resources, not peer agents)
- `verification.py` / ADR-66 security contracts (unchanged)

### Option B: Do Nothing (Keep Current State)

Leave MCP as an undocumented, power-user-only feature. No config documentation, no description sanitization.

**Risk**: The current raw passthrough of tool descriptions (G2) is a latent prompt injection surface. If an operator connects to a third-party MCP server, any tool with a maliciously crafted `description` field will be injected verbatim into the LLM's available tools context.

**Assessment**: Unacceptable for a system with ADR-66 security posture. Option B should be rejected.

---

## Core Trade-offs

| Trade-off | Assessment |
|-----------|------------|
| Implementation effort vs. security gain | Low effort (< 100 LOC changes), high security gain for G2 |
| "Zero extra infrastructure" principle | ✅ Preserved — MCP servers remain opt-in via config |
| Single Host Agent philosophy | ✅ MCP servers are tools/resources, not autonomous agents |
| Backward compatibility | ✅ Existing `mcp_servers` dict API unchanged; config key is additive |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Description sanitization is too aggressive and breaks legitimate tools | Low | Medium | Use truncation + a narrow denylist (e.g., `<INST>`, `[SYSTEM]`, `ignore previous`) rather than full content scanning |
| Reconnection logic introduces new race conditions | Low | Medium | Keep reconnection to a single synchronous attempt; do not introduce retry loops |
| Config schema change breaks existing (undocumented) users | Very Low | Low | Additive only; existing code path still works if `mcp_servers` is passed programmatically |

---

## Unverified Assumptions

| Assumption | Status | Source Needed |
|------------|--------|---------------|
| A1: Description truncation at 500 chars won't break real MCP tools | ❓ Unverified | Need to check reference MCP servers (e.g., filesystem-mcp) |
| A2: `_mcp_connected = True` flag actually prevents re-entry on reconnect; resetting it safely is possible | ❓ Unverified | Code inspection of `_connect_mcp()` confirms flag but reset path is unclear |
| A3: The `MCP_SERVERS` config key was intentionally omitted from `config.sample.json` or accidentally omitted | ❓ Unknown | No ADR or code comment explains the omission |

---

## Summary Recommendation

> Proceed with **Option A** — targeted hardening of the existing MCP implementation:
> G2 (prompt injection via tool description) is a genuine security gap given Nanobot's stated ADR-66 security posture.
> G1 (missing config schema) is a usability gap that also increases blast radius (operators can't safely configure MCP without guessing the API).
> G3, G4, G5 are lower priority and can be deferred to a follow-up phase.

**Scope estimate**: < 100 lines of code across `mcp.py` and `config.sample.json`. Suitable for a single `execute_phase` session post-Harness.
