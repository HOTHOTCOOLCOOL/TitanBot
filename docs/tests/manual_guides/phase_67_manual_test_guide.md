# Phase 67: KnowledgeMapTool Manual Test Guide

## Overview
This guide provides instructions for manually testing the `KnowledgeMapTool` introduced in ADR-67. While the tool is covered by automated unit tests (`A2` through `A5`), human verification is required to ensure the output is logically coherent, and that it integrates correctly with the LLM's decision-making process.

## Prerequisites
- A running Nanobot instance (`python start_console.py` or similar).
- A populated `workspace/memory/graph.json` file. (If empty, the agent should gracefully return an error prefix).

## Test Scenario 1: Basic Tool Invocation
**Objective**: Verify the agent can correctly call the tool and interpret its output.
1. Clear your session memory to avoid context pollution: `/new`
2. Ask the agent a broad, exploratory question: *"你能给我展示一下你目前知识库里都有哪些主要的领域地图吗？请使用 knowledge_map 工具。"*
3. **Expected Result**: 
   - The agent should invoke `knowledge_map`.
   - The agent should respond with a summarized list of domains, accurately reflecting the top hubs in `graph.json`.
   - No exceptions or errors should be visible in the console.

## Test Scenario 2: Zero-Shot Routing (Search-First Fallback)
**Objective**: Verify the agent uses `knowledge_map` as a fallback when `memory` search fails.
1. Clear your session memory: `/new`
2. Ask the agent a question that spans multiple domains or is extremely vague: *"我不知道该怎么搜，关于系统架构设计，你有学过哪些关联的子模块？请先自己摸底。"*
3. **Expected Result**:
   - The agent may first try to use `memory` with a vague query.
   - Upon failing or getting poor results, it should fall back to calling `knowledge_map`.
   - It should then use the topology map to construct better, more specific `memory` search queries.

## 连带回归靶点 (Regression Targets)
From the Blast Radius Analysis, the following core features are the most susceptible to unintended damage during this update. Please manually verify them:

1. **Tool Setup (`tool_setup.py`) Integrity**:
   - Verify that other core tools are still successfully registered.
   - **Test**: Ask the agent to run a simple bash command (`请帮我执行 echo hello`). Ensure it does not crash during tool lookup.
2. **Global Tool Registry Output Limit**:
   - Verify that standard truncations across all tools still function.
   - **Test**: Ask the agent to read a very large file, and ensure it ends with `[OUTPUT TRUNCATED]` without crashing the loop.

## Field Notes From 2026-05-04 Acceptance
- Scenario 2 may surface as a parallel tool fan-out (`knowledge_map` plus one or more `memory` calls in the same reasoning round) rather than a strictly serial fallback chain. Treat this as acceptable if `knowledge_map` clearly participates in refining the topic map and the later `memory` query becomes more specific.
- For the truncation regression, the dashboard-visible reply is the source of truth. The backend `Response to dashboard:web:` log line may only print a head preview and may not include the final `[OUTPUT TRUNCATED]` footer even when truncation is functioning correctly.
- If the live workspace already contains strong architecture-related RAG/KG context, Scenario 2 can short-circuit before explicit tool invocation. In that case, rerun against a graph-only test workspace or otherwise reduce pre-injected topic memory.
