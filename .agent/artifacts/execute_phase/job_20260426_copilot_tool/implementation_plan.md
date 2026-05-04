# Goal

Integrate Copilot Studio Agent (powered by Opus 4.6 in M365 environment) as an external consultant tool for the Nanobot system. This will enable the local Nanobot agent to offload heavy text reasoning, query enterprise data (SharePoint/M365), and get a "second opinion" without incurring extra API token costs.

## Job ID
job_20260426_copilot_tool

## Source Context
- Original discussion on integrating Copilot Studio via Direct Line API.
- Test script `scratch/test_copilot_studio.py` which proved connectivity.
- Architecture requirement to implement tools within `nanobot/agent/tools/` and configure schema in `nanobot/config/schema.py`.

## Blast Radius Analysis
- **Core Agent Loop**: Safe. We are adding a new tool, not modifying the core agent loop or prompt formatting.
- **Tools Registry**: Minor. Modifying `tool_setup.py` to register the default tool.
- **Config**: Minor. Adding a new `copilot_studio` section to `config/schema.py` and updating tests.

## Zone Declaration
- **ZONE B**: Touches `nanobot/agent/tools/`, `nanobot/agent/tool_setup.py`, `nanobot/config/schema.py`, `config.sample.json`.

## Implementation Strategy
We will implement a standard tool subclassing `Tool` (from `nanobot.agent.tools.base`) located in `nanobot/agent/tools/consult_copilot.py`. This tool will use `httpx` to handle the Direct Line API protocol. The required `secret` will be added to the official `Config` schema, mapped to `ToolsConfig`. We will then manually register the new tool in `nanobot/agent/tool_setup.py`'s `_register_default_tools` function.

## Contract / Data Structures / Function Signatures
```python
# nanobot/config/schema.py
class CopilotStudioConfig(Base):
    enabled: bool = False
    secret: str = ""

# Added to ToolsConfig:
class ToolsConfig(Base):
    ...
    copilot_studio: CopilotStudioConfig = Field(default_factory=CopilotStudioConfig)

# nanobot/agent/tools/consult_copilot.py
class ConsultCopilotTool(Tool):
    name = "consult_copilot_studio"
    description = "..."
    # Schema requires a single `prompt` string parameter
    async def execute(self, prompt: str) -> str: ...
```

## Risk Notes
- **Timeouts**: The Copilot Studio agent may take a long time to respond (especially for Opus 4.6 on large queries). The `httpx` client needs an adequate polling timeout.
- **Authentication Exceptions**: Direct Line will throw `IntegratedAuthenticationNotSupportedInChannel` if the agent is incorrectly configured for AAD integrated auth. Tool must gracefully catch and return HTTP exceptions to the agent loop.

## Proposed Changes

#### [MODIFY] nanobot/config/schema.py
Add `CopilotStudioConfig` and register it inside `ToolsConfig`.

#### [MODIFY] config.sample.json
Add a new block under `tools` for the Copilot Studio configuration.

#### [MODIFY] tests/test_config_schema.py
Update schema loading tests to expect the new `copilot_studio` tool config block.

#### [NEW] nanobot/agent/tools/consult_copilot.py
Create the `ConsultCopilotTool` extending `Tool`. Handle Direct Line token generation and activity polling.

#### [MODIFY] nanobot/agent/tool_setup.py
Import `ConsultCopilotTool` and register it inside `_register_default_tools`.

#### [NEW] tests/unit/tools/test_consult_copilot.py
Unit tests to ensure the conversation state machine works correctly.

#### [MODIFY] TOOLS.md
Document the newly added `consult_copilot_studio` tool.

## Validation Plan
### Automated Tests
- Create a unit test `tests/unit/tools/test_consult_copilot.py` mocking the `httpx` responses.

### Manual Verification
- Run a Nanobot interactive session.
- Ask the local Nanobot: "Use the Copilot Studio tool to ask: what is the company policy?"
- Verify that Nanobot invokes the tool and the result is returned.
