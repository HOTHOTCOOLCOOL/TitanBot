import json
import os
import sys

# Load config
try:
    with open(r"C:\Users\davidliu\.nanobot\config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"Failed to load config: {e}")
    sys.exit(1)

model = config["agents"]["defaults"]["model"]
volc_key = config["providers"].get("volcengine", {}).get("apiKey", "")

print(f"Testing model: {model}")
if not volc_key or volc_key == "your_volcengine_api_key_here":
    print("WARNING: It looks like you haven't pasted your actual API Key into the config.json yet.")
    sys.exit(1)

# Ensure liteLLM is available
try:
    import litellm
except ImportError:
    print("LiteLLM is not installed in this environment.")
    sys.exit(1)

# Set the key via environment since LiteLLM reads it there
os.environ["VOLCENGINE_API_KEY"] = volc_key
# Optional: also set litellm.api_key just in case
litellm.api_key = volc_key

print("Sending request to LiteLLM...")
try:
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": "你好！请用一句话介绍你自己。"}],
        timeout=15
    )
    print(f"\n--- API Success ---\n{response.choices[0].message.content}\n-------------------")
except Exception as e:
    import traceback
    print(f"\n--- API Error ---\n{e}\n-----------------")
    traceback.print_exc()
