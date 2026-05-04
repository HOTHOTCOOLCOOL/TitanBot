import pytest
import os
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
from nanobot.agent.context import ContextBuilder
from nanobot.agent.task_tracker import Step
from nanobot.agent.verification import VerificationLayer
from nanobot.config.schema import VerificationConfig
from nanobot.agent.task_tracker import TrackedTask

# ── 1. KI Rules Adversarial Tests ─────────────────────────────────────

@pytest.fixture
def phase59_dir():
    root = Path(".pytest_phase59_local") / uuid4().hex
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_ki_rules_mtime_cache_invalidation(phase59_dir):
    """Bypass purely static caching: ensure mtime invalidation refreshes rules."""
    ki_dir = phase59_dir / ".nanobot" / "ki_rules"
    ki_dir.mkdir(parents=True)
    
    # Init first state
    ki_file = ki_dir / "test1.ki.json"
    ki_file.write_text(json.dumps({"keywords": ["test"], "rule": "Rule v1"}), encoding="utf-8")
    
    vcfg = VerificationConfig(l0_enabled=True)
    layer = VerificationLayer(config=vcfg)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("pathlib.Path.cwd", lambda: ki_dir.parent.parent)
        
        system_messages = [{"role": "system", "content": "Base"}]
        
        # 1. First trigger
        layer.enrich_context(system_messages, "this is a test", 0)
        assert "Rule v1" in system_messages[0]["content"]
        assert "Rule v2" not in system_messages[0]["content"]
        
        # 2. Modify rule behind the scenes + tweak file mtime to guarantee OS detection
        system_messages = [{"role": "system", "content": "Base"}]
        ki_file.write_text(json.dumps({"keywords": ["test"], "rule": "Rule v2"}), encoding="utf-8")
        # Touch only the FILE, leaving ki_dir mtime untouched!
        os.utime(ki_file, (ki_file.stat().st_atime, ki_file.stat().st_mtime + 10))
        
        layer.enrich_context(system_messages, "this is a test", 0)
        assert "Rule v2" in system_messages[0]["content"], "Cache failed to invalidate via mtime"


def test_ki_rules_budget_hard_cap_exhaustion(phase59_dir):
    """Adversarial: Mass injection of rules must respect 8000 byte total budget."""
    ki_dir = phase59_dir / ".nanobot" / "ki_rules"
    ki_dir.mkdir(parents=True)
    
    for i in range(20):
        ki_file = ki_dir / f"test{i}.ki.json"
        ki_file.write_text(json.dumps({
            "keywords": ["attack"], 
            "rule": "X" * 499  # 500 chars limit per rule handled internally, we spam 20 of them
        }), encoding="utf-8")
        
    vcfg = VerificationConfig(l0_enabled=True)
    layer = VerificationLayer(config=vcfg)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("pathlib.Path.cwd", lambda: ki_dir.parent.parent)
        
        system_messages = [{"role": "system", "content": "Base"}]
        injected = layer.enrich_context(system_messages, "this is an attack", 0)
        
        assert injected <= 8000
        # Must clip and not append ALL 20 rules
        assert system_messages[0]["content"].count("Tactical Rule") < 20


def test_ki_rules_fallback_to_cwd_when_workspace_rules_missing(phase59_dir):
    """Missing runtime workspace rules should fall back to another available source."""
    runtime_workspace = phase59_dir / "runtime_workspace"
    repo_root = phase59_dir / "repo_root"
    ki_dir = repo_root / ".nanobot" / "ki_rules"
    ki_dir.mkdir(parents=True)
    (ki_dir / "excel-com.ki.json").write_text(
        json.dumps(
            {
                "keywords": ["excel", "pivot", "chart"],
                "rule": "Prefer excel_actuator over raw win32com.",
            }
        ),
        encoding="utf-8",
    )

    vcfg = VerificationConfig(l0_enabled=True)
    workflow = MagicMock()
    workflow.workspace = runtime_workspace
    layer = VerificationLayer(config=vcfg, knowledge_workflow=workflow)

    with pytest.MonkeyPatch.context() as m:
        m.setattr("pathlib.Path.cwd", lambda: repo_root)

        system_messages = [{"role": "system", "content": "Base"}]
        layer.enrich_context(
            system_messages,
            "Read Excel Book2 and inspect pivot/chart via COM.",
            0,
        )

        assert "Prefer excel_actuator over raw win32com." in system_messages[0]["content"]


# ── 2. TaskTracker Adversarial Tests ──────────────────────────────────

def test_task_tracker_zero_steps_injection():
    """Ensure that an active task with exactly 0 steps is STILL injected. (Root Cause C/B)"""
    workspace = MagicMock()
    workspace.expanduser.return_value = workspace
    workspace.resolve.return_value = "fake_workspace"
    
    builder = ContextBuilder(workspace)
    
    # Hijack build_system_prompt and task_tracker retrieval
    builder.build_system_prompt = MagicMock(return_value="SystemPrompt Base.")
    builder.vector_memory = MagicMock()
    
    import sys
    # Patch TaskTracker logic manually
    with pytest.MonkeyPatch.context() as m:
        fake_task = TrackedTask("t1", "key1", "0-step adversarial request")
        # Ensure zero steps
        fake_task.steps = [] 
        
        fake_tracker = MagicMock()
        fake_tracker.get_active_task.return_value = fake_task
        
        m.setattr("nanobot.agent.task_tracker.get_active_tracker", lambda: fake_tracker)
        
        messages = builder.build_messages(
            history=[],
            current_message="hello",
            context_limit=120000
        )
        
        system_content = messages[0]["content"]
        assert "Active Task Tracker" in system_content, "0-step task bypassed injection barrier"
        assert "0-step adversarial request" in system_content
        assert "Progress" in system_content
        assert "no recorded steps yet" in system_content


def test_task_tracker_running_step_and_progress_visible():
    """Running steps should be rendered as active progress, not as pending."""
    workspace = MagicMock()
    workspace.expanduser.return_value = workspace
    workspace.resolve.return_value = "fake_workspace"

    builder = ContextBuilder(workspace)
    builder.build_system_prompt = MagicMock(return_value="SystemPrompt Base.")
    builder.vector_memory = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        fake_task = TrackedTask("t3-progress", "key3", "extract workbook summary")
        fake_task.steps = [
            Step(1, "open workbook"),
            Step(2, "inspect pivot"),
            Step(3, "draft report"),
        ]
        fake_task.steps[0].status = "completed"
        fake_task.steps[1].status = "running"
        fake_task.steps[2].status = "pending"

        fake_tracker = MagicMock()
        fake_tracker.get_active_task.return_value = fake_task
        fake_tracker.get_progress.return_value = {
            "total_steps": 3,
            "completed_steps": 1,
            "progress_percent": 33,
            "current_step": "inspect pivot",
        }

        m.setattr("nanobot.agent.task_tracker.get_active_tracker", lambda: fake_tracker)

        messages = builder.build_messages(
            history=[],
            current_message="continue",
            context_limit=120000,
        )

        system_content = messages[0]["content"]
        assert "Active Task Tracker" in system_content
        assert "Status" in system_content
        assert "Progress" in system_content
        assert "33%" in system_content
        assert "Current Step" in system_content
        assert "inspect pivot" in system_content
        assert "running" in system_content


def test_task_tracker_massive_budget_clip():
    """Ensure TaskTracker cannot breach the `context_limit` budget check."""
    workspace = MagicMock()
    workspace.expanduser.return_value = workspace
    workspace.resolve.return_value = "fake_workspace"
    
    builder = ContextBuilder(workspace)
    
    # We supply a massive base prompt that eats up ALMOST ALL context_limit
    builder.build_system_prompt = MagicMock(return_value="X" * 119900)
    builder.vector_memory = MagicMock()
    
    with pytest.MonkeyPatch.context() as m:
        fake_task = TrackedTask("t2", "key2", "Huge " * 100)
        fake_tracker = MagicMock()
        fake_tracker.get_active_task.return_value = fake_task
        
        m.setattr("nanobot.agent.task_tracker.get_active_tracker", lambda: fake_tracker)
        
        # Limit is 120,000. Setup takes 119,900. Tracker string is ~400 char max.
        # Should fit if budget is exactly 120,400? Wait, ADR-59 says:
        # if len(system_prompt) + len(status_text) <= context_limit
        # If context_limit is severely truncated to exactly 119900, it MUST NOT inject.
        messages = builder.build_messages(
            history=[],
            current_message="hello",
            context_limit=119900 
        )
        
        system_content = messages[0]["content"]
        assert "Active Task Tracker" not in system_content, "Budget limit breached by TaskTracker"
