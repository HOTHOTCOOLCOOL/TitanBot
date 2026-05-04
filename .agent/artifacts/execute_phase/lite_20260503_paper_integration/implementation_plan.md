# Implementation Plan

## Job ID
`lite_20260503_paper_integration`

## Goal
Implement the P0 observability contract (mandatory `<think>` tag or `reasoning_content` pseudo-plan) and Allowed Write Set runtime interception based on the approved `harness_lite` candidate.

## Source Context
`.agent/artifacts/harness_lite/lite_20260503_paper_integration/candidate.md`

## Blast Radius Analysis
- **`nanobot/agent/loop.py`**: High impact. Modifies the core agent loop immediately before tool execution. A bug here could completely paralyze the agent by blocking all tools.
- **`nanobot/agent/verification.py` & `nanobot/agent/middleware/verification_mw.py`**: Medium impact. Adds L1 rules for filesystem boundary checking.
- **`tests/test_phase68_paper_integration.py`**: Low impact. Just adding new regression tests.

## Zone Declaration
**ZONE A**
Affects `loop.py`, `verification.py`, `verification_mw.py` and core middleware behavior.
Target pytest command:
`pytest tests/test_loop_integration.py tests/test_session_manager.py tests/test_middleware_pipeline.py tests/test_phase31_verification.py -W ignore -v`

## Implementation Strategy
1. **P0 Runtime Gate (`loop.py`)**: 
   - Locate the tool dispatch section in `_run_agent_loop_v2` (around line 887, right before `self.context.add_assistant_message`).
   - Extract `raw_text = response.content or ""` and `reasoning = response.reasoning_content or ""`.
   - Use a regex `(?s)<think>(.*?)</think>` to extract the plan block from `raw_text`.
   - Inside the extracted block (or directly inside `reasoning` if `reasoning_content` is provided without `<think>`), require at least one numbered or bulleted step: `re.search(r"(?m)^\s*(?:\d+\.|\-|\*)\s+\w+", text)`.
   - If invalid, append a user message: `Error: P0 observability contract violation. You must include a numbered or bulleted plan inside <think> tags (or native reasoning channel) before calling tools.` and execute `continue` to let the LLM retry.
   - If valid, log `logger.info("P0 Plan Verified")`.

2. **Allowed Write Set Enforcement (`verification_mw.py` & `verification.py`)**:
   - In `nanobot/agent/middleware/verification_mw.py`, retrieve the workspace from `self._agent.workspace`. Pass it into `verification.check_rules(..., workspace=self._agent.workspace)`.
   - Update `VerificationLayer.check_rules()` signature to accept `workspace: Path | str | None = None`. Pass this into `_check_rule_sensitive_path(..., workspace=workspace)`.
   - Inside `_check_rule_sensitive_path`, when processing `write_file` or `edit_file`, check if `workspace` is provided. If provided, use `pathlib.Path(resolved_norm).is_relative_to(Path(workspace).resolve())` to ensure the target is inside the workspace boundary.
   - If it escapes the workspace, add a `RuleViolation` stating "R07: Out of bounds write. Target path must be within the workspace directory."

## Contract / Data Structures / Function Signatures
```python
# loop.py inline helper
def _is_valid_plan(raw_text: str, reasoning: str) -> bool:
    import re
    plan_pattern = r"(?m)^\s*(?:\d+\.|\-|\*)\s+\w+"
    match = re.search(r"(?s)<think>(.*?)</think>", raw_text)
    if match and re.search(plan_pattern, match.group(1)):
        return True
    if reasoning and re.search(plan_pattern, reasoning):
        return True
    return False

# verification.py
def check_rules(..., workspace: Path | str | None = None) -> RuleResult:
    # ...
```

## Behavior Contract Matrix
| Scenario Input | Expected Behavior / Level | Hidden Runtime State | Auto Verification | Manual Proof Signal |
| --- | --- | --- | --- | --- |
| LLM calls tool without `<think>` or `reasoning_content` | Blocked at L0 loop, LLM prompted to retry | `response.content` remains in memory before ADR-62 null | `test_p0_observability_block` | Log: "P0 observability contract violation" |
| LLM writes `<think>1. ok</think>` and calls tool | Accepted | Tool dispatch proceeds | Regex validation test | Log: "P0 Plan Verified" |
| LLM provides native `reasoning_content` with `- step 1` (no `<think>`) | Accepted | Tool dispatch proceeds | `test_p0_observability_reasoning_only_pass` | Log: "P0 Plan Verified" |
| LLM calls `write_file` to `../outside_workspace.txt` | Blocked at L1 `VerificationMiddleware` | `VerificationLayer.check_rules()` path resolution | `test_allowed_write_set_block` | Log: "L1: Blocking X violation(s)" |

## Hermeticity / Hidden Runtime States Checklist
- [x] Streaming buffering: `LLMResponse` fully accumulates before reaching the check. No streaming edge cases to mock.
- [x] ADR-62 Nullification: The check occurs before `context.add_assistant_message` is called, ensuring we have the raw text.

## Runtime Artifact Parity Checklist
- `loop.py`: Python module loaded at startup. Modifies runtime dispatch directly.
- `verification_mw.py`: Python module. Loaded at startup.
- `verification.py`: Python module. Loaded at startup.

## Proof Signals / Observable Success Criteria
1. `logger.info("P0 Plan Verified")` appears in logs prior to tool execution.
2. `Error: P0 observability contract violation...` is injected into the LLM context if it fails.
3. `RuleViolation` for "Out of bounds write" is emitted when attacking the boundary.

## Risk Notes
- Standard models that don't natively stream `<think>` chunks may experience a slight TTFT penalty because they have to output the whole plan text before the tool call.
- The path check `is_relative_to` might fail if there are symlinks pointing outside the workspace. We should resolve paths fully.

## Validation Plan
1. Add a P0 block test `test_p0_observability_block` in `tests/test_phase68_paper_integration.py`.
2. Add a P0 reasoning-only pass test `test_p0_observability_reasoning_only_pass` in `tests/test_phase68_paper_integration.py`.
3. Add an Allowed Write Set probe test `test_allowed_write_set_block` targeting `../outside_workspace.txt` in `tests/test_phase68_paper_integration.py`.
