# Task

- [ ] T01 Update `nanobot/config/schema.py` to add `CopilotStudioConfig` to `ToolsConfig`
- [ ] T02 Update `config.sample.json` to include the default `copilot_studio` settings
- [ ] T03 Update `tests/test_config_schema.py` to assert the new tool config is parsed
- [ ] T04 Create `nanobot/agent/tools/consult_copilot.py` with `ConsultCopilotTool` inheriting from `nanobot.agent.tools.base.Tool`
- [ ] T05 Update `nanobot/agent/tool_setup.py` to register `ConsultCopilotTool` in `_register_default_tools`
- [ ] T06 Create unit tests for `ConsultCopilotTool` in `tests/unit/tools/test_consult_copilot.py` (mocking httpx)
- [ ] T07 Update `TOOLS.md` with documentation for `consult_copilot_studio`
