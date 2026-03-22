import pytest
from pathlib import Path
from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow

@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def knowledge_store(temp_workspace):
    return TaskKnowledgeStore(temp_workspace)

@pytest.fixture
def workflow(temp_workspace):
    return KnowledgeWorkflow(workspace=temp_workspace)

def test_add_and_retrieve_experience(knowledge_store):
    knowledge_store.add_experience(
        context_trigger="Error: Connection refused",
        tactical_prompt="Wait 5 seconds and retry the connection.",
        action_type="error_handling"
    )
    
    exps = knowledge_store.get_experiences()
    assert len(exps) == 1
    assert exps[0]["trigger"] == "Error: Connection refused"
    assert exps[0]["prompt"] == "Wait 5 seconds and retry the connection."
    assert exps[0]["action_type"] == "error_handling"
    assert exps[0]["success_count"] == 1

def test_match_experience_exact(workflow):
    store = workflow.knowledge_store
    store.add_experience("Out of memory", "Reduce batch size to 16", "optimization")
    
    # Exact match
    prompt = workflow.match_experience("Out of memory")
    assert prompt == "Reduce batch size to 16"

def test_match_experience_hybrid_bm25(workflow):
    store = workflow.knowledge_store
    store.add_experience(
        "Invalid API key provided for the service", 
        "Check the .env file and ensure API_KEY is set correctly.",
        "auth"
    )
    store.add_experience(
        "Timeout when connecting to database",
        "Increase DB_TIMEOUT in config.",
        "db"
    )
    
    # Partial semantic/word match triggering BM25 / Jaccard
    prompt = workflow.match_experience("The service returned invalid api key")
    assert prompt == "Check the .env file and ensure API_KEY is set correctly."
    
    prompt2 = workflow.match_experience("Timeout connecting to database service")
    assert prompt2 == "Increase DB_TIMEOUT in config."
    
def test_match_experience_no_match(workflow):
    store = workflow.knowledge_store
    store.add_experience("Disk full", "Delete temp files", "system")
    
    prompt = workflow.match_experience("Network error")
    assert prompt is None


def test_match_experience_empty_bank(workflow):
    """Empty experience bank should return None without error."""
    prompt = workflow.match_experience("Any query at all")
    assert prompt is None


def test_match_experience_no_store():
    """Workflow without a workspace should return None gracefully."""
    wf = KnowledgeWorkflow(workspace=None)
    prompt = wf.match_experience("Any query")
    assert prompt is None


def test_match_experience_multiple_picks_best(workflow):
    """When multiple experiences exist, the best match should win."""
    store = workflow.knowledge_store
    store.add_experience("Send email via Outlook to the manager", "Use outlook tool", "email")
    store.add_experience("Generate SSRS report PDF output", "Use ssrs tool", "report")
    store.add_experience("Post Slack notification to channel", "Use slack api", "notification")

    # Query shares many words with the first experience
    prompt = workflow.match_experience("Send email via Outlook to the manager now")
    assert prompt == "Use outlook tool"


def test_match_experience_special_characters(workflow):
    """Triggers with special characters should not crash."""
    store = workflow.knowledge_store
    store.add_experience(
        "Error: <html>500 Internal Server Error</html>",
        "Retry after 30 seconds",
        "error"
    )

    prompt = workflow.match_experience("Error: <html>500 Internal Server Error</html>")
    assert prompt == "Retry after 30 seconds"


def test_match_experience_case_insensitive(workflow):
    """Matching should work case-insensitively for BM25/word overlap."""
    store = workflow.knowledge_store
    store.add_experience("TIMEOUT ERROR in DATABASE", "Increase timeout setting", "db")

    prompt = workflow.match_experience("timeout error in database")
    assert prompt == "Increase timeout setting"
