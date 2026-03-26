---
description: How to read, analyze, and compare PDF papers against the Nanobot project architecture
---

# Reading & Analyzing PDF Papers

When the user provides one or more paths to PDF files, follow this complete workflow:

## Phase 1: Extract & Read

1. **Verify paths**: Ensure all provided PDF paths are absolute.
// turbo
2. **Extract text** for each PDF (first 5 pages for overview):
   `python .agent/scripts/read_pdf.py "<path_to_pdf>" --limit 5`
3. **Read further if needed**: For specific sections deeper in the paper:
   `python .agent/scripts/read_pdf.py "<path_to_pdf>" --page <page_number>`
4. **Identify each paper**: Note the title, core concept, and key contributions.

## Phase 2: Summarize

5. **Create a summary** of each paper's core ideas, focusing on:
   - What problem does it solve?
   - What is the key technique/architecture?
   - What are the main results?

## Phase 3: Compare with Nanobot

6. **Review Nanobot's current architecture** by reading:
   - `EVOLUTION.md` — full feature evolution and architecture overview
   - `PROJECT_STATUS.md` — current capabilities, phase history, and roadmap
7. **For each paper**, create a comparison table with columns:
   - 维度 (Dimension)
   - 论文方案 (Paper's approach)
   - Nanobot 现状 (Nanobot's current state)
   - 判定 (Verdict: 🟢 Nanobot already has / 🟡 Similar / 🔴 Nanobot lacks)
8. **Give opinions** for each paper, categorized as:
   - ⭐ **值得借鉴** (Worth borrowing) — with specific implementation ideas and estimated effort
   - 🟢 **Nanobot 已经更好** (Nanobot is already better) — explain why
   - 🔴 **不值得加入** (Not worth adding) — explain why (e.g., conflicts with single-agent philosophy, ROI too low, requires RL training infrastructure)

## Phase 4: Prioritized Report

9. **Create a prioritized recommendation table** sorted by ROI, with columns:
   - Priority (P0–Pn)
   - Borrowable item
   - Source paper
   - Estimated effort
   - Rationale
10. **Highlight areas where Nanobot already leads** — this validates existing architecture decisions.
11. **List items explicitly NOT recommended** with reasons.

## Output

- Write the full report to the artifact directory as `paper_analysis_report.md`.
- Clean up any temporary extracted text files after completion.
- Present the top 3 recommendations to the user for discussion.
