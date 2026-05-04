# Candidate

## Adopted Criticisms
- `Severity A`: Core enforcement owner lacks a concrete file. We adopt the criticism and formally assign the P0 gate to `nanobot/agent/loop.py` immediately before tool dispatch.
- `Severity A`: Observability contradiction with ADR-62 (content is nulled). We adopt the criticism. The P0 gate must inspect `response.content` *before* `context.add_assistant_message` is called, or rely on `response.reasoning_content`.
- `Severity A`: Allowed Write Set lacks a runtime owner. We formally assign this to `VerificationLayer` (`nanobot/agent/verification.py`) which is called by `VerificationMiddleware`.
- `Severity B`: Plan validity rule is too vague. We adopt a strict regex rule for valid numbered plans inside `<think>`.
- `Severity B`: Provider/streaming semantics. We clarify that the LLM provider layer (`nanobot.providers.base.LLMProvider`) accumulates the full string before returning to `loop.py`, so linear regex is safe.

## Rejected Criticisms
- None. All criticisms from the review packet are valid and expose critical flaws in the draft V1.

## Final Candidate

### 1. P0 Runtime Owner (`nanobot/agent/loop.py`)
The Pre-Dispatch P0 Gate will be inserted in `nanobot/agent/loop.py`, right after the LLM returns `response`, around line 887 (before `add_assistant_message`).
```python
# Pseudo-code for loop.py
raw_text = response.content or ""
reasoning = response.reasoning_content or ""
if not (is_valid_plan(raw_text) or is_valid_plan(reasoning)):
    # Block dispatch, inject error
    messages.append({"role": "user", "content": "Error: P0 observability contract violation. You must include a numbered plan inside <think> tags before calling tools."})
    continue
```

### 2. Evidence Channel
Since ADR-62 nulls `assistant.content` when tools are present, the evidence channel cannot be the persistent `messages` history. The evidence channel will be **raw provider output (`response.content` / `response.reasoning_content`)** inspected at runtime. To ensure observability, the pre-dispatch gate will emit a telemetry log `logger.info(f"P0 Plan Verified")`.

### 3. Plan Validity Rule
A valid pseudo-plan must match the regex `(?s)<think>(.*?)</think>` and the extracted inner content must contain at least one numbered bullet point matching `r"(?m)^\s*\d+\.\s+\w+"`. An empty `<think>` or a missing `<think>` will trigger a rejection.

### 4. Allowed Write Set Owner (`nanobot/agent/verification.py`)
The boundary enforcement will live in `VerificationLayer.check_rules()` (invoked by `VerificationMiddleware`). It will enforce that any tool with write side-effects (`write_file`, `exec`) must have its target path checked against a static list of allowed roots (e.g., `self.workspace`). If a path is outside these roots, it throws an `l1_violation`.

### 5. Provider / Streaming Semantics
Because `loop.py` uses `provider.chat()` which fully accumulates streamed chunks into a final `LLMResponse` object before proceeding to tool dispatch, we do not need to parse partial streaming chunks. We only parse the finalized `response.content`.

## Runtime Preconditions / Parity Assumptions
- `nanobot/agent/loop.py` exists and controls the tool execution decision loop.
- `nanobot/agent/verification.py` handles L1 rules and can block tools via `VerificationMiddleware`.

## Residual Risks
- The LLM might learn to write "1. Plan" inside `<think>` just to bypass the gate without actually thinking. This is an unavoidable behavioral risk, but the contract itself will be enforced.

## Evidence Plan
1. **P0 Block Test**: Add a test that mocks `response.content = "tool call without think"` and asserts that tool dispatch is aborted.
2. **OOB Write Probe**: Add a test that calls `write_file` with `/etc/shadow` and asserts it is blocked by `VerificationLayer`.
