# Baseline: 事实真值表

## Claim / Evidence / Status
- **Claim**: The agent uses a `<think>` tag to formulate a pseudo-plan before executing tool calls, and adheres to a strict Allowed Write Set.
- **Evidence**: Currently only assumed through system prompt instructions in `nanobot/agent/context.py` according to the previous plan.
- **Status**: Weak. If the LLM ignores the prompt and emits a tool call immediately, or writes outside the permitted boundary, the system might still execute it (Fail-open).

## Source of Truth Files
- `nanobot/agent/context.py` (Prompt formulation)
- `tests/test_phase68_paper_integration.py` (Regression tests)

## Runtime Artifacts / Hidden Runtime States
- `LLM Response Stream`: The raw text stream from the LLM before tool parsing.
- `Tool Execution Engine State`: Whether it accepts tool calls before seeing a valid `<think>` block.
- `Allowed Write Set Configuration`: The runtime enforcement list of filesystem paths or external states the LLM is permitted to mutate. 

## Observable Proof Signals
- **Proof Signal 1 (Observability Contract)**: The telemetry/log explicitly captures the content of the `<think>` block *prior* to any `function_call` or tool execution being dispatched. The parser explicitly aborts if the tag is missing.
- **Proof Signal 2 (Allowed Write Set)**: Any write action proposed outside the authorized path list (or any tool call lacking an explicit write scope) is rejected by the tool executor layer with an observable error.

## Unknowns
- Does the current tool parser strictly block tool calls that are not preceded by a `<think>` block, or does it silently allow them?
- How is the Allowed Write Set currently enforced at the tool boundary? Is it just a prompt suggestion or a hard code-level constraint?

## Questions the Critic Must Attack
1. If the LLM completely omits the `<think>` tag and directly emits a tool call, will the system execute it anyway? (False positive risk)
2. If the LLM writes a plan inside `<think>` but proposes a write operation outside the Allowed Write Set, does the system block it, or does it just rely on the prompt to discourage it?
