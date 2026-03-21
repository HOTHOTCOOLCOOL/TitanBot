# Lessons from Building Nanobot: A Personal AI Agent's Architecture Journey

> How we evolved a simple chatbot into an enterprise-grade autonomous AI assistant  
> — Inspired by @trq212's "Lessons from Building Claude Code"  
> Last updated: 2026-03-20

---

## Introduction

When we started Nanobot, it was a ~10-file chatbot with 3 tools and 2 channels. Today it's a 95-file, 14-package system with 18 tools, 9 channels, 763 tests, and a 7-layer memory architecture. Along the way, we discovered several design principles that we believe are broadly applicable to anyone building AI agent systems.

This article captures those lessons, especially in conversation with Anthropic's Thariq Shihipar's excellent ["Lessons from Building Claude Code"](https://x.com/trq212/article/2033949937936085378). We share both what worked and where we see room for growth.

---

## Lesson 1: The Simple Main Loop Wins

**The single most important architecture decision: resist complexity.**

Our agent core is a single `loop.py` — one async function that runs the LLM, dispatches tools, and iterates. No DAG orchestrator. No multi-agent framework. No state machine library. Just a loop.

```
User Input → LLM → Tool Calls → Results → LLM → ... → Final Response
```

This mirrors what Anthropic found with Claude Code: "a simple main loop with tool calls" outperforms complex DAG-based architectures. 

**Why it works:**

- LLMs are already powerful planners — adding an orchestration layer on top fights their natural strengths
- Debugging is trivial: every turn is a clean function call
- Error recovery is simple: retry the loop, break after N failures (our circuit breaker triggers after 3 consecutive all-exception turns)

**Our metric:** We started with a 916-line monolithic `loop.py`. Through modularization we stripped it to ~670 lines, extracting 12 specialized modules (state handler, context builder, command processor, etc.) while keeping the core loop dead simple.

> **Takeaway:** If you're building an agent, start with the dumbest possible loop. You'll be shocked how far it takes you.

---

## Lesson 2: Knowledge Should Evolve Into Skills Automatically

This is perhaps where Nanobot goes beyond what most agent frameworks offer.

**The Auto-Sublimation Pipeline:**

1. User asks something → agent figures out how → records steps as a "knowledge entry" (JSON)
2. Next time a similar request comes in → knowledge is matched via 5-layer hybrid retrieval → steps are injected as few-shot examples  
3. After a knowledge entry succeeds ≥3 times → agent automatically proposes upgrading it to a permanent Python Skill

```
Observation → Knowledge → Validated Pattern → Permanent Skill
```

**The 5-Layer Retrieval Pyramid:**

| Layer | Method | When |
|-------|--------|------|
| L1 | Exact key match | Always |
| L2 | Substring match (threshold 0.65, min 4 chars) | Always |
| L3 | jieba segmentation + Jaccard | Always |
| L4 | BM25 sparse retrieval | >100 entries |
| L5 | Dense vector similarity (BAAI/bge-m3, 1024-dim) | >100 entries |

**The Knowledge Judge** makes add/merge/discard decisions automatically. If a new entry is semantically similar to an existing one, it merges them. If it conflicts, it replaces. If it's low-quality, it discards.

> **Takeaway:** Don't just build a skill system — build a *pipeline* that automatically promotes proven patterns from ad-hoc knowledge into permanent skills. Let the agent learn from its own successes.

---

## Lesson 3: Skills Are Folders, Not Files

We fully agree with @trq212's insight: **Skills are folders, not Markdown files.**

Our skill structure:

```
outlook-email-analysis/
├── SKILL.md              ← YAML frontmatter + instructions
├── scripts/              ← Deterministic code
├── references/           ← Domain docs loaded on-demand
└── assets/               ← Templates, configs
```

**Progressive Disclosure** is critical for context window efficiency:

1. **Metadata** (name + description) — always in context (~100 words)
2. **SKILL.md body** — loaded only when skill triggers (<5k words)  
3. **Bundled resources** — loaded only when the agent needs them

This matches Anthropic's three-level loading system exactly. The key insight is that `description` is the **only trigger mechanism** — the body is never seen until after triggering. So all "when to use" information must be in the description.

> **Takeaway:** Treat your skill's `description` field as the advertisement. It's the only thing the model sees when deciding whether to use the skill. Optimize it for AI parsing, not human readability.

---

## Lesson 4: Memory Is Not One Thing — It's Seven

The most under-engineered part of most AI agents is memory. We spent 3 phases (20A-20H) building a comprehensive memory architecture inspired by *"Survey on AI Memory"* (Ting Bai et al., 2026).

**Our 7-Layer Memory Stack:**

| Layer | Name | Purpose | Implementation |
|-------|------|---------|----------------|
| L1 | Core Preferences | "Who is the user?" | LLM-distilled `preferences.json` |
| L2 | Semantic Store | Long-term knowledge | ChromaDB + bge-m3 with time-decay scoring |
| L3 | Daily Logs | Temporal awareness | `YYYY-MM-DD.md` structured logs |
| L4 | Evicted Context | Virtual memory paging | MemGPT-inspired buffer for overflow |
| L5 | Slow-Path Consolidation | Deep pattern extraction | CLS-style batch LLM consolidation |
| L6 | Metacognitive Reflection | Self-awareness | "What worked? What didn't?" |
| L7 | Entity-Relation Graph | Structured knowledge | Lightweight triple store |

Each layer has different read/write patterns, retention policies, and injection budgets. The system prompt injection has a hard 8000-char cap across all memory sources to prevent context window bloat.

**Memory Lifecycle:**

```
Conversation → Immediate Store (L2) → Auto-Consolidation (every 20 msgs)
                                     → Deep Consolidation (periodic L5)
                                     → Reflection (periodic L6)
                                     → Entity Extraction (L7)
```

**Capacity management** is automatic: ReflectionStore caps at 100 entries, KnowledgeGraph at 500 triples, both with LRU pruning.

> **Takeaway:** Don't treat memory as a single vector store. Different types of information (preferences, facts, experiences, reflections) need different storage strategies, retention policies, and retrieval methods.

---

## Lesson 5: Security Is Not Optional — Even for Personal Assistants

"It's just a personal bot" is the most dangerous phrase in AI engineering. When your agent has shell access, email capabilities, and file system tools, the attack surface is enormous.

**Our 32-item security audit covered:**

- **Shell hardening**: 14 deny patterns blocking path traversal (`cd ..`), encoded attacks (`%2e`), interpreter bypasses (`python -c`), network exfiltration, reverse shells
- **Path traversal protection**: `is_relative_to()` checks on all file operations
- **SSRF blocking**: RFC1918/loopback/link-local/metadata IP checks on all web fetches
- **Auth everywhere**: Bearer Token on all Dashboard HTTP + WebSocket endpoints
- **Rate limiting**: 30 msg/min per WebSocket connection, 10KB message cap
- **Atomic writes**: All JSON persistence uses temp-file + `os.replace()`
- **Error sanitization**: Generic user messages, full tracebacks only in logs

**The scariest bug we found:** Our shell tool could be bypassed via `python -c "import os; os.system('rm -rf /')"`. The deny pattern for `rm -rf` didn't catch interpreter-mediated execution.

> **Takeaway:** Audit your agent's tool capabilities as if a hostile user will interact with them. Because eventually, one will — even if it's an LLM hallucination that constructs a dangerous command.

---

## Lesson 6: Channels Are Just Adapters — But Adapters Are Hard

Nanobot supports 9 channels (CLI, MoChat, Telegram, Discord, Slack, Email, Feishu, DingTalk, WhatsApp). Each one has its own authentication flow, message format, rate limits, and media handling quirks.

**What worked: Data-Driven Registration**

We replaced 9 repetitive if/try/except blocks with a single `_CHANNEL_REGISTRY` list:

```python
_CHANNEL_REGISTRY = [
    ("telegram", "channels.telegram", "TelegramChannel", cfg.telegram.enabled),
    ("discord",  "channels.discord",  "DiscordChannel",  cfg.discord.enabled),
    # ... one line per channel
]
```

One loop iterates the list, imports the module, instantiates the class, and registers it. Adding a new channel = one line.

**The Master Identity System** maps different identities across channels to a single person:

```json
{
  "master_identities": {
    "david": {
      "email": "david@company.com",
      "telegram": "david_tg",
      "mochat": "david_wx"
    }
  }
}
```

This enables cross-channel context: "What did David ask me on Telegram yesterday?" works even if you're talking via email.

> **Takeaway:** Design your channel layer as a thin adapter with a unified interface. The hard part isn't adding channels — it's maintaining identity and context across them.

---

## Lesson 7: Tools Should Be Designed for Models, Not Humans

This echoes @trq212's companion article "Seeing like an Agent": **tools should be designed around how models think, not how humans would design APIs.**

**Our examples:**

| Human-Centric Design | Model-Centric Design |
|---|---|
| Multi-step wizard for email search | Single `find_emails` call with structured JSON criteria |
| Interactive prompts ("What folder?") | All parameters in one tool call, with smart defaults |
| Rich HTML error messages | Structured error prefix `"Error: "` for reliable parsing |
| Separate tools for each email action | Unified `outlook` tool with `action` parameter |

**Tool output discipline:**
- All tool outputs capped at 50,000 chars with `[TRUNCATED]` marker
- Error messages use consistent `"Error: "` prefix so models can reliably detect failures
- Success messages are structured JSON when possible

**The "Action Space Explosion" problem:** We found that having too many tools causes models to stall. Model capability evolves over time — a tool that works at one capability level may become counterproductive at the next. We periodically audit whether tools can be consolidated.

> **Takeaway:** Regularly revisit your tool APIs. Ask: "Would a model make better decisions with fewer, more powerful tools or more, specialized ones?" The answer changes as models improve.

---

## Lesson 8: The Skill-Creator Skill — Meta-Skills That Build Skills

One of our most powerful skills is `skill-creator` — a meta-skill that teaches the agent how to create new skills. It embodies all our lessons about skill design:

- **Concise is key**: "The context window is a public good"
- **Degrees of freedom**: High freedom for creative tasks, low freedom for fragile operations
- **Progressive disclosure**: Keep SKILL.md lean, move details to `references/`
- **Test by doing**: Scripts must be tested by actually running them

The creation flow:
1. Understand the skill with concrete examples (talk to the user)
2. Plan reusable contents (scripts, references, assets)
3. Initialize the skill directory structure
4. Write SKILL.md + implement resources
5. Package and distribute
6. Iterate based on real usage

This means our agent can **bootstrap new capabilities** by creating skills for itself, validated through actual use and automatically promoted from the knowledge pipeline.

> **Takeaway:** Build a meta-skill that teaches your agent how to extend itself. The compounding effect is enormous.

---

## Lesson 9: Production Bugs Are Teachers — Document Everything

We maintain a `LESSONS_LEARNED.md` document that captures every production incident. Here are our most instructive failures:

**L7: The Triple-Recurring Dimension Bug**  
Our embedding model upgrade (384→1024 dimensions) required ChromaDB collection migration. The migration code failed silently **three times** because:
1. First fix: Used `peek()` API which didn't support `include=` parameter
2. Second fix: Used `get()` but error handler silently skipped dimension mismatches
3. Third fix: `peek().get("embeddings")` returned numpy ndarray — `bool(ndarray)` raises ValueError

**Root cause:** Each fix only addressed the symptom, not the underlying assumption. The lesson: **always test the migration path end-to-end**, not just the happy path.

**L9: The Outlook Recipients Mystery**  
`mail.To = "external@gmail.com"` works for Exchange GAL addresses but **silently fails** for external SMTP addresses. The correct COM API is `mail.Recipients.Add(addr); recipient.Resolve()`. This is undocumented in most Python-COM tutorials.

**Root cause:** Internal-only testing. External email addresses use a fundamentally different resolution path.

> **Takeaway:** Every production bug should become a documented lesson. Pattern-match across lessons periodically — recurring themes reveal systematic weaknesses in your architecture.

---

## Lesson 10: Proactive Execution Over Passive Wait

A common failure mode in AI agents: the model generates a "thought" or "analysis" but never actually *does* anything. We call this the "fake completion" problem.

**Our proactive execution constraints:**

1. **`_CONTINUE_TOOLS` set**: Tools like `find_emails`, `get_all_attachments` are marked as "intermediate" — after calling them, the loop automatically continues instead of terminating
2. **`_MAX_MESSAGE_CALLS` flood guard**: Prevents the model from sending the same response 3+ times
3. **Circuit breaker**: Breaks after 3 consecutive all-exception turns
4. **Mandatory SKILL.md reading**: Before executing a new skill, the agent must read the SKILL.md first — prevents hallucinated scripts

The `outlook-email-analysis` skill explicitly states: "**不要**在每一步后追问用户'需要继续吗'" (Don't ask the user "continue?" after each step). This single instruction dramatically improved user experience.

> **Takeaway:** Design your agent to be biased toward action. Users hire agents to *do things*, not to ask permission at every step. Build guardrails (circuit breakers, deny lists) instead of gates (confirmation dialogs).

---

## Where We're Going: Phase 22

Inspired by @trq212's article, we're incorporating several improvements:

1. **Skill-Level Memory** — Each skill gets its own persistent memory directory
2. **AI-First Descriptions** — Rewriting all skill descriptions as model-optimized trigger specifications
3. **Skill Taxonomy** — Formal categorization system for discovery and management
4. **Configurable Skills** — JSON-driven skill behavior parameterization
5. **Dynamic Hooks** — Pre/post-execute hooks for skills
6. **Tool Design Audit** — Systematic review of all tool I/O for model-friendliness
7. **Skill Registry** — Version management and usage tracking

---

## Summary: Our Design Principles

1. **Simple loop, smart tools** — Don't fight the model's natural planning ability
2. **Let knowledge evolve** — Observation → Knowledge → Validated Pattern → Skill
3. **Skills are folders** — Progressive disclosure saves your context budget
4. **Memory is layered** — Different information types need different strategies
5. **Security first** — Treat every tool as an attack surface
6. **Channels are adapters** — Thin adapters, unified identity, cross-channel context
7. **Design for models** — Tool APIs should serve how models think
8. **Meta-skills compound** — Teach your agent to extend itself
9. **Bugs are lessons** — Document every failure, pattern-match across incidents
10. **Bias toward action** — Guardrails, not gates

---

*This article is part of the Nanobot project — an open-source enterprise-grade personal AI assistant. We believe the AI agent community grows stronger when we share our hard-won lessons. We hope these insights help you build better agents.*

*References:*
- *@trq212: ["Lessons from Building Claude Code: How We Use Skills"](https://x.com/trq212/article/2033949937936085378)*
- *@trq212: "Lessons from Building Claude Code: Seeing like an Agent"*
- *Ting Bai et al.: "Survey on AI Memory: Theories, Taxonomies, Evaluations, and Emerging Trends" (2026)*
- *AutoSkill (ECNU, 2603.01145v2), XSKILL (HKUST, 2603.12056v1)*
