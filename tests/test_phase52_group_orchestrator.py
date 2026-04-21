"""Tests for Phase 52 GroupRAG Complexity and Orchestration."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanobot.agent.complexity_detector import ComplexityDetector
from nanobot.agent.subagent import GroupAwareOrchestrator, SubagentManager, GroupResult

def test_complexity_detector_rules():
    from nanobot.config.loader import get_config
    config = get_config()
    config.features.parallel_reasoning = True
    config.features.parallel_complexity_token_threshold = 100
    config.features.parallel_complexity_entity_threshold = 5

    # Rule 3 + 4 met
    task1 = "/parallel 请对比分析这两个方案的区别"
    assert ComplexityDetector.should_parallelize(task1) is True

    # None met
    task2 = "hello world"
    assert ComplexityDetector.should_parallelize(task2) is False

    # Rule 1 + 4 met
    task3 = "分析" + (" a" * 450) # 900+ chars, > 100 token threshold + "分析" keyword
    assert ComplexityDetector.should_parallelize(task3) is True


@pytest.mark.asyncio
async def test_group_aware_orchestrator():
    manager = MagicMock(spec=SubagentManager)
    manager.provider = MagicMock()
    manager.model = "test-model"
    manager.exec_config = MagicMock()
    manager.exec_config.model_fields = {"parallel_conflict_cosine_threshold": 0.3}

    # Mock SubagentManager._run_subagent to just return a simulated output
    async def mock_run_subagent(task_id, task, label, origin, parent_trace, return_result):
        if "Angle 0" in label:
            return "Result A is definitely better."
        elif "Angle 1" in label:
            return "Result A is definitely better."
        else:
            return "Neutral."

    manager._run_subagent = mock_run_subagent

    # Mock the LLM split and evaluate
    split_mock = MagicMock()
    split_mock.content = '["Angle 0", "Angle 1"]'
    
    evaluate_mock = MagicMock()
    evaluate_mock.content = "NO_CONFLICT\n\nOverall it is agreed Result A is better."
    
    manager.provider.chat = AsyncMock(side_effect=[split_mock, evaluate_mock])

    orchestrator = GroupAwareOrchestrator(manager)
    result = await orchestrator.run_parallel("Compare A and B")
    
    assert isinstance(result, GroupResult)
    assert result.status == "OK"
    assert result.requires_human_input is False
    assert "Overall it is agreed" in result.conclusion
