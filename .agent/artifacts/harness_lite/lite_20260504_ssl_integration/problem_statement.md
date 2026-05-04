# Problem Statement

- **Job ID**: lite_20260504_ssl_integration
- **Goal**: Evaluate and design the integration of the SSL Scheduling Layer (P1) into Nanobot's KnowledgeMapTool metadata, and explore an automated LLM-based normalizer for README parsing (P2), as recommended in the `2604.24026v3` paper analysis report.
- **Source Context**: `.agent/artifacts/paper_analysis_report.md` (P1 and P2 recommendations), `nanobot/agent/tools/knowledge_map.py` (Phase 67 KnowledgeMapTool).
- **In Scope**:
  - Defining the JSON schema for the Scheduling Layer (Goal, Input/Output, Triggers) as tool metadata.
  - Designing how this metadata attaches to existing Knowledge Graph (KG) entities or `TOOLS.md`.
  - Designing a lightweight script/tool to auto-generate these capability cards (Scheduling Layer) from raw documentation.
- **Out of Scope**:
  - Implementing the SSL Structural Layer (Execution flow) or Logical Layer (Risk Assessment), as Nanobot already handles these via Phase 56/64 security sandboxing.
  - Making changes to existing Phase 64 Zone A/B/C isolation logic.
- **Expected Output**:
  - A technical design (Draft V1) detailing the schema for the Capability Card.
  - An update plan for `KnowledgeMapTool` to consume and return this data.
  - A design for the automated extraction pipeline.
