#!/usr/bin/env python
"""Debug script to test email search without filters."""

import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
import asyncio

async def main():
    tool = OutlookTool()
    
    # Test 1: Find emails in inbox/reporting WITHOUT date filter
    print("=== Test 1: Find emails (no date filter, no attachment filter) ===")
    criteria = {
        "folder": "inbox/reporting",
        "has_attachments": False,  # No filter
        "max_results": 5
    }
    result = await tool.execute(action="find_emails", criteria=criteria)
    print(result[:2000])  # Print first 2000 chars
    
    # Test 2: Find emails in inbox/reporting WITH today's date but NO attachment filter
    print("\n=== Test 2: Find emails (today's date, no attachment filter) ===")
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"Searching for emails after: {today}")
    
    criteria2 = {
        "folder": "inbox/reporting",
        "received_after": today,
        "has_attachments": False,  # No filter
        "max_results": 5
    }
    result2 = await tool.execute(action="find_emails", criteria=criteria2)
    print(result2[:2000])
    
    # Test 3: Find emails WITH attachments but no date filter
    print("\n=== Test 3: Find emails (has attachments, no date filter) ===")
    criteria3 = {
        "folder": "inbox/reporting",
        "has_attachments": True,
        "max_results": 5
    }
    result3 = await tool.execute(action="find_emails", criteria=criteria3)
    print(result3[:2000])

if __name__ == "__main__":
    asyncio.run(main())
