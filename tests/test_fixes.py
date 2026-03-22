import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import nanobot modules
sys.path.insert(0, r"d:\Python\nanobot")

from nanobot.providers.custom_provider import CustomProvider
from nanobot.agent.vector_store import VectorMemory

async def test_provider():
    print("Testing custom provider error handling...")
    provider = CustomProvider(api_base="http://10.18.34.60:5888/v1")
    try:
        await provider.chat([{"role": "user", "content": "hello"}])
        print("FAIL: Custom provider did not raise an exception")
    except Exception as e:
        print(f"SUCCESS: Custom provider properly raised exception: {type(e).__name__} - {e}")

def test_vector_store():
    print("\nTesting vector store local loading...")
    workspace = Path(r"d:\Python\nanobot")
    vm = VectorMemory(workspace)
    # Perform search, which triggers _load()
    # It should load the model without reaching out to HuggingFace
    results = vm.search("test query")
    print("SUCCESS: Vector store loaded model and performed search")
    print(f"Results: {results}")

async def main():
    await test_provider()
    test_vector_store()

if __name__ == "__main__":
    asyncio.run(main())
