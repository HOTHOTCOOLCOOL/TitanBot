import asyncio
import sys
from pathlib import Path
from loguru import logger

# Add nanobot to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from nanobot.agent.loop import AgentLoop
from nanobot.agent.context import ContextBuilder
from nanobot.bus.queue import MessageBus

class MockProvider:
    """Mock LLM Provider that outputs a fake completion message on the first turn."""
    def __init__(self):
        self.call_count = 0
        
    async def chat(self, messages, *args, **kwargs):
        from dataclasses import dataclass
        @dataclass
        class MockResponse:
            content: str
            has_tool_calls: bool
            tool_calls: list
            reasoning_content: str = ""
            
        self.call_count += 1
        
        # Turn 1: Fake completion
        if self.call_count == 1:
            print("\n[MockProvider] Turn 1: Emitting fake completion message...")
            return MockResponse(
                content="<think>我已经知道怎么发邮件了</think>\n✅ 已发送！任务处理完成。",
                has_tool_calls=False,
                tool_calls=[],
                reasoning_content="我已经知道怎么发邮件了"
            )
            
        # Turn 2: After getting caught, use a tool
        if self.call_count == 2:
            print("\n[MockProvider] Turn 2: Caught by system, now using tools...")
            
            @dataclass
            class MockToolCall:
                id: str
                name: str
                arguments: dict
                
            return MockResponse(
                content="Got caught, running actual tool now.",
                has_tool_calls=True,
                tool_calls=[MockToolCall(id="call_123", name="exec", arguments={"command": "echo 'sending email'"})],
                reasoning_content=""
            )
            
        # Turn 3: End
        print("\n[MockProvider] Turn 3: Terminating correctly.")
        return MockResponse(
            content="Tool executed, task actually completed.",
            has_tool_calls=False,
            tool_calls=[],
            reasoning_content=""
        )
        
    def get_default_model(self):
        return "mock-model"

async def run_test():
    workspace = Path("C:/Users/davidliu/.nanobot/workspace")
    bus = MessageBus()
    provider = MockProvider()
    
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        model="mock-model",
        max_iterations=5
    )
    
    # Disable actual MCP connections for test
    loop._mcp_connected = True 
    
    print("=== Starting Fake Completion Test ===\n")
    
    # We construct some initial basic messages
    initial_messages = [{"role": "user", "content": "帮我做一个有关科技的PPT，发送给 DAVIDMSN@HOTMAIL.COM"}]
    
    final_content, tools_used, _ = await loop._run_agent_loop(initial_messages)
    
    print("\n=== Test Results ===")
    print(f"Final Content: {final_content}")
    print(f"Tools Used: {tools_used}")
    
    if tools_used == ["exec"] and provider.call_count == 3:
        print("\n✅ PASS: The agent successfully caught the fake completion and forced the LLM to use a tool!")
    else:
        print("\n❌ FAIL: The agent did not behave as expected.")

if __name__ == "__main__":
    asyncio.run(run_test())
