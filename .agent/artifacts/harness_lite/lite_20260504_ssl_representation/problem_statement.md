# Problem Statement

**Job ID**: `lite_20260504_ssl_representation`

**Goal**: Integrate the SSL (Scheduling-Structural-Logical) 3-layer JSON graph representation for Agent Skills into Nanobot's Knowledge Graph to enhance the Skill Dependency Framework and Pre-flight Skill Verifier (PSV) at index-time.

**Source Context**: 
- Paper Analysis Report (derived from arXiv 2604.24026v3)
- Nanobot `harness_lite` workflow

**In Scope**:
- Defining the SSL Knowledge Graph entity schema (`skill_ssl`).
- Designing an LLM-based `SkillNormalizer` to parse `SKILL.md` into this schema during skill registration.
- Defining how PSV and the ContextBuilder query these KG entities to enforce dependency boundaries and prompt budgets.

**Out of Scope**:
- Modifying the existing AST-level execution blocks (AST Sandbox remains the ultimate source of truth, SSL is an index-time enhancement).
- Retrofitting skills that do not have any instructional documentation or `SKILL.md`.

**Expected Output**:
A finalized ADR candidate outlining the schema, normalizer pipeline, and integration points with PSV and the Knowledge Graph.
