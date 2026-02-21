#!/usr/bin/env python
"""Debug script to list all Outlook folders."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
import asyncio

async def main():
    tool = OutlookTool()
    
    # List all folders
    print("=== All Email Folders ===")
    result = await tool.execute(action="list_folders")
    print(result)
    
    # Try to access the folder
    print("\n=== Trying to access 'inbox/reporting' ===")
    try:
        folder = tool._get_folder("inbox/reporting")
        print(f"Success! Folder: {folder.Name}")
        print(f"Total emails: {folder.Items.Count}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Try "Inbox/Reporting" with capital I
    print("\n=== Trying to access 'Inbox/Reporting' ===")
    try:
        folder = tool._get_folder("Inbox/Reporting")
        print(f"Success! Folder: {folder.Name}")
        print(f"Total emails: {folder.Items.Count}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Try "Reporting" directly
    print("\n=== Trying to access 'Reporting' ===")
    try:
        folder = tool._get_folder("Reporting")
        print(f"Success! Folder: {folder.Name}")
        print(f"Total emails: {folder.Items.Count}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
