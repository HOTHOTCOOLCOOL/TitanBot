# Draft V2

**Job ID**: `heavy_20260503_eywa_mcp`
**Session**: A — Lead / Synthesizer
**Phase**: A3 — Revised Technical Draft

---

## Synthesis of Critique

The Extreme Critic correctly identified that Draft V1 failed to answer the fundamental question of *whether* to adopt MCP over custom bridges, and severely underestimated the security surface of untrusted schema passthrough, unregulated outbound connections, and broken state lifecycles.

### Adopted Criticisms

1. **Evasion of the Adoption Decision**: We cannot use the mere existence of `mcp.py` as justification. We must explicitly justify MCP adoption vs. keeping custom bridges. (Adopted: Justified below based on the Eywa paper integration requirements).
2. **Untrusted `inputSchema` Passthrough**: Description sanitization is insufficient. Passing raw server-provided JSON schemas directly to the LLM bypasses our strict typing contracts and creates an injection/drift surface. (Adopted: We will enforce strict schema subset validation at registration).
3. **Outbound Connection Security Gap**: Opening an external connection at startup bypasses the L1 `verification.py` gate. (Adopted: MCP server connections must be treated as verified external resources subject to explicit domain allowlisting and formal admission control).
4. **Lifecycle & State Corruption**: Setting `_mcp_connected = True` before a successful connection and failing open leaves the agent in a permanently degraded state. (Adopted: We will implement atomic connection state management and explicit reconnect/fail semantics).
5. **Config Schema Under-evidenced**: We cannot just "add a key" to config without defining the full `MCPServerConfig` loader plumbing. (Adopted: Formal config model required).

### Rejected Criticisms

1. **Rejecting First-Class MCP Entirely**: 
   - *Criticism*: Is MCP needed at all compared to custom bridge tools like `ConsultCopilotTool`?
   - *Rejection Rationale*: While custom bridges are safer for single-purpose enterprise endpoints, the goal of integrating the "Eywa" architecture requires scaling to heterogeneous scientific foundation models. Maintaining custom wrappers for dozens of dynamic scientific tools does not scale. MCP is the required standard for this integration. We accept the integration pattern, provided we harden the boundary.
2. **Treating All Metadata Drift as Fatal**: 
   - *Criticism*: The local validation only implements a small subset of JSON schema semantics, making passthrough dangerous.
   - *Rejection Rationale*: We do not need to rewrite the entire JSON Schema engine locally to fix this. We can simply apply a "deny-by-default" validation filter that rejects complex/nested schemas not supported natively by Nanobot. This mitigates the risk without over-engineering a full schema parser.

---

## Revised Decision: Hardened First-Class MCP (The "Tsaheylu" Boundary)

We will formalize MCP as a first-class integration pattern, but wrap it in a strict "Tsaheylu" boundary (referencing the Eywa paper's connection mechanism) that enforces local verification, metadata sanitization, and strict lifecycle controls.

### Core Architecture Updates

1. **Formalized Config & Admission Control (MCP-internal gate)**:
   - Introduce a formal `MCPServerConfig` object (new Pydantic model in `config/schema.py`).
   - Enforce domain/command allowlisting **inside `connect_mcp_servers()`** in `mcp.py`: before opening any stdio or HTTP connection, validate the configured server command/URL against an explicit operator-defined allowlist. Any server not on the allowlist is skipped with a `logger.error` and never registered. This gate lives entirely in `mcp.py` and does **not** touch `verification.py` or the ADR-66 security layer (which remains Out of Scope).

2. **Strict Metadata Sanitization & Schema Validation**:
   - `MCPToolWrapper` must sanitize both `description` (truncate, strip injection patterns) AND `inputSchema`.
   - The `inputSchema` must be validated against a rigid, supported subset of JSON schema types. Any tool returning an unsupported schema type is rejected at registration.

3. **Lifecycle & Connection Integrity**:
   - Fix `loop.py` to only set `_mcp_connected = True` upon verified success.
   - Implement per-server atomic connection state. If one server fails to connect or drops, it fails cleanly without corrupting the global state or preventing other tools from functioning.

4. **Output Normalization**:
   - Ensure all non-`TextContent` blocks are safely serialized, rejected, or transformed, preserving the local Nanobot tool output contract to prevent output-content drift.

---

## Trade-off Rationale

1. **Extensibility vs. Security**: We trade away "plug-and-play" compatibility with any arbitrary public MCP server in favor of strict security. By enforcing strict `inputSchema` subset validation, some complex external tools will fail to register. This is acceptable to prevent untrusted metadata from corrupting the agent's context and bypassing the LLM interface.
2. **Startup Latency vs. Verification**: Running connection admission control (L1 verification) and tool schema validation at startup adds latency to the agent boot sequence. However, this is a necessary trade-off to ensure the agent never starts in an unverified state and that external boundaries are enforced before the first LLM interaction.
3. **Resilience vs. Completeness**: If an MCP server connection drops or fails verification, the agent will continue running, but those specific tools will be unavailable. We trade complete tool availability for overall agent resilience (the main loop must survive external server crashes and degrade gracefully).
