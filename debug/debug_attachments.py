#!/usr/bin/env python
"""Debug script to check attachment detection."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
import asyncio

async def main():
    tool = OutlookTool()
    
    # Find emails
    criteria = {
        "folder": "inbox/reporting",
        "received_after": "2026-02-20",
        "has_attachments": False,
        "max_results": 3
    }
    
    result = await tool.execute(action="find_emails", criteria=criteria)
    print("=== Find Emails Result ===")
    print(result[:3000])
    
    print("\n=== Checking stored attachment_details ===")
    for i, email in enumerate(tool._last_search_results[:3]):
        print(f"\nEmail {i}: {email['subject']}")
        print(f"  document_count: {email.get('document_count', 0)}")
        print(f"  attachment_details: {email.get('attachment_details', [])}")

if __name__ == "__main__":
    asyncio.run(main())
