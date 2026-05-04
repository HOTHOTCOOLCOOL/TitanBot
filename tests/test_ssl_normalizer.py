import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.agent.skills import SkillsLoader
from nanobot.agent.knowledge_graph import KnowledgeGraph

# --- T02: Normalizer Fail-Closed Logic ---
@pytest.mark.asyncio
async def test_ssl_normalizer_fail_closed():
    """Verify that if the LLM provider fails to generate a valid graph, the normalizer fails closed."""
    # This assumes the implementation will add SkillNormalizer in nanobot.agent.ssl_normalizer
    try:
        from nanobot.agent.ssl_normalizer import SkillNormalizer
    except ImportError:
        pytest.fail("T02: SkillNormalizer is not yet implemented")

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = MagicMock(content="INVALID JSON")
    
    normalizer = SkillNormalizer(provider=mock_provider, model="mock-model")
    result = await normalizer.normalize("test_skill", "Skill content here")
    
    assert result is None, "Normalizer must fail-closed (return None) on invalid LLM output"

# --- T02: Composite Hashing ---
def test_skills_loader_composite_hash(tmp_path):
    """Verify that SkillsLoader can compute a composite hash of all python and markdown files in a skill dir."""
    skill_dir = tmp_path / "skills" / "mock_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Mock skill", encoding="utf-8")
    (skill_dir / "validator.py").write_text("def validate(): pass", encoding="utf-8")
    
    loader = SkillsLoader(workspace=tmp_path)
    
    if not hasattr(loader, "_compute_skill_hash"):
        pytest.fail("T02: SkillsLoader missing _compute_skill_hash method")
        
    hash1 = loader._compute_skill_hash("mock_skill")
    assert hash1 is not None
    
    # Change code file, hash must change
    (skill_dir / "validator.py").write_text("def validate(): return True", encoding="utf-8")
    hash2 = loader._compute_skill_hash("mock_skill")
    assert hash1 != hash2, "Composite hash must change when validator.py changes"

# --- T03: ContextBuilder / SkillsLoader Injection Compression ---
def test_load_skills_for_context_with_ssl(tmp_path):
    """Verify that load_skills_for_context injects ONLY the Scheduling layer if skill_ssl exists."""
    kg = KnowledgeGraph(workspace=tmp_path)
    # Inject a mock skill_ssl entity
    kg._entities["mock_skill_ssl"] = {
        "type": "skill_ssl",
        "summary": "",
        "triple_indices": [],
        "properties": {
            "hash": "mockhash",
            "graph": {
                "Scheduling": {"trigger": "always", "cost": "low"},
                "Structural": {"depends_on": []},
                "Logical": {"rules": []}
            }
        }
    }
    
    skill_dir = tmp_path / "skills" / "mock_skill"
    skill_dir.mkdir(parents=True)
    long_md = "A" * 5000  # Raw SKILL.md is long
    (skill_dir / "SKILL.md").write_text(long_md, encoding="utf-8")
    
    loader = SkillsLoader(workspace=tmp_path)
    loader.kg = kg  # Mock dependency injection or lookup
    
    content = loader.load_skills_for_context(["mock_skill"])
    
    assert "Scheduling" in content
    assert "trigger" in content
    assert len(content) < 1000, "Context must be compressed to < 1000 chars by injecting only Scheduling layer"
    assert "AAAAA" not in content, "Raw SKILL.md content must NOT be injected if skill_ssl exists"

# --- T04: KG Schema Durability ---
def test_kg_rebuild_preserves_skill_ssl(tmp_path):
    """Verify that rebuild_entity_index explicitly preserves skill_ssl full payload."""
    kg = KnowledgeGraph(workspace=tmp_path)
    kg._entities["mock_skill_ssl"] = {
        "type": "skill_ssl",
        "summary": "Mock summary",
        "triple_indices": [],
        "properties": {
            "hash": "abc",
            "graph": {"Scheduling": {}}
        }
    }
    
    kg.rebuild_entity_index()
    
    assert "mock_skill_ssl" in kg._entities
    rebuilt = kg._entities["mock_skill_ssl"]
    assert rebuilt["type"] == "skill_ssl"
    assert "properties" in rebuilt, "Full custom payload (properties) must be preserved during reindex"
    assert "hash" in rebuilt["properties"]
    assert "graph" in rebuilt["properties"]
