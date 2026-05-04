# Job 20260426: Copilot Studio External Consultant Tool

## Summary

This job introduced `consult_copilot_studio` as a built-in Nanobot tool so the local agent can delegate heavy text reasoning or enterprise knowledge lookups to a Copilot Studio agent over Direct Line.

## What Landed

- Added `CopilotStudioConfig` to `nanobot/config/schema.py` and wired it into `ToolsConfig` as `tools.copilot_studio`.
- Updated `config.sample.json` with the `tools.copilotStudio` example block (`enabled`, `secret`), preserving camelCase input compatibility for user-facing config files.
- Added `nanobot/agent/tools/consult_copilot.py` with `ConsultCopilotTool`, built on `Tool`.
- Registered the tool in `nanobot/agent/tool_setup.py` as a built-in default tool instead of a plugin.
- Expanded `tests/test_config_schema.py` to cover defaults plus camelCase and snake_case parsing.
- Replaced the placeholder tool test with `tests/unit/tools/test_consult_copilot.py`, covering missing secret, success path, timeout, and surfaced HTTP failures.
- Appended `TOOLS.md` with tool usage documentation.

## Runtime Contract

- Tool name: `consult_copilot_studio`
- Config path at runtime: `tools.copilot_studio`
- Required secret source: Direct Line secret configured in the main Nanobot config
- Failure contract: all handled failures return strings prefixed with `Error: `

## Direct Line Flow

`ConsultCopilotTool` currently performs the following sequence:

1. Generate a Direct Line token.
2. Create a conversation.
3. Send the `startConversation` event.
4. Send the user prompt as a message activity.
5. Poll conversation activities until a non-user bot text reply is found or timeout is reached.

The current aggregation rule returns the last non-user bot text activity.

## Automated Verification

The implementation was validated with:

```text
python -m pytest tests/unit/tools/test_consult_copilot.py tests/test_config_schema.py tests/test_tool_validation.py tests/test_tool_concurrency.py tests/test_plugin_loader.py -W ignore -v
```

Result: pass

## Manual Validation Still Needed

- Run one end-to-end request against a real Copilot Studio Direct Line secret.
- Confirm whether returning only the last bot text activity matches the tenant's actual reply shape.
- Confirm that disabled or invalid-secret cases surface as `Error: ...` without destabilizing the agent loop.

## Follow-up Risks

- Multi-part Copilot replies may need concatenation instead of last-message selection.
- Tenant-specific Direct Line policy or auth behavior can still differ from the mocked test environment.
