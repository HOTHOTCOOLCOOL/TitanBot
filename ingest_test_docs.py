import sys
import os
from pathlib import Path

# Add nanobot to path
sys.path.insert(0, str(Path("d:/Python/nanobot").resolve()))

from nanobot.agent.vector_store import VectorMemory
import asyncio

async def main():
    workspace = Path("d:/Python/nanobot")
    vm = VectorMemory(workspace)
    print("Initializing VectorMemory...")
    
    docs_to_ingest = [
        workspace / "docs" / "rules" / "ARCHITECTURE.md",
        workspace / "docs" / "adr" / "ADR-49-ifcc-context-condensation.md",
        workspace / "docs" / "adr" / "ADR-55-architecture-maintenance.md",
        workspace / "nanobot" / "agent" / "context.py"
    ]
    
    total = 0
    for doc in docs_to_ingest:
        if doc.exists():
            print(f"Ingesting {doc.name}...")
            content = doc.read_text(encoding="utf-8")
            count = vm.ingest_text(content, source=f"docs:{doc.name}")
            print(f"  -> Ingested {count} chunks.")
            total += count
        else:
            print(f"File not found: {doc}")
            
    print(f"Total chunks ingested: {total}")

if __name__ == "__main__":
    asyncio.run(main())
