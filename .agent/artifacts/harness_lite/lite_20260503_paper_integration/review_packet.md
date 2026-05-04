# Review Packet

## Findings

- `Severity A` The draft's core enforcement owner is not grounded in the reviewed source-of-truth files. `baseline.md` names only `nanobot/agent/context.py` and `tests/test_phase68_paper_integration.py`, but `draft_v1.md` moves the real control point into an unnamed "tool parser/dispatcher in nanobot/agent" and an unnamed "tool execution layer". In the reviewed code, `nanobot/agent/context.py:302` only adds a prompt instruction for `<think>`; it does not show any pre-dispatch runtime gate. As written, the draft's main mechanism is still unowned.

- `Severity A` The visible-`<think>` observability contract is internally inconsistent with the reviewed message-shaping behavior. In `nanobot/agent/context.py:799-801`, assistant `content` is forcibly nulled whenever `tool_calls` are present. The current contradiction probe in `tests/test_phase68_paper_integration.py:134-168` proves that, under this message shape, a visible `<think>` block in assistant `content` cannot coexist with tool calls in the same stored assistant message. The draft does not resolve whether the required proof channel is raw provider output, `reasoning_content`, assistant `content`, or separate telemetry.

- `Severity A` Allowed Write Set enforcement has no verified runtime owner. `problem_statement.md` explicitly puts runtime-level write boundary enforcement in scope, and `baseline.md` asks whether the boundary is hard code or just prompt guidance. The reviewed files do not show any `allowed_write_set` structure, validator, executor hook, or rejection path. The draft's "strict allowed_write_set validation at the tool execution level" is therefore still an unsupported claim.

- `Severity B` The current P0 regression only proves prompt presence, not enforcement. `tests/test_phase68_paper_integration.py:90-94` checks only that the built system prompt contains `<think>` and the phrase `pseudo-plan`. That is compatible with the exact false-positive path the baseline warns about: the prompt says the right thing, but runtime still accepts immediate tool calls.

- `Severity B` The draft's assumption that "the runtime intercepts the raw text and can easily check for `<think>...</think>` before executing the tool" is unverified, especially for structured tool-calling or streaming providers. None of the reviewed source-of-truth files identify where raw provider output is buffered, how numbered-plan validation is performed, or what happens if tool calls arrive before a closing `</think>`.

- `Severity B` The draft does not define what qualifies as a valid pseudo-plan. The baseline question attacks the empty-plan false positive, but the draft still leaves acceptance ambiguous between:
  - any `<think>` tag,
  - a numbered or bulleted plan,
  - a plan in `reasoning_content`,
  - or a visible plan in assistant `content`.

## Must Keep

- Keep the draft's central correction that prompt-only wording is not enough for a runtime-sensitive mechanism.

- Keep the baseline's emphasis on false positives where the answer looks right but the mechanism never actually fired.

- Keep the requirement that any Allowed Write Set claim must be backed by a fail-closed runtime rejection, not by LLM obedience.

- Keep the demand for pre-dispatch proof signals. For this task, "the system prompt contains `<think>`" is not a sufficient proof signal.

## Weak Claims / Unverified Claims

- "The tool parser/dispatcher in `nanobot/agent` must be modified" is too vague to review. No concrete repo file is named in the reviewed artifacts.

- "We will introduce a strict `allowed_write_set` validation at the tool execution level" is unverified. No executor or validator file is identified in the reviewed inputs.

- "Dynamic overrides passed via explicit tool schemas" is unverified. No reviewed file shows such a schema field or a consumer for it.

- "The runtime intercepts the raw text and can easily check for `<think>` before executing the tool" is unverified. The reviewed files do not show a raw-response gate.

- The current contradiction test proves one impossibility in the reviewed `ContextBuilder` message shape, but it does not by itself prove where the correct evidence channel should move next.

## False Positive Risks

- The prompt can contain a correct `<think>` instruction while runtime still executes immediate tool calls. This is already compatible with `tests/test_phase68_paper_integration.py:90-94`.

- Planning may appear in `reasoning_content` or another hidden provider field while assistant `content` remains empty or null. External observers may believe P0 worked even though the chosen observability contract was never met.

- A `<think>` block can exist but still fail the intended contract if it is empty, non-numbered, or semantically useless. The draft currently names this risk but does not close it.

- Allowed Write Set can appear "successful" in tests simply because the model chose an in-bounds path. Without a forced out-of-bounds rejection probe, the boundary is still prompt-level theater.

- Post-normalization history inspection can erase the very evidence channel being claimed. If the contract depends on visible assistant `content`, `nanobot/agent/context.py:799-801` is already a danger sign.

## Acceptance Checklist

- `A1 / Runtime Owner`
  - `Claim`: The candidate names the exact runtime owner file for the pre-dispatch P0 gate.
  - `Evidence Method`: Cite the concrete repo file path and the exact control point where provider output is inspected before tool dispatch.
  - `Proof Signal`: A file-level ownership statement that is specific enough to hand to `execute_phase`.
  - `Expected Result`: No phrases like "parser/dispatcher in nanobot/agent" without a file path.
  - `If Fail`: The candidate remains under-specified and is not ready for implementation.

- `A2 / Evidence Channel`
  - `Claim`: The candidate explicitly chooses the accepted proof channel for pseudo-plan observability: raw provider output, `reasoning_content`, assistant `content`, or separate telemetry.
  - `Evidence Method`: Reconcile that choice against `nanobot/agent/context.py:799-801`.
  - `Proof Signal`: A contradiction-free statement of what must be observed and where.
  - `Expected Result`: The candidate no longer demands an impossible visible `<think>` signal in a channel that is nulled during tool calls.
  - `If Fail`: The design still contains an internal observability contradiction.

- `A3 / Plan Validity Rule`
  - `Claim`: The candidate defines what counts as a valid pseudo-plan.
  - `Evidence Method`: Enumerate rejection cases for empty `<think>`, non-numbered `<think>`, and direct tool call with no accepted plan.
  - `Proof Signal`: A deterministic validation rule, not a vibe-based interpretation.
  - `Expected Result`: False Positive 1 is closed.
  - `If Fail`: Tag presence alone will continue to masquerade as enforcement.

- `A4 / Pre-Dispatch Abort`
  - `Claim`: Tool dispatch is blocked when the P0 contract is not satisfied.
  - `Evidence Method`: Define a concrete runtime probe that observes rejection before any tool side effect.
  - `Proof Signal`: Observable abort/error emitted before tool execution.
  - `Expected Result`: The design distinguishes "model answered with tools" from "runtime accepted tools".
  - `If Fail`: The observability contract stays fail-open.

- `A5 / Allowed Write Set Owner`
  - `Claim`: The candidate names the exact runtime owner for write-boundary enforcement.
  - `Evidence Method`: Cite the concrete repo file and boundary source for the allowed set.
  - `Proof Signal`: A defined validator/executor rejection path for out-of-bounds writes.
  - `Expected Result`: The candidate can explain where the boundary lives and who checks it.
  - `If Fail`: Allowed Write Set remains only a prompt suggestion.

- `A6 / Out-of-Bounds Rejection Probe`
  - `Claim`: The candidate defines one minimal probe that attempts a write outside the allowed set.
  - `Evidence Method`: Force an out-of-bounds write request and specify the expected rejection artifact.
  - `Proof Signal`: Deterministic observable error from runtime, not "the model should avoid this".
  - `Expected Result`: False Positive 2 is closed.
  - `If Fail`: The write-boundary claim is still unproven.

- `A7 / Provider / Streaming Semantics`
  - `Claim`: The candidate explains how structured tool-calling or streaming responses interact with the chosen P0 evidence channel.
  - `Evidence Method`: State whether partial `<think>` chunks, `reasoning_content`, and immediate tool-call emission are accepted, rejected, or transformed.
  - `Proof Signal`: A concrete runtime rule for those cases.
  - `Expected Result`: The candidate no longer assumes a simple linear text parser if the provider path is structured.
  - `If Fail`: The design is fragile against the exact runtime-sensitive cases that triggered this re-review.

- `A8 / Scope Sanity`
  - `Claim`: The candidate states whether the current write boundary is sufficient, or whether this must be escalated to a broader harness / wider write set.
  - `Evidence Method`: Compare the chosen mechanism to the files actually available for implementation.
  - `Proof Signal`: An explicit `implementable as-scoped` or `BLOCKED unless scope expands` statement.
  - `Expected Result`: No hidden dependency on unspecified runtime files.
  - `If Fail`: `execute_phase` will be handed an impossible or misleading contract.
