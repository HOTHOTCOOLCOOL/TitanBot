# Draft V1

## 当前方案摘要 (Current Draft Summary)
To harden the P0 feature (Pseudo-Plan Guided Skill Retrieval), we must move from a "Prompt-only" contract to a "Runtime-enforced" contract. 
1. **P0 Observability Contract**: The tool parser/dispatcher in `nanobot/agent` must be modified to *reject* any tool invocation if a `<think>` block containing a numbered plan has not been detected in the current turn.
2. **Allowed Write Set Enforcement**: We will introduce a strict `allowed_write_set` validation at the tool execution level. Any tool call that attempts a write operation must be validated against this set before execution. If the path is out of bounds, the tool call must raise an observable runtime error, not just rely on LLM alignment.

## 关键 trade-off
- **Strictness vs. Resilience**: Enforcing the `<think>` tag strictly means we might break simple tasks where the LLM immediately knows the answer and tool to use. However, for paper integration reasoning, strictness is required.
- **Static vs. Dynamic Write Sets**: Hardcoding the allowed write set is safer but inflexible. We propose defining a static project-level boundary first, with dynamic overrides passed via explicit tool schemas.

## 风险与假设
- **Assumption**: The runtime intercepts the raw text and can easily check for the presence of `<think>...</think>` before executing the tool.
- **Risk**: Streaming responses might trigger a tool call before the closing `</think>` tag is fully received, complicating the parser state machine.

## False Positive Success Paths (假阳性路径)
- **False Positive 1**: The LLM outputs a `<think>` block, but it's empty or just says "I will do the task". The system accepts it and runs the tool. This violates the "numbered plan" requirement, but appears successful externally.
- **False Positive 2**: The Allowed Write Set is defined in the prompt, the LLM obeys it, and the test passes. We claim the Write Set is enforced, but in reality, if the LLM hallucinated a path outside the set, the runtime would still execute it.

## 仍待验证的点
- Where exactly is the tool parser and executor located in the `nanobot` repository?
- How do we inject the Allowed Write Set into the tool execution layer without breaking existing non-reasoning agent flows?
