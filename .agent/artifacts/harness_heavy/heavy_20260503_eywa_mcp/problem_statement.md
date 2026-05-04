# Problem Statement

**Job ID**: `heavy_20260503_eywa_mcp`
**Session**: A — Lead / Synthesizer
**Phase**: A0 — Startup & Fact Baseline
**Date**: 2026-05-03

---

## Goal

Evaluate the Eywa paper (arXiv:2604.27351v1) recommendations and decide whether Nanobot should adopt **native MCP (Model Context Protocol) server support** as a first-class integration pattern, replacing or augmenting the current ad-hoc `MCPToolWrapper` implementation.

---

## Business / Technical Context

The Eywa paper demonstrates a heterogeneous agentic framework where domain-specific Foundation Models (FMs) are exposed as MCP servers, allowing an orchestrating LLM to invoke them via structured tool calls without needing full language translation. The paper's P1 recommendation from the prior `read_paper` analysis was:

> **Native MCP Support for Tools** — Aligning Nanobot's IPC and tool registry with the Model Context Protocol (MCP) will allow plug-and-play access to external domain-specific FMs without writing custom bridge code for each.

Nanobot already has:
- A partial `mcp.py` (`MCPToolWrapper`) that connects to MCP servers via `StdioServerParameters` or `streamable_http_client`
- A `ToolRegistry` that accepts dynamically registered tools
- Strict security boundary enforcement via `CapabilityTag` and `verification.py`

The question is whether the current partial MCP implementation is **sufficient**, or whether an architectural upgrade is warranted — and if so, what scope and risk it carries.

---

## In Scope

1. Audit of current `mcp.py` implementation — completeness vs. the MCP specification
2. Security implications of connecting to external MCP servers
3. Whether a formal `MCPServerConfig` and registry lifecycle management is needed
4. Whether MCP server tool descriptions should be trusted or sanitized before LLM injection
5. Whether MCP improves or conflicts with Nanobot's Single Host Agent architecture

---

## Out of Scope

1. EywaMAS (Peer-to-Peer Multi-Agent topology) — already rejected as `🔴 Not worth adding`
2. Full implementation / coding — this is Heavy; `execute_phase` handles implementation
3. Changes to the `verification.py` security layer itself (separate ADR-66 contract)
4. LiteLLM gateway migration (tracked separately under Phase 60)

---

## Decision Type

**Architecture / Integration** — medium blast radius. The decision affects:
- How external tools are loaded and sandboxed
- The security surface area via external MCP server connections
- Tool registry lifecycle and naming conventions

---

## Expected Deliverable

A candidate ADR (`adr_candidate.md`) clearly stating:
- Whether to formalize MCP as a first-class integration pattern in Nanobot
- What security controls are required
- What the minimum viable upgrade to `mcp.py` looks like (if any)
- What is explicitly left out
