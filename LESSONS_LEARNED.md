# Lessons Learned

Critical bugs and design mistakes encountered in production. Review this before making changes.

---

## 2026-03-19: Post-Model-Switch Production Bugs

### L1: `message` in `_CONTINUE_TOOLS` → Infinite Loop

**File**: `nanobot/agent/loop.py`

The `message` tool was added to `_CONTINUE_TOOLS` assuming it was an intermediate step.
In reality, `message()` is a **terminal action** — it sends the final response to the user.
After each `message()` call, the system injected a "continue executing" nudge, which caused the LLM to call `message()` again with the same summary, creating an infinite loop of 15+ identical messages.

**Rule**: Never add terminal/output tools to `_CONTINUE_TOOLS`. Only add tools
that produce intermediate data requiring further processing (like `outlook` search or `attachment_analyzer`).

---

### L2: Key Extractor Doesn't Handle Reasoning Models Without `<think>` Tags

**File**: `nanobot/agent/key_extractor.py`

When switching to a reasoning model (e.g., Nemotron), the model outputs chain-of-thought
as **plain text** without `<think>` tags. The `strip_think_tags()` utility does nothing
because there are no tags to strip. The extracted "key" becomes a 500+ character reasoning blob.

**Rule**: Always enforce output length limits on LLM extraction calls. Never trust the model
to produce the expected format — truncate and take the last line as the answer.

---

### L3: ChromaDB `peek()` API Incompatibility Silently Breaks Dimension Migration

**File**: `nanobot/agent/vector_store.py`

`collection.peek(limit=1, include=["embeddings"])` — the `include` kwarg is not supported
by all ChromaDB versions. The call failed silently (caught by try/except), leaving the
old 384-dim collection intact while the new model produces 1024-dim embeddings. Every
subsequent `search()` call threw "dimension mismatch" errors.

**Rule**: When using third-party library APIs, check compatibility across versions.
Use `get()` instead of `peek()` for ChromaDB dimension probing — it's the more stable API.

---

### L4: Outlook `send_email` Returns Non-Standard Error Strings

**File**: `nanobot/agent/tools/outlook.py`

`send_email` returned `"Failed to send email: ..."` on failure, but other tool actions
return `"Error: ..."`. The agent loop doesn't detect `"Failed"` as an error indicator,
so it treats the failure as success and retries in a loop.

**Rule**: All tool error returns MUST start with `"Error: "` for consistency. The agent
loop and `_FAIL_INDICATORS` rely on this prefix to detect workflow failures.

---

### L5: Language Instruction Says "中文" Without Specifying 简体/繁体

**File**: `nanobot/agent/context.py`

The system prompt told the LLM to "use Chinese" but didn't specify simplified vs traditional.
Different models have different defaults — some reasoning models trained on Traditional Chinese
data will switch to 繁体 mid-conversation.

**Rule**: Always specify `简体中文` explicitly in the language instruction. Include concrete
examples of simplified vs traditional characters (执行 vs 執行, 任务 vs 任務).

---

### L6: Tests Mock the Wrong API After Code Changes

**Files**: `tests/test_phase21e_embedding.py`, `tests/test_loop_cleanup.py`

When changing `peek()` to `get()` in production code, the corresponding test still mocked
`peek()`. Since MagicMock auto-creates missing methods, the test passed the mock setup but
the actual dimension logic was never exercised — the test passed vacuously.

**Rule**: When changing a function/method call in production code, immediately search tests
for mocks of the old call and update them. Use `grep` to find all references before committing.

---

## 2026-03-19 (PM): Recurring Bugs — Incomplete Fixes from Previous Sessions

> **⚠️ CRITICAL PATTERN: "Fixed but not actually fixed."** Four bugs documented below
> were all supposedly addressed in Phase 21F (earlier today), yet all four recurred in
> production. The previous fixes were **superficial** — they addressed the symptom but
> not the root cause. This wasted user time and tokens. Every fix MUST be verified
> end-to-end in the actual production code path, not just in isolation.

### L7: Dimension Migration Error Silently Caught → Collection Never Recreated

**File**: `nanobot/agent/vector_store.py`

L3 documented changing `peek()` → `get()` for the dimension probe, but the **error handler**
was the real problem. The `except Exception as dim_err` block only logged at DEBUG level and
skipped the migration entirely. When ChromaDB itself throws a dimension error during the
probe (e.g., `"Collection expecting embedding with dimension of 384, got 1024"`), the catch
block swallowed it, leaving the old collection intact. Every subsequent `search()` failed.

**Previous fix (L3)**: Changed `peek()` → `get()`. This was correct but incomplete.
**Actual fix (this session)**: The `except` handler now checks if the error message contains
`"dimension"` and forces collection recreation if so.

**Rule**: When writing error handlers for migration/upgrade logic, **always consider the case
where the probe itself fails for the exact reason you're trying to detect**. A migration
probe that fails silently is worse than no probe at all. Log at WARNING, not DEBUG. Test
with a mock that raises the exact production error.

---

### L8: `<think>` Tags Not Stripped in Agent Loop Response Path

**File**: `nanobot/agent/loop.py`

S6 (Phase 21C) created `think_strip.py` and replaced 7 call sites — but **missed the most
critical one**: the `_execute_with_llm()` response path in `loop.py`. The `final_content`
was checked against `_FAIL_INDICATORS` and sent to the user with raw `<think>` tags.
This caused two problems:
1. `<think>无法直接解析内容</think>成功发送` triggered false failure (无法 in `_FAIL_INDICATORS`)
2. Users received raw `<think>` reasoning text in their messages

**Previous fix (S6)**: Added `strip_think_tags()` to 7 locations. Missed `loop.py`.
**Actual fix (this session)**: `strip_think_tags()` applied to `final_content` in
`_execute_with_llm()` BEFORE the `_FAIL_INDICATORS` check.

**Rule**: When adding a utility function to "all call sites", use `grep` to verify
**every** place the data flows through, not just the obvious ones. The agent loop
response path is the MOST CRITICAL path — it must be checked first. Create a checklist
of all locations where raw LLM output is consumed and verify each one.

---

### L9: Outlook COM `mail.To` Doesn't Resolve External Addresses

**File**: `nanobot/agent/tools/outlook.py`

L4 documented standardizing error prefixes to `"Error: "`, and H4 added recipient validation
and explicit `CoInitialize()`. But the **actual COM API bug** was never addressed: setting
`mail.To = "external@hotmail.com"` and calling `mail.Send()` fails with `"Outlook does not
recognize one or more names"` because Exchange tries to resolve the recipient against the
Global Address List (GAL). External addresses not in the GAL are rejected.

**Previous fix (H4)**: Standardized error strings, added validation. Did NOT fix the COM API.
**Actual fix (this session)**: Use `mail.Recipients.Add(addr)` + `recipient.Resolve()` + set
`recipient.Type = 1` (olTo) instead of `mail.To`. This properly handles external SMTP addresses.

**Rule**: When a tool fails with a third-party API error, **research the actual API behavior**
instead of just cleaning up error messages. COM/Outlook documentation clearly states that
`Recipients.Add + Resolve` is the correct way to handle arbitrary email addresses. Error
message cosmetics are not a fix.

---

### L10: Key Extractor Reasoning Detection Too Weak

**File**: `nanobot/agent/key_extractor.py`

L2 documented "take last line + enforce 50/200 char limits" as the fix for verbose key
extraction. But two problems remained:
1. **200-char English limit was too generous** — reasoning text like `"The last user message
   appears: ..."` easily fits within 200 chars
2. **"Take last line" heuristic fails** when the reasoning is a single long line without
   newline breaks

**Previous fix (L2/H2)**: Last-line heuristic + length limits.
**Actual fix (this session)**: Added `_is_reasoning_text()` function that detects 15+ common
reasoning prefixes (e.g., "The user", "We need", "Let me", "Based on"), prompt echo patterns,
and multi-sentence long outputs. Reduced English limit from 200→100 chars. Falls back to
simple truncation of original user request when reasoning is detected.

**Rule**: Length limits alone do NOT prevent bad LLM output. Always add **content-based
validation** that detects common failure patterns. When a model outputs reasoning as plain
text (no `<think>` tags), the only reliable defense is pattern detection + aggressive fallback.

---

## Meta-Lesson: The "Fix Verification" Gap

The pattern across L7–L10 is clear: **each previous fix was technically correct in isolation
but incomplete in the production code path.** Root causes:

1. **Isolated testing** — fixes were verified with unit tests that mocked the exact expected
   behavior, but the mocks didn't simulate the actual production failure mode.
2. **Missing end-to-end validation** — no one replayed the actual production error scenario
   after applying the fix to confirm it was resolved.
3. **Surface-level fixes** — addressing error messages or adding validation without fixing
   the underlying API misuse (Outlook COM) or logic gap (silent error swallowing).

**Going forward, every bug fix MUST include:**
1. A unit test that reproduces the **exact production error** (not a simplified version)
2. Manual verification against the actual log line or error message that triggered it
3. `grep` verification that all related code paths are covered, not just the obvious one

---

### L11: ChromaDB Returns numpy ndarray — Truthiness Check Fails Silently

**File**: `nanobot/agent/vector_store.py`

**Third recurrence** of the dimension migration failure (L3 → L7 → L11).

Previous fixes correctly switched from `peek()` to `get()` and added fallback recreation.
But the dimension probe still failed because:

```python
# OLD — breaks with numpy arrays
if probe and probe.get("embeddings") and len(probe["embeddings"]) > 0:
```

`probe.get("embeddings")` returns a **numpy ndarray**. Python's `bool(ndarray)` raises
`ValueError: The truth value of an array with more than one element is ambiguous`.
This exception was caught by the generic `except`, but the error message didn't contain
the word "dimension", so it fell into the `else` branch and logged at DEBUG level —
**completely hiding the failure**. The old 384-dim collection survived, and every
`search()` call failed with "dimension mismatch".

**Fix**:
```python
# NEW — works with both numpy arrays and Python lists
embeddings = probe.get("embeddings") if probe else None
if embeddings is not None and len(embeddings) > 0:
```

**Rule**: Never use truthiness (`if x`) on values that might be numpy arrays.
Always use `is not None` + explicit `len()`. Also, never log silently at DEBUG
when a safety check fails — use WARNING so failures are visible in production logs.

---

## 2026-03-20: Phase 23A Security Hardening

### L12: Using a Nonexistent API Class (`httpcore.AsyncHTTPTransport`)

**File**: `nanobot/agent/tools/web.py`

When implementing the SSRF transport-level fix (R4), the initial implementation subclassed
`httpcore.AsyncHTTPTransport` — **this class does not exist**. The correct base class is
`httpx.AsyncBaseTransport`. The error was only caught at test collection time (`ModuleNotFoundError`),
which means the production code would also have crashed on first import.

**Rule**: Before using any third-party class or API, **verify it exists** by checking
`dir(module)` or the library documentation. Never assume an API exists based on naming
conventions alone. `httpcore` and `httpx` have similar naming but completely different
class hierarchies. When subclassing framework types, always test that the module **imports
correctly** before writing business logic.

---

### L13: Moving a Defense Layer Breaks Tests That Mock the Old Layer

**File**: `tests/test_ssrf_protection.py`

Phase 23A R4 moved SSRF checking from a pre-flight `_is_internal_address()` call to
a transport-level `_SSRFSafeTransport`. The old integration tests mocked
`_is_internal_address` to return `True` — but since the function was no longer called
in the request path, **the mock had no effect**. The tests appeared to pass setup but
failed assertion because the transport did its own DNS resolution.

This is the same pattern as L6 ("Tests mock the wrong API after code changes"), but at
a higher architectural level: when you **move a defense** from one layer to another,
every test that mocked the old layer becomes invalid.

**Rule**: When refactoring a security/validation check from one layer to another:
1. `grep` for all mocks of the old function (`@patch("...old_function"`)
2. Update every test to mock at the **new** layer
3. Verify the old tests still exercise the defense, not just pass vacuously

---

### Meta-Lesson: Always Update LESSONS_LEARNED.md Proactively

This document was NOT updated at the end of Phase 23A until the user reminded.
Despite L12 and L13 being genuine mistakes that consumed debugging time,
they were not recorded automatically.

**Rule**: After every Phase or significant code change, **ALWAYS** update this file
before reporting completion. This is not optional. Treat it as part of the definition
of "done" — the same as running tests. The user should **never** have to remind about
updating Lessons Learned.

**Checklist before reporting a Phase complete:**
1. ✅ All tests pass
2. ✅ `EVOLUTION.md` updated
3. ✅ `LESSONS_LEARNED.md` updated ← **THIS ONE**
4. ✅ `PROJECT_STATUS.md` updated (if applicable)

---

## 2026-03-20: Production Bug Trilogy (Third Round)

### L14: Outlook COM Email — `PropertyAccessor` Is Required for External SMTP (3rd Fix)

**File**: `nanobot/agent/tools/outlook.py`

L4 standardized error strings. L9 switched from `mail.To` to `Recipients.Add` + `Resolve()`. **Both failed.** `Resolve()` returns `False` for external addresses, and `Send()` still throws "Outlook does not recognize one or more names" because Exchange GAL rejection persists.

**Fix**: Set `PR_SMTP_ADDRESS` (`0x39FE001E`) via `PropertyAccessor.SetProperty()` to force SMTP address type, then `ResolveAll()`. If `Send()` still fails → fallback to fresh mail item with `mail.To` direct assignment.

**Rule**: COM email to external addresses needs **MAPI property-level** forcing, not just API-level resolution. Always have a fallback chain.

---

### L15: Cron Cross-Day Guard — Don't Catch Up Yesterday's Jobs

**File**: `nanobot/cron/service.py`

Previous fix (L18) removed `_run_missed_jobs` and relied on heartbeat timer for catch-up. But this caught up ALL stale jobs including yesterday's — unacceptable when the gateway restarts the next day.

**Fix**: Added `_skip_stale_cross_day_jobs()` in `start()` — jobs whose `next_run_at_ms` predates today's midnight are skipped (status = "skipped"), next run recomputed. Same-day missed jobs still catch up.

**Rule**: Catch-up logic must differentiate same-day from cross-day. Always check calendar day boundaries.

---

### L16: Agent Loop Missing Duplicate Tool Call Detection → Infinite Loops

**File**: `nanobot/agent/loop.py`, `nanobot/agent/tools/shell.py`

The agent loop had NO detection for the LLM calling the same tool with the same arguments repeatedly. Combined with overly aggressive `deny_patterns` in `shell.py` (blocking `python -c` and `node -e`), the LLM would:
1. Try to generate PPT using `python -c` → blocked by shell guard
2. Try `node -e` → blocked by shell guard  
3. Fall into `list_dir` of the same directory 10+ times → no detection

**Fix**: 
1. Unblocked `python -c` and `node -e` (legitimate scripting, not dangerous)
2. Added **duplicate tool call detection** — tracks last 3 call signatures, breaks if all identical

**Rule**: Security deny_patterns must NOT block legitimate productive tool usage. Agent loops MUST have stall detection beyond just `max_iterations`.

---

## 2026-03-21: Phase 23B/23C — Architecture Polish

### L17: `os.environ.setdefault` Silently Ignores Override Attempts

**File**: `nanobot/providers/litellm_provider.py`

When switching VLM providers dynamically (e.g., from Claude to Gemini Vision), `setdefault` does NOT override an existing environment variable. If the main provider already set `GOOGLE_API_KEY`, a subsequent VLM route to a different Google model with a different API key will silently use the wrong key.

**Fix**: Use `os.environ[key] = value` for dynamic routes that intentionally override. Keep `setdefault` only for initial setup where user-set env vars should be respected.

**Rule**: `setdefault` is for "use this if nothing else is set." Direct assignment is for "I need this specific value now." Know the difference and choose deliberately.

---

### L18: Mocking `Path.stat()` for Size Checks — Use Threshold Manipulation Instead

**File**: `tests/test_phase23c_polish.py`

Initial test tried to mock `Path.stat` to return a fake `st_size` of 25 MB. This failed because `Path.stat()` is a built-in method that returns an `os.stat_result` (a C struct) — `MagicMock(wraps=...)` on it produces objects that don't behave like the real struct for attribute access.

**Fix**: Instead of mocking the filesystem, temporarily lower the size threshold (`_MAX_IMAGE_BYTES = 50`) so a real 104-byte test file exceeds it. This tests the actual code path without fragile mocks.

**Rule**: When testing size/threshold checks, prefer adjusting the threshold over mocking the filesystem. It's more robust and exercises real I/O.

