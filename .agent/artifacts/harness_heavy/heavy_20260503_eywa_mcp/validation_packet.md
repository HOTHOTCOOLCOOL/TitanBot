# Validation Packet

**Job ID**: `heavy_20260503_eywa_mcp`  
**Session**: C - Validator / Evidence Auditor  
**Phase**: C4 - Validation Packet

This packet validates `draft_v2.md` against `problem_statement.md`, `baseline.md`, `critique.md`, and only the explicitly named repo files. It does not make the final decision for Session A.

---

## Must Keep

- Keep the correction to the core decision frame: the adoption question must be answered on its own merits, not inferred from the mere existence of `mcp.py`. This directly answers the original goal in `problem_statement.md:12-27` and preserves the critic's main correction in `critique.md:13-16`.

- Keep the broadened trust-boundary model around MCP metadata. `draft_v2.md:16`, `draft_v2.md:42-44`, `nanobot/agent/tools/mcp.py:21-22`, `nanobot/agent/tools/base.py:141-149`, and `nanobot/agent/loop.py:680-682` together show that the correct surface is not just description text, but the full tool contract exposed to the model.

- Keep the lifecycle integrity fix as a first-order requirement. `draft_v2.md:18`, `draft_v2.md:46-48`, and `nanobot/agent/loop.py:431-437` / `1038-1045` correctly focus on the fact that connection state can be poisoned today.

- Keep the requirement that MCP remains opt-in and bounded. That stays aligned with `baseline.md:40-44` and with the Single Host Agent constraint in `problem_statement.md:31-37`.

- Keep the output-normalization concern. `draft_v2.md:50-51` correctly addresses the drift identified in `critique.md:65-71` and the current `str(block)` fallback in `nanobot/agent/tools/mcp.py:45-49`.

- Keep the config coherence problem, but restate it precisely: the real gap is not the absence of an MCP config model, but the mismatch between runtime/schema support and the operator-facing sample config. `config.sample.json:79-87` lacks `mcp_servers`, while `nanobot/config/schema.py:462-485` already defines `MCPServerConfig` and `tools.mcp_servers`.

---

## Resolved vs Unresolved

| Item | Status | Evidence | Validation Note |
|---|---|---|---|
| Adoption question is now addressed explicitly | Partially Resolved | `draft_v2.md:15-19`, `draft_v2.md:23-28` | V2 no longer relies on "MCP already exists" as justification. However, the claim that MCP is the required standard for Eywa-style integration is still asserted, not demonstrated from allowed repo evidence. |
| Metadata risk widened from description-only to full contract boundary | Resolved in design intent | `draft_v2.md:16`, `draft_v2.md:42-44`; `nanobot/agent/tools/mcp.py:21-22`; `nanobot/agent/tools/base.py:93-149` | This is a real improvement over V1 and should survive into later artifacts. |
| Lifecycle corruption is correctly identified | Resolved in design intent | `draft_v2.md:18`, `draft_v2.md:46-48`; `nanobot/agent/loop.py:431-437`, `1038-1045` | V2 is targeting the correct failure mode: poisoned global connection state. |
| Config model gap is understood accurately | Unresolved | `draft_v2.md:19`, `draft_v2.md:38-40`; `nanobot/config/schema.py:462-485`; `config.sample.json:79-87` | V2 still claims a new `MCPServerConfig` must be introduced, but the repo already has it. The actual unresolved gap is sample/config plumbing and operator documentation. |
| Security boundary story is coherent with baseline constraints | Unresolved | `baseline.md:40-44`; `critique.md:18-21`; `draft_v2.md:17`, `draft_v2.md:38-40`, `draft_v2.md:58`; `nanobot/agent/verification.py:425-483` | V2 says the gate can live entirely inside `mcp.py` while also describing it as "L1 verification". On the allowed evidence set, equivalence to the baseline ADR-66 boundary is not yet proven. |
| Schema subset policy is concrete enough for verification | Unresolved | `draft_v2.md:27-28`, `draft_v2.md:43-44`; `nanobot/agent/tools/base.py:93-139` | "Rigid supported subset" is directionally correct, but the subset is not yet defined precisely enough to test. |
| Per-server failure isolation is specified well enough | Unresolved | `draft_v2.md:47-48`; `nanobot/agent/tools/mcp.py:60-89`; `nanobot/agent/loop.py:431-437` | The target behavior is good, but V2 does not yet define the concrete state machine for partial startup failure, runtime drop, unregister/retry, or close/reset semantics. |
| Draft V2 is complete enough for downstream evidence planning | Unresolved | Workflow requirement in `harness_heavy.md`; `draft_v2.md:55-59` | `draft_v2.md` includes `Adopted Criticisms`, `Rejected Criticisms`, and `Trade-off Rationale`, but it does not include explicit `Updated Risks` or `Open Verification Items`, which weakens the next-stage handoff. |

---

## Unverified Claims

| Claim | Status | Why It Is Not Yet Validated |
|---|---|---|
| "`MCP is the required standard` for the Eywa integration target." (`draft_v2.md:25`) | Unverified | The allowed repo evidence does not show a comparative maintenance analysis against the current custom-bridge pattern. This remains a strategic claim, not a validated repo fact. |
| "Introduce a formal `MCPServerConfig` object (new Pydantic model in `config/schema.py`)." (`draft_v2.md:39`) | Contradicted by repo evidence | `nanobot/config/schema.py:462-485` already defines `MCPServerConfig` and `tools.mcp_servers`. The config issue is documentation/plumbing drift, not model absence. |
| An allowlist gate inside `mcp.py` is sufficient while leaving `verification.py` untouched. (`draft_v2.md:40`) | Unverified | This may be a valid design, but V2 does not yet prove that it satisfies the baseline requirement in `baseline.md:43` for new external integrations to pass L1/path-boundary checks. |
| A deny-by-default schema subset is enough without a fuller local schema engine. (`draft_v2.md:28`, `draft_v2.md:43-44`) | Unverified | The subset is not specified, so we cannot yet tell whether it safely rejects risky schemas while still admitting the target MCP tools. |
| Per-server atomic state management can preserve resilience without hidden regressions. (`draft_v2.md:47-48`, `draft_v2.md:59`) | Unverified | The desired behavior is clear, but the reconnection and cleanup contract is not yet concrete enough for audit or test design. |
| Output normalization can preserve the Nanobot contract for non-text MCP blocks. (`draft_v2.md:50-51`) | Unverified | V2 identifies the problem correctly, but it does not yet define whether non-text blocks are serialized, transformed, or rejected. |

---

## Acceptance Matrix

| A# | Claim | Evidence Method | Expected Result | If Fail, What It Means |
|---|---|---|---|---|
| A1 | First-class MCP is justified over keeping MCP private or continuing with only custom bridge tools for the Eywa-target scope. | ADR text review against `problem_statement.md`, `baseline.md`, and current repo capabilities. | The rationale compares MCP with the existing bridge pattern and no longer relies on "the code already exists" as justification. | The adoption premise is still under-argued; return to Phase A3 before ADR candidate. |
| A2 | Untrusted MCP server admission is denied by default before any outbound connection or tool registration occurs. | Code inspection and tests around `connect_mcp_servers()` in `mcp.py`. | Disallowed command/URL entries are rejected before `stdio_client` / `streamable_http_client` and before `registry.register(wrapper)`. | The external connection boundary remains uncontrolled. |
| A3 | Raw MCP metadata does not reach model-visible tool definitions without local filtering. | Code inspection and tests across `MCPToolWrapper`, registration flow, and tool-definition export. | Unsupported `description` / `inputSchema` content is sanitized or rejected before appearing in `tools=(...).get_definitions()`. | Prompt/contract drift is still present at the model boundary. |
| A4 | The supported JSON Schema subset is explicit, deny-by-default, and testable. | File assertions plus positive/negative tests against representative schemas. | Supported constructs are documented; unsupported or nested constructs fail deterministically at registration. | "Schema subset validation" remains too vague to trust. |
| A5 | The MCP config contract is coherent across schema and sample configuration. | File assertions in `nanobot/config/schema.py` and `config.sample.json`. | `tools.mcp_servers` is documented consistently, and the proposal does not claim to introduce config models that already exist. | Operator setup remains ambiguous and the design is still based on stale config assumptions. |
| A6 | MCP connection state is atomic and recoverable. | Code inspection and lifecycle tests of `_connect_mcp()` and `close_mcp()` in `loop.py`. | `_mcp_connected` flips only after successful connection, and cleanup/reset semantics are explicit on failure and close. | The agent can still enter a poisoned or permanently degraded MCP state. |
| A7 | A failing MCP server does not corrupt unrelated MCP servers or the main agent loop. | Multi-server startup/runtime tests with one healthy server and one failing server. | Healthy servers remain registered and usable; failure is isolated, logged, and recoverable. | The resilience claim in V2 is not achieved. |
| A8 | Non-text MCP output is normalized to a stable Nanobot-native contract. | Code inspection and tests covering `TextContent` and non-text content blocks. | Non-text blocks are deterministically serialized, transformed, or rejected; the system no longer relies on arbitrary `str(block)` output. | Output-content drift remains unresolved. |
| A9 | The security-boundary story is internally consistent with the Out-of-Scope constraint on `verification.py`. | Design review plus code-path proof. | The author either proves that the MCP-internal gate satisfies the baseline security requirement without modifying `verification.py`, or explicitly narrows/revises the claim. | The proposal still contains an unresolved boundary contradiction and should not advance as if settled. |
| A10 | Downstream artifacts have explicit risk and verification bookkeeping. | File assertion on the next revised design artifact or ADR handoff. | `Updated Risks` and `Open Verification Items` are explicit enough for `evidence_plan.md` to map evidence to A# items cleanly. | Evidence Gate inputs will be weak or incomplete, increasing the risk of papering over unresolved claims. |
