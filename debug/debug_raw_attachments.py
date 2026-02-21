#!/usr/bin/env python
"""Debug script to see raw attachment info - try both 0 and 1 based."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
import asyncio

async def main():
    tool = OutlookTool()
    
    # Get folder
    folder = tool._get_folder("inbox/reporting")
    items = folder.Items
    items.Sort("[ReceivedTime]", True)
    
    print("=== Checking first email - trying different indexing ===\n")
    
    i = 0
    item = items[i + 1]
    
    print(f"Subject: {item.Subject}")
    
    raw_count = item.Attachments.Count
    print(f"Raw attachment count: {raw_count}")
    
    # Try 0-based indexing
    print("\n--- Trying 0-based indexing ---")
    try:
        att = item.Attachments[0]
        print(f"  Attachment[0]: {att.FileName}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Try 1-based indexing
    print("\n--- Trying 1-based indexing ---")
    try:
        att = item.Attachments[1]
        print(f"  Attachment[1]: {att.FileName}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Try iteration
    print("\n--- Trying iteration ---")
    try:
        for att in item.Attachments:
            print(f"  Got attachment via iteration: {att.FileName}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Try using .Item()
    print("\n--- Trying .Item(1) ---")
    try:
        att = item.Attachments.Item(1)
        print(f"  Attachments.Item(1): {att.FileName}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Check what type of object Attachments is
    print(f"\n--- Type info ---")
    print(f"Type: {type(item.Attachments)}")

if __name__ == "__main__":
    asyncio.run(main())
