import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from nanobot.agent.loop import AgentLoop
from nanobot.agent.middleware.base import TurnContext
from nanobot.agent.middleware.verification_mw import VerificationMiddleware
from nanobot.agent.tools.filesystem import WriteFileTool
from nanobot.agent.verification import VerificationLayer
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.context import ContextBuilder
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import VerificationConfig
from nanobot.providers.base import LLMResponse, ToolCallRequest


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with skills dir."""
    (tmp_path / "skills").mkdir()
    return tmp_path


def _create_skill(workspace, name, deps=None, missing=False):
    """Helper to create a skill and its config.defaults.json."""
    if missing:
        return
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    # Write SKILL.md
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\n---\n# {name}\n\nBody.\n",
        encoding="utf-8",
    )
    
    # Write config.defaults.json if deps are specified
    if deps is not None:
        config_data = {"depends_on": deps}
        (skill_dir / "config.defaults.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
    return skill_dir


def _make_test_agent(workspace: Path, *, max_iterations: int = 2) -> AgentLoop:
    """Build a lightweight AgentLoop for targeted loop-contract tests."""
    provider = MagicMock()
    with patch("nanobot.agent.tool_setup.setup_all_tools", lambda agent: None):
        return AgentLoop(
            workspace=workspace,
            bus=MessageBus(),
            provider=provider,
            model="test-model",
            max_iterations=max_iterations,
        )


def _make_runtime_workspace() -> Path:
    """Create a repo-local scratch workspace that avoids pytest tmpdir issues."""
    root = Path(".phase68_runtime")
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir()
    return workspace.resolve()


def _make_verification_agent_stub(workspace: Path, verification: VerificationLayer) -> MagicMock:
    agent = MagicMock()
    agent.workspace = workspace
    agent.tools = None
    agent._get_verification.return_value = verification
    agent._get_config.return_value = SimpleNamespace(
        agents=SimpleNamespace(sandbox=None)
    )
    agent.context = SimpleNamespace(
        add_tool_result=lambda messages, tc_id, tool_name, content: messages
        + [
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tool_name,
                "content": content,
            }
        ]
    )
    return agent


class TestSkillDependencies:
    """Test recursive dependency resolution for skills (P1)."""
    
    def test_no_dependencies(self, tmp_workspace):
        _create_skill(tmp_workspace, "skill_a")
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        deps = loader.resolve_dependencies("skill_a")
        assert deps == []

    def test_single_dependency(self, tmp_workspace):
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b")
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        deps = loader.resolve_dependencies("skill_a")
        assert deps == ["skill_b"]

    def test_nested_dependencies(self, tmp_workspace):
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b", "skill_c"])
        _create_skill(tmp_workspace, "skill_b", deps=["skill_d"])
        _create_skill(tmp_workspace, "skill_c", deps=["skill_d"])
        _create_skill(tmp_workspace, "skill_d")
        
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        deps = loader.resolve_dependencies("skill_a")
        
        # Should contain b, c, d in correct post-order or at least all unique
        assert set(deps) == {"skill_d", "skill_b", "skill_c"}
        # Ensure d comes before b and c because they depend on it
        assert deps.index("skill_d") < deps.index("skill_b")
        assert deps.index("skill_d") < deps.index("skill_c")

    def test_circular_dependency(self, tmp_workspace):
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b", deps=["skill_c"])
        _create_skill(tmp_workspace, "skill_c", deps=["skill_a"])
        
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        deps = loader.resolve_dependencies("skill_a")
        # Should gracefully break the cycle and return the dependencies
        assert set(deps) == {"skill_c", "skill_b"}

    def test_missing_dependency(self, tmp_workspace):
        _create_skill(tmp_workspace, "skill_a", deps=["skill_missing"])
        loader = SkillsLoader(tmp_workspace, builtin_skills_dir=Path("/nonexistent"))
        deps = loader.resolve_dependencies("skill_a")
        
        assert deps == []


class TestContextInjection:
    """Test ContextBuilder injecting prerequisite skills and pseudo-plan prompt."""
    
    def test_pseudo_plan_prompt(self):
        builder = ContextBuilder(workspace=Path("/nonexistent"))
        prompt = builder.build_system_prompt()
        assert "<think>" in prompt
        assert "pseudo-plan" in prompt.lower()
    def test_dependency_ordering_in_payload(self, tmp_workspace, monkeypatch):
        # Override get_always_skills to prevent picking up actual workspace skills
        monkeypatch.setattr("nanobot.agent.skills.SkillsLoader.get_always_skills", lambda self: [])
        
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b")
        
        builder = ContextBuilder(workspace=tmp_workspace)
        prompt = builder.build_system_prompt(skill_names=["skill_a"])
        
        # Ensure both are present
        assert "### Skill: skill_b" in prompt
        assert "### Skill: skill_a" in prompt
        
        # Ensure prerequisite b is injected BEFORE target a
        idx_b = prompt.index("### Skill: skill_b")
        idx_a = prompt.index("### Skill: skill_a")
        assert idx_b < idx_a

    def test_injection_budget_constraint(self, tmp_workspace, monkeypatch):
        # Override get_always_skills
        monkeypatch.setattr("nanobot.agent.skills.SkillsLoader.get_always_skills", lambda self: [])
        
        # Create a chain of skills
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b", deps=["skill_c"])
        _create_skill(tmp_workspace, "skill_c")
        
        builder = ContextBuilder(workspace=tmp_workspace)
        # Force a tiny budget that only fits skill_c (and maybe one more)
        monkeypatch.setattr(builder, "_SKILL_INJECTION_BUDGET", 50) 
        
        prompt = builder.build_system_prompt(skill_names=["skill_a"])
        
        # skill_c should be present since it's the deepest dependency
        assert "### Skill: skill_c" in prompt
        # skill_a should be dropped because the budget is exhausted
        assert "### Skill: skill_a" not in prompt

class TestProbe2Contradiction:
    """Regression probe to prove the conflict between ADR-62 Schema Null Compliance and visible <think> requirement."""
    
    def test_reasoning_content_null_compliance_conflict(self):
        """
        Demonstrates that when an LLM emits reasoning_content and tool_calls simultaneously:
        1. ADR-62 forces `content = None` to satisfy Azure OpenAI schema.
        2. Thus, it's impossible to have a visible <think> block inside `content`.
        """
        builder = ContextBuilder(workspace=Path("/nonexistent"))
        messages = []
        
        tool_calls = [{"id": "call_1", "type": "function", "function": {"name": "read_file"}}]
        # Simulate LLM returning a plan in reasoning_content and simultaneously calling a tool
        reasoning_text = "1. First plan\n2. Second plan"
        content_text = "<think>1. First plan</think>"
        
        # add_assistant_message simulates what the orchestrator does when it receives the LLM response
        updated_messages = builder.add_assistant_message(
            messages=messages,
            content=content_text,
            tool_calls=tool_calls,
            reasoning_content=reasoning_text
        )
        
        last_msg = updated_messages[-1]
        
        # Verify ADR-62 Null Compliance erased the content
        assert last_msg["content"] is None, "ADR-62 requires content to be None when tool_calls are present"
        
        # Verify the reasoning_content survived
        assert last_msg["reasoning_content"] == reasoning_text
        
        # Verify that because content is None, the visible <think> requirement cannot be met
        assert "<think>" not in (last_msg["content"] or "")


@pytest.mark.asyncio
async def test_p0_observability_block():
    agent = _make_test_agent(_make_runtime_workspace(), max_iterations=2)
    seen_messages: list[list[dict]] = []

    responses = [
        LLMResponse(
            content="call tool without think",
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="write_file",
                    arguments={"path": "notes.txt", "content": "x"},
                )
            ],
            reasoning_content="plain sentence only",
        ),
        LLMResponse(content="Recovered after retry", tool_calls=[]),
    ]

    async def fake_call_llm(messages, *args, **kwargs):
        seen_messages.append([dict(message) for message in messages])
        return responses.pop(0)

    pipeline = MagicMock()

    async def abort_if_called(ctx):
        ctx.abort("unexpected_pipeline", "pipeline should not run")

    pipeline.run_turn = AsyncMock(side_effect=abort_if_called)

    agent._call_llm_for_turn = AsyncMock(side_effect=fake_call_llm)
    agent._get_middleware_pipeline = MagicMock(return_value=pipeline)

    result = await agent._run_agent_loop_v2(
        initial_messages=[{"role": "user", "content": "write a file"}],
        channel="api",
        chat_id="test",
    )

    assert result.final_content == "Recovered after retry"
    assert pipeline.run_turn.await_count == 0
    assert len(seen_messages) == 2
    assert any(
        message.get("role") == "user"
        and "P0 observability contract violation" in (message.get("content") or "")
        for message in seen_messages[1]
    )


@pytest.mark.asyncio
async def test_p0_observability_reasoning_only_pass():
    agent = _make_test_agent(_make_runtime_workspace(), max_iterations=1)
    response = LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(
                id="call_1",
                name="read_file",
                arguments={"path": "report.md"},
            )
        ],
        reasoning_content="- inspect the requested file first",
    )

    pipeline = MagicMock()

    async def abort_after_validation(ctx):
        ctx.abort("stop_after_verification", "stop after verification")

    pipeline.run_turn = AsyncMock(side_effect=abort_after_validation)

    agent._call_llm_for_turn = AsyncMock(return_value=response)
    agent._get_middleware_pipeline = MagicMock(return_value=pipeline)

    with patch("nanobot.agent.loop.logger.info") as info_log:
        result = await agent._run_agent_loop_v2(
            initial_messages=[{"role": "user", "content": "open the report"}],
            channel="api",
            chat_id="test",
        )

    assert result.action_reason == "stop_after_verification"
    assert pipeline.run_turn.await_count == 1
    assert any(
        call.args and call.args[0] == "P0 Plan Verified"
        for call in info_log.call_args_list
    )


@pytest.mark.asyncio
async def test_allowed_write_set_block(monkeypatch: pytest.MonkeyPatch):
    workspace = _make_runtime_workspace()
    monkeypatch.chdir(workspace)

    verification = VerificationLayer(config=VerificationConfig())
    agent = _make_verification_agent_stub(workspace, verification)

    ctx = TurnContext(
        messages=[{"role": "user", "content": "write outside the workspace"}],
        iteration=1,
        channel="api",
        chat_id="test",
        consecutive_all_exceptions=0,
        recent_call_sigs=[],
        action_log=[],
        message_call_count=0,
        loop_injection_used=0,
    )
    ctx.tool_calls = [
        ToolCallRequest(
            id="call_1",
            name="write_file",
            arguments={"path": "../outside_workspace.txt", "content": "x"},
        )
    ]

    await VerificationMiddleware(agent).pre_process(ctx)

    assert ctx.action_reason == "l1_violation"
    assert any(
        "Out of bounds write" in (message.get("content") or "")
        for message in ctx.messages
    )


@pytest.mark.asyncio
async def test_allowed_write_set_blocks_workspace_root_outside_sandbox(
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = _make_runtime_workspace()
    monkeypatch.chdir(workspace)

    verification = VerificationLayer(config=VerificationConfig())
    agent = _make_verification_agent_stub(workspace, verification)

    ctx = TurnContext(
        messages=[{"role": "user", "content": "write to the workspace root"}],
        iteration=1,
        channel="api",
        chat_id="test",
        consecutive_all_exceptions=0,
        recent_call_sigs=[],
        action_log=[],
        message_call_count=0,
        loop_injection_used=0,
    )
    ctx.tool_calls = [
        ToolCallRequest(
            id="call_1",
            name="write_file",
            arguments={"path": "phase68_manual_ok.txt", "content": "ok"},
        )
    ]

    await VerificationMiddleware(agent).pre_process(ctx)

    assert ctx.action_reason == "l1_violation"
    assert any(
        "sandbox" in (message.get("content") or "").lower()
        for message in ctx.messages
    )


@pytest.mark.asyncio
async def test_allowed_write_set_allows_sandbox_write(
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = _make_runtime_workspace()
    # Reproduce the real dashboard/runtime case where the process cwd is not the
    # agent workspace. Relative sandbox paths must still resolve from workspace.
    monkeypatch.chdir(workspace.parent)

    verification = VerificationLayer(config=VerificationConfig())
    agent = _make_verification_agent_stub(workspace, verification)

    ctx = TurnContext(
        messages=[{"role": "user", "content": "write to sandbox"}],
        iteration=1,
        channel="api",
        chat_id="test",
        consecutive_all_exceptions=0,
        recent_call_sigs=[],
        action_log=[],
        message_call_count=0,
        loop_injection_used=0,
    )
    ctx.tool_calls = [
        ToolCallRequest(
            id="call_1",
            name="write_file",
            arguments={"path": "sandbox/phase68_manual_ok.txt", "content": "ok"},
        )
    ]

    await VerificationMiddleware(agent).pre_process(ctx)

    assert ctx.action_reason == ""
    result = await WriteFileTool(
        allowed_dir=workspace / "sandbox",
        base_dir=workspace,
    ).execute(
        path="sandbox/phase68_manual_ok.txt",
        content="ok",
    )
    assert result.startswith("Successfully wrote")
    assert (workspace / "sandbox" / "phase68_manual_ok.txt").read_text(encoding="utf-8") == "ok"
