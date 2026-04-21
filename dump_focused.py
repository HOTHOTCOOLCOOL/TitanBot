import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path("d:/Python/nanobot").resolve()))
from nanobot.agent.context import ContextBuilder

async def dump_focused():
    cb = ContextBuilder(Path("d:/Python/nanobot"))
    query = "Explain the detailed internal logic of our memory architecture, specifically focusing on ContextBuilder, IFCC, and the Waterfall Budget mechanisms."
    rag_results = cb.vector_memory.search(query, top_k=15)
    formatted = cb.vector_memory.format_results_for_context(rag_results)
    
    with open("d:/Python/nanobot/debug_focused_rag.txt", "w", encoding="utf-8") as f:
        f.write(formatted)

asyncio.run(dump_focused())
