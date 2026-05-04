# Job 20260426 Manual Test Guide

## Overview

This guide validates the new `consult_copilot_studio` built-in tool after automated tests have passed. The focus is runtime wiring, failure handling, and blast-radius regression checks around tool registration and config loading.

## Prerequisites

- A runnable Nanobot instance.
- A valid config file with the `tools.copilot_studio` or `tools.copilotStudio` block.
- For live end-to-end validation, a working Copilot Studio Direct Line secret.

## Test Scenario 1: Disabled or Missing Secret Fails Cleanly

**Objective**: Verify the tool does not crash the agent loop when configuration is incomplete.

1. Set `tools.copilot_studio.enabled` to `false`, or leave `secret` empty.
2. Start a fresh session.
3. Ask Nanobot to use `consult_copilot_studio` for a simple question.

**Expected Result**:

- The tool call returns an `Error: ...` string.
- The agent loop remains responsive.
- No startup or tool-registry crash occurs.

## Test Scenario 2: Live Copilot Round Trip

**Objective**: Verify the built-in tool is registered and can complete one Direct Line conversation.

1. Set `tools.copilot_studio.enabled` to `true`.
2. Provide a valid Direct Line secret.
3. Start a fresh session.
4. Ask Nanobot: `请使用 consult_copilot_studio 工具，询问“请用一句话介绍你自己”。`

**Expected Result**:

- Nanobot successfully resolves and invokes `consult_copilot_studio`.
- The returned text comes back through the local agent without a registry or config error.
- The reply is attributable to the Copilot Studio side rather than a local fallback answer.

## Test Scenario 3: Invalid Secret Surfaces a Diagnosable Error

**Objective**: Verify Direct Line failures remain visible and actionable.

1. Replace the valid secret with an invalid one.
2. Repeat the same prompt.

**Expected Result**:

- The tool returns an `Error: ...` string instead of hanging silently.
- Nanobot remains usable after the failed call.
- The failure message is specific enough to distinguish auth or HTTP problems from generic tool lookup failures.

## Regression Targets

Derived from the Blast Radius Analysis, manually verify the following older behavior was not damaged:

1. **Default tool registry still works**: invoke one known existing built-in tool in your environment and confirm registration still succeeds after adding `consult_copilot_studio`.
2. **Config loading still accepts the updated tools block**: restart Nanobot with the new config and confirm startup succeeds without schema errors.
3. **Agent loop still treats tool failures as recoverable**: after forcing one Copilot Studio failure, ask a normal follow-up question and confirm the session continues normally.
4. **Tool setup changes did not leak into plugin loading behavior**: if you use any existing plugin tool, confirm it still loads independently of the new built-in registration path.

## Recommended Final Check

After the three scenarios above pass, keep the valid secret in place and run one realistic enterprise question that is hard for the local agent alone. This is the fastest way to confirm the tool adds real value rather than only passing synthetic smoke tests.
