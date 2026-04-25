import asyncio
from pathlib import Path
from nanobot.agent.tools.knowledge_map import KnowledgeMapTool, _MAP_OUTPUT_CAP
import json

def test_truncation_bug(tmp_path: Path):
    triples = [{"source": "A" * 3500, "target": "B", "predicate": "rel"}]
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "graph.json").write_text(json.dumps({"triples": triples}), encoding="utf-8")
    
    tool = KnowledgeMapTool(workspace=tmp_path)
    result = asyncio.run(tool.execute())
    
    assert len(result) <= _MAP_OUTPUT_CAP, f"Failed! Length was {len(result)}"
