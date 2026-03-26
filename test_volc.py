import asyncio
from nanobot.config.loader import load_config
from nanobot.providers.factory import get_llm

async def main():
    print("Loading config...")
    config = load_config()
    model = config.agents.defaults.model
    print(f"Config loaded. LLM set to: {model}")
    print(f"Provider Volcengine API Key set? {'Yes' if config.providers.volcengine.api_key else 'No'}")
    
    print("Initializing LLM...")
    llm = get_llm(config)
    print("Sending prompt: 'Hello, what is your name?'")
    try:
        response = await llm.achat("Hello, what is your name?")
        print(f"\n--- Response from Volcengine ---\n{response}\n--------------------------------")
    except Exception as e:
        import traceback
        print(f"\n--- Error occurred ---\n{e}\n----------------------")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
