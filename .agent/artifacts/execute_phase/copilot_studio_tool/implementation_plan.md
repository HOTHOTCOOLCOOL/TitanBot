# Goal

Integrate Copilot Studio Agent (powered by Opus 4.6 in M365 environment) as an external consultant tool for the Nanobot system. This will enable the local Nanobot agent to offload heavy text reasoning, query enterprise data (SharePoint/M365), and get a "second opinion" without incurring extra API token costs, taking advantage of the M365 Copilot license.

## User Review Required

> [!WARNING]
> This integration will add a new remote dependency. We will store the `directline_secret` in `config.json` (similar to how we store API keys). Is this acceptable, or do you prefer environment variables (`.env`) for secrets?

## Open Questions

> [!IMPORTANT]
> 1. Which directory should the new tool be placed in? Currently, I see `nanobot/tools/write_artifact.py` and `nanobot/skills/builtin`. Should I create it as a standard Tool under `nanobot/tools/consult_copilot.py`?
> 2. Do you want to configure specific sub-scenarios (e.g., separate tools for `query_enterprise_knowledge` vs `peer_review`), or one generic `consult_copilot_studio` tool where the Nanobot just passes a prompt?

## Proposed Changes

### Configuration Updates

#### [MODIFY] config.sample.json
Add a new block under `tools` for the Copilot Studio configuration:
```json
  "tools": {
    "copilot_studio": {
      "secret": "your_direct_line_secret_here"
    }
  }
```

### Tool Implementation

#### [NEW] nanobot/tools/consult_copilot.py
Create the `ConsultCopilotTool` extending `BaseTool`. This tool will:
1. Load the Direct Line Secret from the configuration.
2. Provide a prompt parameter to the tool schema.
3. Manage the Direct Line conversation lifecycle (Token generation, Start Conversation, Send Message, Poll Response).
4. Return the plain text response from the Copilot Studio Agent to the Nanobot.
5. Handle timeouts and the `IntegratedAuthenticationNotSupportedInChannel` error gracefully.

### Documentation

#### [MODIFY] TOOLS.md
Document the newly added `consult_copilot_studio` tool, providing examples of when the local Nanobot should invoke it (e.g., large text synthesis, M365 knowledge queries, peer review).

## Verification Plan

### Automated Tests
- Create a unit test `tests/tools/test_consult_copilot.py` mocking the `httpx` responses to ensure the conversation state machine works correctly.

### Manual Verification
- Run a Nanobot interactive session.
- Ask the local Nanobot: "Use the Copilot Studio tool to ask: what is the company policy?"
- Verify that Nanobot invokes the tool, the tool hits the Direct Line API, and the Opus 4.6 response is successfully synthesized back to the user.
