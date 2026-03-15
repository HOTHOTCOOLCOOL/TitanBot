---
name: "calc-rpa-demo"
description: "A demonstration skill that uses text-based UI matching and RPA to automatically operate the Windows Calculator."
available: "true"
tags: ["rpa", "automation", "demo"]
---

# Calculator RPA Demo Skill

This skill demonstrates Nanobot's **Text-Based UI Automation** framework.
It uses `screen_capture` with `annotate_ui=True` to detect UI elements by name, then clicks them directly using `rpa(action='click', ui_name='...')` — no VLM screenshot analysis required.

## Prerequisites

1.  An LLM must be active (text-only is sufficient; VLM is NOT required).
2.  Windows Calculator (`calc.exe`) must be visible on the screen.

## How it works (The Name-Match Approach)

When a user triggers this skill by saying "Run the calculator RPA demo", execute the following steps:

1.  **Preparation**:
    - Use the `exec` tool to run `calc.exe` to open the Windows Calculator.
    - Wait 2 seconds for it to open.
2.  **Perception**:
    - Call `screen_capture` with `{"annotate_ui": true}`.
    - You will receive a **text list** of all interactive UI elements grouped by type (Buttons, Edits, etc.), each with its name.
3.  **Action (using ui_name — RECOMMENDED)**:
    - Your goal is to click `5`, `+`, `8`, `=`.
    - **Use `ui_name` to click each element directly by its label:**
      - `rpa({"action": "click", "ui_name": "Five"})` 
      - `rpa({"action": "click", "ui_name": "Plus"})` 
      - `rpa({"action": "click", "ui_name": "Eight"})` 
      - `rpa({"action": "click", "ui_name": "Equals"})` 
    - No need to look at the screenshot image — the text element list is enough!
4.  **Verification**:
    - Call `screen_capture` again to verify the calculator display shows `13`.
    - Report the final success to the user!

## Execution Guidelines for the LLM

- **Prefer `ui_name` over `ui_index`.** The `ui_name` parameter matches elements by their label text, which is faster and more reliable.
- **Only use `ui_index` as a fallback** if `ui_name` fails to match (e.g., unnamed elements).
- **Do NOT use raw x/y coordinates.** The system will reject raw coordinates when anchors are available.
- **Handle Latency:** Use the `wait_after` parameter in the `rpa` tool if the UI needs time to transition.
- **Fail Gracefully:** If `ui_name` returns "not found", call `screen_capture` again to refresh the element list, or inform the user.
