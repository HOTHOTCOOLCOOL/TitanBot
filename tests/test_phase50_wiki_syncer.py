import json
import pytest
from pathlib import Path
from nanobot.agent.wiki_syncer import WikiSyncer, sanitize_title

def test_sanitize_title():
    # Test boundary constraints for Windows illegal characters
    assert sanitize_title("Hello:World") == "Hello_World"
    assert sanitize_title("Test \\ / : * ? \" < > | End") == "Test _ _ _ _ _ _ _ _ _ End"
    assert sanitize_title("Normal Title 123") == "Normal Title 123"
    assert sanitize_title("中文标题") == "中文标题"
    assert sanitize_title("   Spaces   ") == "Spaces"

def test_wiki_syncer_empty_state(tmp_path):
    # Graceful empty state checks
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    syncer = WikiSyncer(workspace)
    # The files don't exist yet, we expect 0,0,0
    e, t, d = syncer.sync(force=True)
    assert e == 0
    assert t == 0
    assert d == 0
    
    # Check that it didn't create anything other than the base dirs and _index.md / _log.md
    assert syncer.wiki_dir.exists()
    assert (syncer.wiki_dir / "_index.md").exists()
    assert (syncer.wiki_dir / "_log.md").exists()

def test_wiki_syncer_with_data(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory_dir = workspace / "memory"
    memory_dir.mkdir()
    
    graph_data = {
        "triples": [
            {"source": "Apple", "predicate": "makes", "target": "iPhone", "context": "In 2007"}
        ],
        "_aliases": {
            "Apple Inc.": "Apple"
        }
    }
    
    exp_data = {
        "experiences": [
            {"trigger": "User says hi", "prompt": "Say hello back."}
        ]
    }
    
    (memory_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")
    (memory_dir / "experiences.json").write_text(json.dumps(exp_data), encoding="utf-8")
    
    syncer = WikiSyncer(workspace)
    e, t, d = syncer.sync(force=True)
    assert e == 1
    assert t == 1
    assert d == 1
    
    # Check created files
    entity_file = syncer.entities_dir / "Apple.md"
    assert entity_file.exists()
    content = entity_file.read_text(encoding="utf-8")
    assert "Apple Inc." in content  # alias check
    assert "type: \"kg_entity\"" in content
    assert "| makes | [[iPhone]] | In 2007 |" in content
    
    # Check directives
    directives = list(syncer.directives_dir.glob("*-User says hi-auto.md"))
    assert len(directives) == 1
    assert "Directive: User says hi" in directives[0].read_text(encoding="utf-8")
    assert "Say hello back." in directives[0].read_text(encoding="utf-8")

def test_wiki_syncer_idempotency(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory_dir = workspace / "memory"
    memory_dir.mkdir()
    
    graph_file = memory_dir / "graph.json"
    graph_file.write_text(json.dumps({"triples": []}), encoding="utf-8")
    
    syncer = WikiSyncer(workspace)
    # First sync (force=False) should trigger because last_sync_time is 0
    e, t, d = syncer.sync(force=False)
    
    # Second sync should be 0,0,0
    e2, t2, d2 = syncer.sync(force=False)
    assert e2 == 0
    assert t2 == 0
    assert d2 == 0
