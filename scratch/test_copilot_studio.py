"""
Test script: Call a Copilot Studio Agent via Direct Line API.

Usage:
    python test_copilot_studio.py --secret "YOUR_SECRET" --question "你好"
"""

import argparse
import asyncio
import sys
import os
import json
import time

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx


DIRECT_LINE_BASE = "https://directline.botframework.com/v3/directline"
USER_ID = "nanobot_test_user"


async def get_token_from_secret(secret: str) -> dict:
    """Exchange Direct Line Secret for a Token."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DIRECT_LINE_BASE}/tokens/generate",
            headers={"Authorization": f"Bearer {secret}"},
        )
        resp.raise_for_status()
        return resp.json()


async def start_conversation(token: str) -> dict:
    """Start a new Direct Line conversation."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DIRECT_LINE_BASE}/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def send_message(token: str, conversation_id: str, text: str) -> None:
    """Send a message to the agent."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "type": "message",
                "from": {"id": USER_ID, "name": "Nanobot Test"},
                "text": text,
                "textFormat": "plain",
                "locale": "zh-CN",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"  [OK] Message sent (activity id: {data.get('id', '?')})")


async def poll_response(
    token: str, conversation_id: str, watermark: str | None = None, timeout_s: int = 30
) -> tuple[str, str | None]:
    """Poll for agent response. Returns (reply_text, new_watermark)."""
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=30) as client:
        while time.monotonic() - start < timeout_s:
            params = {}
            if watermark:
                params["watermark"] = watermark

            resp = await client.get(
                f"{DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            new_watermark = data.get("watermark")

            # Filter: only agent replies (not our own messages)
            bot_replies = [
                a
                for a in data.get("activities", [])
                if a.get("type") == "message" and a["from"]["id"] != USER_ID
            ]

            if bot_replies:
                # Print raw activities for debugging
                for r in bot_replies:
                    print(f"  [DEBUG] Activity from '{r['from'].get('name', '?')}' (id={r['from']['id']})")
                    print(f"  [DEBUG]   type={r.get('type')}, text length={len(r.get('text', ''))}")
                
                combined = "\n".join(r.get("text", "") for r in bot_replies if r.get("text"))
                return combined, new_watermark

            await asyncio.sleep(1)

    return "[TIMEOUT] Agent did not respond within timeout", watermark


async def main():
    parser = argparse.ArgumentParser(description="Test Copilot Studio Agent via Direct Line")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--token-endpoint", help="Copilot Studio Token Endpoint URL")
    group.add_argument("--secret", help="Direct Line Secret")
    parser.add_argument("--question", default=None, help="Question to ask")
    args = parser.parse_args()

    # -- Step 1: Get token --
    print("[Step 1] Obtaining Direct Line token...")
    if args.token_endpoint:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(args.token_endpoint)
            resp.raise_for_status()
            token_data = resp.json()
    else:
        token_data = await get_token_from_secret(args.secret)

    token = token_data["token"]
    print(f"  [OK] Token obtained (expires_in: {token_data.get('expires_in', '?')}s)")
    print(f"  Token preview: {token[:20]}...{token[-10:]}")

    # -- Step 2: Start conversation --
    print("\n[Step 2] Starting conversation...")
    conv_data = await start_conversation(token)
    conversation_id = conv_data["conversationId"]
    token = conv_data.get("token", token)
    print(f"  [OK] Conversation started: {conversation_id}")

    # -- Step 3: Send startConversation event --
    print("\n[Step 3] Sending startConversation event...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "type": "event",
                "name": "startConversation",
                "from": {"id": USER_ID, "name": "Nanobot Test"},
            },
        )
        print(f"  Start event status: {resp.status_code}")

    # Wait for greeting
    await asyncio.sleep(2)
    greeting, watermark = await poll_response(token, conversation_id, timeout_s=8)
    if greeting and "TIMEOUT" not in greeting:
        print(f"\n[Agent Greeting]\n{greeting}")
    else:
        print("  (No greeting received, continuing...)")

    # -- Step 4: Send question --
    question = args.question or "你好，请介绍一下你自己"
    print(f"\n[Step 4] Sending question: {question}")
    await send_message(token, conversation_id, question)
    print("  Waiting for agent response...")

    reply, watermark = await poll_response(token, conversation_id, watermark, timeout_s=60)
    print(f"\n{'='*60}")
    print(f"[Agent Reply]")
    print(f"{'='*60}")
    print(reply)
    print(f"{'='*60}")

    # -- Step 5: Follow-up question --
    followup = "你能帮我做什么？你有什么能力？"
    print(f"\n[Step 5] Follow-up question: {followup}")
    await send_message(token, conversation_id, followup)
    print("  Waiting for agent response...")

    reply2, watermark = await poll_response(token, conversation_id, watermark, timeout_s=60)
    print(f"\n{'='*60}")
    print(f"[Agent Reply - Follow-up]")
    print(f"{'='*60}")
    print(reply2)
    print(f"{'='*60}")

    print("\n[DONE] Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
