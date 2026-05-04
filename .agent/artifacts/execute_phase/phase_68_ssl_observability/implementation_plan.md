# Implementation Plan

**Job ID**: `phase_68_ssl_observability`

**Goal**: Implement the SSL (Scheduling-Structural-Logical) representation as an Observability and Context Optimization layer. Add an LLM normalizer during index-time skill registration, store the 3-layer JSON graph in the Knowledge Graph (`skill_ssl`), and refactor `ContextBuilder` to inject ONLY the `Scheduling` layer (capped at 1000 chars) instead of the raw `SKILL.md`.

**Source Context**: 
- `harness_lite` candidate (`.agent/artifacts/harness_lite/lite_20260504_ssl_representation/candidate.md`)

## Blast Radius Analysis
- **Core Components**: `nanobot/agent/skills.py` (loader caching and hashing), `nanobot/agent/context.py` (prompt injection).
- **Security Boundary**: ZERO impact. The AST Sandbox (`verification.py`) is untouched and continues to act as the sole source of truth for authorization. SSL is purely for context and observability.

## Zone Declaration
- **ZONE A** (Affects `context.py` and `skills.py`).
- Target Pytest command: `pytest tests/test_context_knowledge.py tests/test_phase22a_skills.py tests/test_phase68_paper_integration.py -W ignore -v`

## Implementation Strategy
1. **Normalizer**: Add a utility `nanobot/agent/ssl_normalizer.py` that takes `SKILL.md` text and calls the LLM to output a JSON dictionary containing `"Scheduling"`, `"Structural"`, and `"Logical"`. Provide a fail-closed fallback if parsing fails.
2. **Lifecycle & Hashing**: Update `SkillsLoader` to hook into skill registration. It will compute a composite hash of all `.py` and `.md` files in the skill directory. If the hash has changed, it calls the normalizer and stores a `skill_ssl` entity in the Knowledge Graph.
3. **Context Optimization**: Refactor `SkillsLoader.load_skills_for_context()`. When loading a skill for prompt injection, query the KG for `skill_ssl`. If found, inject ONLY the `Scheduling` dictionary (serialized, max 1000 chars). If not found, fall back to a truncated version of `SKILL.md`.
4. **KG Schema Durability**: Update `KnowledgeGraph.rebuild_entity_index()` in `nanobot/agent/knowledge_graph.py` so that standalone `skill_ssl` entities are preserved during reindexing without backing triples. You MUST ensure that the complete custom payload (including `hash` and `graph` properties) is fully copied over, rather than selectively stripping fields like `reasoning_template` does.

## Contract / Data Structures / Function Signatures
- `SkillNormalizer.normalize(skill_name, skill_text) -> dict | None`
- `SkillsLoader._compute_skill_hash(skill_name) -> str`
- KG Entity: `type: "skill_ssl"`, `name: "{skill_name}_ssl"`, `properties: { "hash": "...", "graph": { "Scheduling": {...}, "Structural": {...}, "Logical": {...} } }`

## Behavior Contract Matrix
| 场景输入 | 预期行为/分级 | 隐藏运行时状态 | 自动验证方式 | 人工验收信号 |
| --- | --- | --- | --- | --- |
| Load new valid skill | Normalizer generates 3-layer JSON, stored in KG. Context gets `<skill_ssl>` | KG index files, LLM provider availability | `pytest` checking mock KG insertion | Log `L0: Normalizing SKILL.md to SSL graph...` |
| Load malicious skill | Normalizer fails or creates graph; AST Sandbox still blocks at runtime | `validator.py` AST cache | `test_adversarial` verifying block | `verification.py` logs `deny` regardless of SSL |
| Change `validator.py` | Composite hash changes, SSL graph rebuilt | `SkillsLoader` cache hash | `pytest` verifying hash trigger | Log `L0: Rebuilding SSL graph due to hash change` |

## Hermeticity / Hidden Runtime States Checklist
- [x] **LLM Provider Dependency**: Normalization requires a live LLM. Will use a mock provider or standard dummy response in `pytest`.
- [x] **Knowledge Graph Storage**: `memory/graph.json` will persist state. Red tests must use isolated tmp directory.

## Runtime Artifact Parity Checklist
- **`skill_ssl` Entity in KG**: 
  - *Location*: Specifically inside `memory/graph.json` under the `entities` mapping.
  - *Fallback*: If missing or failed to parse, fallback to raw `SKILL.md` injection.

## Proof Signals / Observable Success Criteria
- **Log**: `[SkillsLoader] Injected SSL Scheduling for skill '{name}'`
- **Log**: `[SkillsLoader] Computed new composite hash for skill '{name}', triggering SSL rebuild`
- **File**: `memory/graph.json` contains `skill_ssl` entity.

## Risk Notes
- If the normalizer fails continuously due to strict schema prompt, skills will silently fall back to raw injection, defeating the token savings.

## Validation Plan
1. **Red Test**: Create a mock skill, verify the composite hash computation. Modify a Python file, verify hash changes.
2. **Red Test**: Verify `ContextBuilder` prioritizes the `Scheduling` layer and truncates it correctly.
