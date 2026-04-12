# Phase 49: In-Flight Context Condensation (IFCC)

The goal of this phase is to implement the IFCC protocol as defined in `ADR-49`. This protocol borrows from the MemPO paper by teaching the LLM to summarize key milestones within `<mem>` tags, preventing amnesia during long tasks by condensing large histories into lightweight milestone messages upon truncation.

## User Review Required

> [!IMPORTANT]
> The `milestone_summary` will be added to the memory structure. We will implement `tag_extractor.py` to strip out `<mem>` tags from the final user visibility, but embed the content inside the session history. Check if there are any specific UI concerns around displaying these milestones implicitly (or if they should remain invisible to users).
> We will also modify the `_trim_history()` behavior. Does this match your expectations for truncating history while keeping skeleton records?

## Proposed Changes

---

### Core Data Structures & Config

#### [MODIFY] `nanobot/config/schema.py`
- Add `ifcc_enabled: bool = True` to the `MemoryFeaturesConfig` class.

#### [MODIFY] `nanobot/session/models.py`
- Add `milestone_summary: str | None = None` to the `Message` class or typed dictionary.
- Ensure the field serialization and deserialization retains `milestone_summary`.

---

### Tag Extraction Engine

#### [NEW] `nanobot/agent/tag_extractor.py`
- Implement `extract_mem_content(text: str) -> tuple[str, str | None]`.
- Will use RegExp (`re.finditer`) to extract content inside `<mem>...</mem>` tags.
- For multiple occurrences, join the found tags with `" | "`.
- Apply a hard truncation to `500 chars` on the accumulated milestone summary.
- Safely remove the tag contents to produce the `clean_text`.
- If no tags are found, return `(text, None)`.

---

### Knowledge Integration & Flow

#### [MODIFY] `nanobot/agent/loop.py`
- In `_run_agent_loop(...)`, after `text = response.content`, intercept the output to parse `<mem>` tags.
- **Safety**: Only process outputs originating from `role='assistant'`.
- Pass the extracted `milestone_summary` to the `ContextBuilder.add_assistant_message()` call.
- Append a small prompt snippet (~45 tokens) to the `System Prompt` driving the LLM to use `<mem>` tags upon concluding intermediate steps. Note: Ensure this is skipped if `config.agents.memory_features.ifcc_enabled == False`.

#### [MODIFY] `nanobot/agent/context.py`
- Update `add_assistant_message` to take an optional `milestone_summary` argument and set it on the newly created `Message`.
- Crucial Change: Update `_trim_history(messages)`. For messages selected for eviction, instead of discarding, check `msg.get("milestone_summary")`.
- If `milestone_summary` exists, down-grade the message in place: set its content to `(上下文已压缩) {msg['milestone_summary']}` and drop any heavy attachments/tool payloads. Keep `role='assistant'`.

---

### Tests

#### [NEW] `tests/test_phase49_ifcc.py`
- Will include the 10 test cases as prescribed in ADR-49 (T1-T10).
- Coverage includes empty parsing, unclosed tags limit handling, multiple chunks, string truncation, and verifying the `_trim_history` down-grade mechanism.

## Verification Plan

### Automated Tests
- `pytest tests/test_phase49_ifcc.py -v` (Should pass all 10 new test cases).
- `pytest -v` (Full regression to ensure we haven't broken tool outputs or history management).

### Manual Verification
- Spawn a dummy subagent task designed to hit `max_iterations`, and force the token budget to max out. Check the raw `Session` JSON to verify that earlier chunks are successfully rewritten to "（上下文已压缩）...".
