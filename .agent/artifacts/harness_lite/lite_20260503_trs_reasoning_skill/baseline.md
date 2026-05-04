# Baseline

### Claim / Evidence / Status
- **Claim 1**: Reasoning LLMs (o1, DeepSeek-R1) and complex CoT prompts spend excessive output tokens on trial-and-error deliberation.
  - *Evidence*: TRS Paper [2604.21764v2] industry reports and Nanobot's observed token consumption on complex coding tasks.
  - *Status*: Accepted.
- **Claim 2**: Nanobot's current architecture can support skill reuse.
  - *Evidence*: `README.md` documents an existing `AutoSkill` pipeline, 5-layer Hybrid Retrieval, and a Knowledge Graph with MDER-DR.
  - *Status*: Accepted.
- **Claim 3**: Injecting known reasoning traces into the prompt reduces redundant model deliberation.
  - *Evidence*: TRS Paper empirical results showing accuracy gains and token cost reduction.
  - *Status*: Accepted as a premise for this design.

### Source of Truth Files
- `nanobot/agent/skills.py`
- `nanobot/agent/context.py`
- `nanobot/agent/memory.py`

### Unknowns
- How to extract `reasoning_skill`s from past execution traces without introducing a fully autonomous, unsupervised agent (which conflicts with Nanobot's rules).
- The optimal injection point: whether to append reasoning templates to the System Prompt, or pass them as a dynamic `GroupRAG` retrieval result.

### Questions the Critic Must Attack
1. Does the proposed `reasoning_skill` extraction mechanism bypass HITL and introduce security or hallucination risks?
2. Will injecting long reasoning templates break the prompt size limits enforced by the In-Flight Context Condensation (IFCC) system?
3. Is modifying the `context.py` prompt builder the safest architectural choice compared to using the existing `GroupRAG` pipeline?
