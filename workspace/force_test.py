import sys
import asyncio
from pathlib import Path

sys.path.insert(0, r"d:\Python\nanobot")

from nanobot.agent.tools.memory_search_tool import MemorySearchTool
from nanobot.agent.vector_store import VectorMemory
from nanobot.agent.marker_extractor import MarkerExtractor
from nanobot.config.loader import get_config

class MockStore:
    def append_daily_log(self, text):
        print(f"MockStore: Appended to daily log: {text}")
    def read_long_term(self):
        return ""
    def write_long_term(self, text):
        print(f"MockStore: Wrote long term: {text}")

class MockProvider:
    async def chat(self, *args, **kwargs):
        class Response:
            content = """[
              {
                "key": "邮件网关拥堵原因服务限流",
                "value": "今天下午3点由于上游供应商服务限流，导致公司邮件网关发生严重拥堵，发送给欧洲区的所有周报邮件退回。",
                "paragraphs": [0]
              }
            ]"""
        return Response()

async def ensure_init(vm):
    if hasattr(vm, '_ensure_init'):
        if asyncio.iscoroutinefunction(vm._ensure_init):
            await vm._ensure_init()
        else:
            vm._ensure_init()

async def main():
    cfg = get_config()
    print(f"Config marker_indexing: {getattr(cfg.features, 'marker_indexing', False)}")
    
    workspace = Path("d:/Python/nanobot/workspace")
    vm = VectorMemory("d:/Python/nanobot/workspace")
    vm.provider = MockProvider()
    vm.model = "gpt-mock"
    await ensure_init(vm)
    
    tool = MemorySearchTool()
    tool.set_vector_memory(vm)
    tool.set_memory_store(MockStore())
    
    res = await tool.execute(action="store", query="今天下午 3 点公司的邮件网关发生了严重的拥堵，导致发送给欧洲区的所有周报邮件退回。原因是上游供应商的服务限流。")
    print(f"Tool Return: {res}")
    
    print(f".marker_cache exists: {(workspace / '.marker_cache').exists()}")

asyncio.run(main())
