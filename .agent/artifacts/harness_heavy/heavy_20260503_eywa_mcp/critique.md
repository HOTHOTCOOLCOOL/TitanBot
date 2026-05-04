# Critique

**Job ID**: `heavy_20260503_eywa_mcp`  
**Session**: B - Extreme Critic  
**Phase**: B2 - Extreme Critic

This document is intentionally adversarial. It attacks `draft_v1.md` as a decision artifact. It does not provide the final integrated design.

---

## Findings

1. **Draft V1 evades the actual decision question and prematurely collapses the option space.**  
   `problem_statement.md:12-27` asks whether Nanobot should adopt native MCP as a first-class integration pattern, replacing or augmenting the current wrapper. `baseline.md:62-66` explicitly requires attacking whether MCP is needed at all, and what the real maintenance delta is versus custom bridge tools.  
   But `draft_v1.md:17` reframes the core question as "not should we adopt MCP - it already exists." That is a category error. Existing partial code does not prove that first-class adoption is justified, nor that productizing it beats keeping it private, undocumented, or narrowly scoped.  
   This is the largest decision-quality flaw in the draft: it uses existence as proxy for approval.

2. **The biggest security gap is not description text; it is the new outbound connection path that sits outside the proven L1 verification boundary.**  
   `nanobot/agent/loop.py:429-437` shows `_connect_mcp()` directly opens MCP connections and registers tools. `nanobot/agent/loop.py:978-981` shows this happens at agent startup before normal message processing. `nanobot/agent/tools/mcp.py:67-70` passes `cfg.url` directly into `streamable_http_client(cfg.url)`.  
   Meanwhile `nanobot/agent/verification.py:425-483` shows the visible L1 tag-driven enforcement is centered on `CapabilityTag.DESTRUCTIVE`, not on outbound MCP server connection approval or remote endpoint policy.  
   `baseline.md:43` states that any new external integration must pass L1 path/boundary checks. `draft_v1.md:59` says `verification.py` / ADR-66 contracts remain unchanged. On the allowed evidence set, that claim is not supported. First-class MCP creates a startup-time external connection surface that is not shown to be governed by the same boundary.

3. **Draft V1 attacks raw description passthrough but misses the larger untrusted metadata surface: raw `inputSchema` passthrough.**  
   `nanobot/agent/tools/mcp.py:21-22` forwards both `tool_def.description` and `tool_def.inputSchema` from the remote server. `nanobot/agent/tools/base.py:142-149` forwards both into the provider tool schema. `nanobot/agent/loop.py:680-682` passes those tool definitions directly to the model via `tools=...`.  
   But local validation in `nanobot/agent/tools/base.py:93-139` only implements a small subset of JSON Schema semantics. There is no evidence here for full enforcement of server-supplied schema behavior.  
   Result: the draft treats this as a "description sanitization" problem when it is actually a broader "untrusted tool metadata contract" problem. A 500-char description cap does nothing about oversized or semantically drifting `inputSchema`.

4. **The lifecycle failure model is mischaracterized. The real problem is fail-open startup and permanent degraded state, not merely missing reconnect.**  
   `nanobot/agent/loop.py:431-437` sets `_mcp_connected = True` before connection succeeds. `nanobot/agent/tools/mcp.py:61-89` catches per-server failures and logs them instead of surfacing a hard failure. `nanobot/agent/loop.py:1038-1045` closes the stack but does not reset `_mcp_connected`.  
   That means the system can enter a partial-registration state and then permanently skip future reconnect attempts. This is materially different from the draft's wording in `draft_v1.md:36`, which focuses on mid-session crash behavior.  
   Also, `nanobot/agent/tools/registry.py:77-80` shows runtime tool failures are surfaced as `Error executing ...`, so "fail silently with generic errors" is overstated. The startup/teardown semantics are the more serious issue.

5. **The draft overstates what `UNTRUSTED_EXTERNAL` buys you.**  
   `nanobot/agent/tools/mcp.py:29-30` confirms the tag is assigned. But in the allowed evidence set, `nanobot/agent/verification.py:425-483` only shows an active hard block for `CapabilityTag.DESTRUCTIVE`.  
   `baseline.md:63` explicitly asked whether `UNTRUSTED_EXTERNAL` is sufficient. `draft_v1.md:55` effectively treats it as "already correct" and done. That is too charitable. In the visible code, this tag is classification metadata; it is not demonstrated to be a mitigation for prompt injection, endpoint trust, connection policy, or registry admission.

6. **The scope estimate and compatibility claims are under-evidenced.**  
   `draft_v1.md:75`, `draft_v1.md:78`, `draft_v1.md:88`, and `draft_v1.md:109` claim the work is small, additive, and likely under 100 LOC across `mcp.py` and `config.sample.json`.  
   But `problem_statement.md:35` explicitly includes the need for a formal `MCPServerConfig`. The allowed evidence does not show such a config model or loader path. Worse, `nanobot/agent/tools/mcp.py:62-70` expects `cfg.command`, `cfg.args`, `cfg.env`, and `cfg.url` as attribute-style fields, not raw JSON dict access.  
   Without evidence from config schema/loader wiring, "add a sample key and keep the existing API unchanged" is not an evidence-based claim.

---

## Fatal Assumptions

- **Assumption A: partial implementation equals adoption justification.**  
  The draft assumes that because MCP exists in code, the remaining question is hardening. That bypasses the required comparison against "do not formalize" or "keep private/power-user-only."

- **Assumption B: `UNTRUSTED_EXTERNAL` is a real security control in this path.**  
  The visible evidence proves assignment, not enforcement.

- **Assumption C: description sanitization is the main trust problem.**  
  Raw `inputSchema` passthrough, startup-time outbound connection policy, and partial local schema enforcement are at least as important.

- **Assumption D: config exposure is additive and low-risk.**  
  The current evidence does not prove end-to-end config plumbing or a stable server config contract.

- **Assumption E: no `verification.py` implications.**  
  That only holds if first-class MCP is constrained so that the external connection boundary is governed elsewhere. The draft does not prove that.

---

## Contract Drift Risks

- **Tool metadata drift:** Remote `description` and `inputSchema` are presented to the model as if they were trustworthy local tool contracts, but local validation only enforces a subset of schema semantics (`nanobot/agent/tools/base.py:93-139`).

- **Output-content drift:** `nanobot/agent/tools/mcp.py:45-49` coerces every non-`TextContent` block to `str(block)`. If the remote server returns richer structures, the wrapper degrades them into opaque strings instead of a stable Nanobot-native contract.

- **Threat-model wording drift:** `draft_v1.md:35` and `draft_v1.md:65` describe the description issue as injection into the "system context." The allowed code shows tool metadata is passed through the `tools=` channel (`nanobot/agent/loop.py:680-682`), not literally appended into the system prompt. The security concern is still real, but the mechanism matters because the mitigation may differ.

- **Operational-state drift:** The system can treat itself as "MCP connected" while some or all configured servers failed during connection, producing a misleading runtime state.

---

## Where Draft V1 Overreaches

- `draft_v1.md:17` overreaches by replacing the adoption decision with a hardening decision.

- `draft_v1.md:44-52` overreaches by presenting "description sanitization + config schema + reconnect guard" as sufficient without addressing endpoint trust policy, raw schema passthrough, or startup-time admission control.

- `draft_v1.md:59` overreaches by asserting `verification.py` / ADR-66 can stay untouched when the visible connection path bypasses the demonstrated L1 tool-call gate.

- `draft_v1.md:65-67` overreaches by treating description passthrough as already enough to reject Option B on ADR-66 grounds, while the draft does not prove the full threat chain or compare it against narrower alternatives.

- `draft_v1.md:78` and `draft_v1.md:88` overreach by calling compatibility additive and the `mcp_servers` API stable without evidence of the config object model.

- `draft_v1.md:107-109` overreach by downgrading G3-G5 and compressing the scope to a small `execute_phase`. The lifecycle and contract issues exposed above suggest the draft is not yet mature enough for a small, two-file implementation estimate.

---

## What Is Still Worth Keeping

- The draft is right that MCP is not greenfield here. There is already real code in `mcp.py`, lazy startup plumbing in `loop.py`, and registry integration. That matters.

- The draft is right to preserve the "Single Host Agent" boundary. Nothing in the allowed evidence requires peer-to-peer agent topology to use MCP.

- The draft is right that `config.sample.json` currently leaves MCP undocumented and that `TOOLS.md` gives tool #15 only a shallow audit.

- The draft is right that raw description passthrough is a genuine red flag. It should remain in the next revision, but it must be framed as one part of a broader untrusted metadata and connection-boundary problem.

- The draft is right that lifecycle management already uses `AsyncExitStack`; that is a useful starting point even though the current state machine is not resilient enough.
