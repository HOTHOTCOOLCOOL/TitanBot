---
name: memory
description: >
  Two-layer memory system (MEMORY.md long-term facts + HISTORY.md event log) with
  grep-based recall. Use when user asks to: remember/store a fact, search past events,
  recall what happened on a date, or update user preferences and project context.
  Triggers: "记住", "remember", "别忘了", "don't forget", "what happened on",
  "search history", "update preferences". Always loaded — core memory infrastructure.
category: library_api
always: true
---

# Memory

## Structure

- `memory/MEMORY.md` — Long-term facts (preferences, project context, relationships). Always loaded into your context.
- `memory/HISTORY.md` — Append-only event log. NOT loaded into context. Search it with grep.

## Search Past Events

```bash
grep -i "keyword" memory/HISTORY.md
```

Use the `exec` tool to run grep. Combine patterns: `grep -iE "meeting|deadline" memory/HISTORY.md`

## When to Update MEMORY.md

Write important facts immediately using `edit_file` or `write_file`:
- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Auto-consolidation

Old conversations are automatically summarized and appended to HISTORY.md when the session grows large. Long-term facts are extracted to MEMORY.md. You don't need to manage this.
