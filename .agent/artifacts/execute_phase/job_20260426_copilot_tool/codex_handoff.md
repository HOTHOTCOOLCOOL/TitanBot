# Codex Handoff

Job ID: job_20260426_copilot_tool
Artifact Directory: .agent/artifacts/execute_phase/job_20260426_copilot_tool/

## Artifact Registry
- `.agent/artifacts/execute_phase/job_20260426_copilot_tool/implementation_plan.md`
- `.agent/artifacts/execute_phase/job_20260426_copilot_tool/task.md`
- `.agent/artifacts/execute_phase/job_20260426_copilot_tool/codex_handoff.md`
- `nanobot/config/schema.py`
- `tests/test_config_schema.py`
- `config.sample.json`
- `nanobot/agent/tool_setup.py`
- `TOOLS.md`
- `nanobot/agent/tools/consult_copilot.py` (to be created)
- `tests/unit/tools/test_consult_copilot.py` (to be created)

## Source Context
- Adding Copilot Studio as a new local tool for Nanobot to consult Enterprise knowledge and offload large texts for free using the Direct Line API.

## Goal
Implement the `ConsultCopilotTool` as a built-in agent tool, update `config/schema.py`, `tool_setup.py`, documentation, and add unit tests.

## Allowed Write Set
- `nanobot/config/schema.py`
- `tests/test_config_schema.py`
- `config.sample.json`
- `nanobot/agent/tools/consult_copilot.py`
- `nanobot/agent/tool_setup.py`
- `tests/unit/tools/test_consult_copilot.py`
- `TOOLS.md`

## Forbidden Write Set
- Core agent loop files (`nanobot/agent/loop.py`, `middleware/`, etc.)
- Any existing provider implementations (`nanobot/providers/*`)
- Any existing tests outside the allowed write set.

## Red Tests to Satisfy
- `pytest tests/unit/tools/test_consult_copilot.py`
  - *Current Status*: FAILED
  - *Failure Summary*: `AssertionError` (ToolsConfig has no 'copilot_studio' attribute) and `ModuleNotFoundError` (No module named 'nanobot.agent.tools.consult_copilot').
- `pytest tests/test_config_schema.py` (ensure the added schema block doesn't break parsing)

## Green Exit Criteria
- Tool registers successfully and complies with `Tool` interface (`nanobot.agent.tools.base.Tool`).
- Schema parsing works without errors.
- Unit tests pass with 100% coverage for the new tool (mocking HTTP).
- Documentation is updated.

## Stop Conditions
- If any *existing* file in the Allowed Write Set cannot be found or modified, stop. (Note: `nanobot/agent/tools/consult_copilot.py` and `tests/unit/tools/test_consult_copilot.py` do not exist yet and must be created).

## Codex Startup Checklist
- [ ] Read `codex_handoff.md`
- [ ] Read `implementation_plan.md`
- [ ] Read `task.md`
- [ ] Verify access to *existing* Allowed Write Set files.

## Return Contract
After completing the tasks, write the results to:
`.agent/artifacts/execute_phase/job_20260426_copilot_tool/codex_result.md`
Follow the standard Codex Result format addressing each Task ID.
