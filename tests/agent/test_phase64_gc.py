# test_phase64_gc.py
import pytest
from pathlib import Path
from nanobot.agent.vector_store import VectorMemory
import shutil

def test_gc_deletes_ghosts_and_verifies_footprint(tmp_path: Path):
    """Test purge_flagged_gc deletes items and correctly handles footprint limits."""
    vm = VectorMemory(workspace=tmp_path)
    
    # 1. Setup mock Chroma collection
    vm._ensure_init()
    vm._collection.add(
        documents=["doc1", "doc2"],
        metadatas=[{"file_path": "/fake/1"}, {"file_path": "/fake/2"}],
        ids=["id1", "id2"]
    )
    
    # 2. Flag an item manually
    vm._flagged_for_gc.add("id1")
    
    # 3. Create fake database heavy file to trigger compaction limit
    db_dir = tmp_path / "memory" / "vectordb"
    db_dir.mkdir(parents=True, exist_ok=True)
    heavy_file = db_dir / "fake_db.sqlite3"
    heavy_blob = b"A" * (201 * 1024 * 1024) # 201MB
    with open(heavy_file, "wb") as f:
        f.write(heavy_blob)
    
    # 4. Trigger purge (the footprint is ~201MB > 200MB default limit)
    # This should clear id1, and then call full_reindex because footprint is large
    # To prevent full_reindex from actually running a massive scan without knowledge tasks,
    # we just let it execute. We can verify id1 is deleted physically.
    purged = vm.purge_flagged_gc(max_footprint_mb=200)
    
    assert purged == 1
    # Check that id1 (and id2 since it's a dummy) is wiped by the full_reindex
    remaining = vm._collection.get()
    assert len(remaining["ids"]) == 0
    
    # Cleaning up large file
    heavy_file.unlink(missing_ok=True)
