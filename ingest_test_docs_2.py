import sys
import os
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path("d:/Python/nanobot").resolve()))
from nanobot.agent.vector_store import VectorMemory

async def main():
    workspace = Path("d:/Python/nanobot")
    vm = VectorMemory(workspace)
    
    docs = [
        workspace / "docs" / "archive" / "epoch_55_architecture_maintenance.md",
        workspace / "docs" / "adr" / "ADR-57-context-intelligence-upgrade.md",
        workspace / "docs" / "archive" / "epoch_49_ifcc_details.md"
    ]
    
    total = 0
    for doc in docs:
        if doc.exists():
            print(f"Ingesting {doc.name}...")
            content = doc.read_text(encoding="utf-8")
            count = vm.ingest_text(content, source=f"docs:{doc.name}")
            print(f"  -> Ingested {count} chunks.")
            total += count
            
    print(f"Done! {total} chunks.")

if __name__ == "__main__":
    asyncio.run(main())
