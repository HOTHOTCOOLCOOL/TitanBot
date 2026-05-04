# Phase 65 Reasoning Template Manual Test Guide

## Overview

This guide validates the ReasoningSkill implementation after automated tests have passed. The focus is Knowledge Graph durability, prompt-budget enforcement, and regression safety across the direct retrieval path and the `pre_fetched_kg` optimization path.

## Prerequisites

- A runnable Nanobot workspace.
- Permission to inspect or temporarily edit `memory/graph.json`.
- A Python environment that can import `nanobot.agent.context` and `nanobot.agent.knowledge_graph`.

## Test Scenario 1: Manual Reasoning Template Survives Rebuild

**Objective**: Verify hand-curated `reasoning_template` metadata is not erased by `rebuild_entity_index()`.

1. Prepare a temporary workspace or backup the current `memory/graph.json`.
2. Add a KG entity similar to:
   - `name`: `Reasoning: Manual Template`
   - `type`: `reasoning_template`
   - `summary`: any short template text
   - `triple_indices`: `[]`
3. Run a local check that instantiates `KnowledgeGraph` and calls `rebuild_entity_index()`.
4. Inspect the resulting entity payload.

**Expected Result**:

- The entity still exists after rebuild.
- `type` remains exactly `reasoning_template`.
- `summary` is preserved.

## Test Scenario 2: Direct KG Injection Applies the 1000-Character Cap

**Objective**: Verify `ContextBuilder` enforces the reasoning-template cap when it retrieves KG content directly.

1. Create a KG entity named `Reasoning: Huge`.
2. Set:
   - `type = "reasoning_template"`
   - `summary = "A" * 1500`
3. Build a prompt through `ContextBuilder.build_messages(..., knowledge_graph=kg)` with a query that matches the entity.
4. Inspect the system prompt content.

**Expected Result**:

- The prompt contains the reasoning template text.
- The injected reasoning block is capped at 1000 `A` characters.
- Content beyond that cap does not appear.

## Test Scenario 3: Pre-fetched KG Injection Matches Direct Behavior

**Objective**: Verify the `pre_fetched_kg` optimization path does not bypass the reasoning-template budget.

1. Reuse the `Reasoning: Huge` entity from Scenario 2.
2. Produce `pre_fetched_kg` from the KG retrieval path.
3. Call `ContextBuilder.build_messages(..., knowledge_graph=kg, pre_fetched_kg=pre_fetched_kg)`.
4. Inspect the resulting system prompt.

**Expected Result**:

- The prompt output matches the direct path behavior.
- The injected reasoning template is still capped at 1000 characters.

## Test Scenario 4: Ordinary KG Summaries Are Not Accidentally Truncated

**Objective**: Verify the new cap is scoped only to `reasoning_template`.

1. Create a normal KG entity named `Normal Entity`.
2. Set:
   - `type = ""` or omit the type
   - `summary = "B" * 1500`
3. Build the prompt with a matching query.
4. Inspect the system prompt.

**Expected Result**:

- The normal entity summary is injected in full.
- The new rule does not clip ordinary KG summaries.

## Regression Targets

Derived from the job blast-radius analysis, manually verify the following older behavior was not damaged:

1. **`context.py` still assembles a valid system prompt**: non-KG sections such as bootstrap files, memory, and session metadata still appear normally after the new formatter was introduced.
2. **`loop.py` prefetch flow still behaves consistently**: the main loop path that passes both `knowledge_graph` and `pre_fetched_kg` still yields the same prompt budget outcome as the direct retrieval path.
3. **`memory/graph.json` backward compatibility remains intact**: older graphs without entity `type` fields still load and query without crashes.
4. **Vector-assisted KG retrieval still works for ordinary entities**: semantic retrieval of non-reasoning entities still returns the expected summaries and does not inherit the reasoning-template cap.

## Recommended Final Check

After the four scenarios above pass, run one realistic prompt that should match a hand-curated reasoning template and one prompt that should match a normal entity summary. This is the fastest manual confirmation that the system now differentiates template-style reasoning hints from ordinary knowledge summaries.
