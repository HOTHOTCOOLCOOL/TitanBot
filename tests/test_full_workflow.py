#!/usr/bin/env python
"""
Full End-to-End Workflow Test

This script simulates the complete nanobot workflow:
- Search emails in inbox/reporting folder received today
- Download all attachments
- Extract content from all attachments
- Generate a comprehensive report using local LLM

Usage:
    python test_full_workflow.py
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool


# LLM Configuration - UPDATE THESE FOR YOUR ENVIRONMENT
LLM_CONFIG = {
    "api_base": "http://10.18.34.60:5888/v1",
    "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
    "api_key": "none"
}


class FullWorkflowTester:
    """Full workflow tester simulating nanobot behavior."""
    
    def __init__(self):
        self.outlook_tool = OutlookTool()
        self.attachment_tool = AttachmentAnalyzerTool()
        self.results = {
            "emails_found": [],
            "attachments": [],
            "extracted_content": {},
            "report": ""
        }
    
    async def run(self, folder="inbox/reporting", generate_report=True):
        """Run the full workflow."""
        print("="*70)
        print("FULL EMAIL ANALYSIS WORKFLOW")
        print("="*70)
        print(f"Folder: {folder}")
        print(f"Date: Today ({datetime.now().strftime('%Y-%m-%d')})")
        print("="*70)
        
        # Step 1: Find today's emails in the folder
        print("\n📧 Step 1: Searching for today's emails...")
        today = datetime.now().strftime('%Y-%m-%d')
        
        criteria = {
            "folder": folder,
            "received_after": today,
            "has_attachments": False,  # Get all emails first
            "max_results": 10
        }
        
        result = await self.outlook_tool.execute(action="find_emails", criteria=criteria)
        print(result)
        
        # Parse to check if we found emails
        if "Found" in result and "email(s)" in result:
            import re
            match = re.search(r"Found (\d+) email", result)
            if match:
                email_count = int(match.group(1))
                print(f"\n✅ Found {email_count} email(s)")
                
                # Step 2: Download all attachments from all emails
                print("\n📥 Step 2: Downloading attachments...")
                
                save_dir = tempfile.gettempdir()
                
                for email_idx in range(min(email_count, 5)):
                    attach_result = await self.outlook_tool.execute(
                        action="get_all_attachments",
                        email_index=email_idx,
                        save_directory=save_dir
                    )
                    
                    if "Saved" in attach_result:
                        print(f"  Email {email_idx}: Downloaded attachments")
                        for line in attach_result.split('\n'):
                            if '->' in line and 'Saved' not in line:
                                path = line.split('->')[-1].strip()
                                if os.path.exists(path):
                                    self.results["attachments"].append(path)
                    elif "no document" in attach_result.lower():
                        print(f"  Email {email_idx}: No document attachments")
                
                print(f"\n✅ Total attachments downloaded: {len(self.results['attachments'])}")
                
                # Step 3: Extract content from all attachments
                print("\n📄 Step 3: Extracting content from attachments...")
                
                for att_path in self.results["attachments"]:
                    filename = os.path.basename(att_path)
                    print(f"  Processing: {filename}")
                    
                    content = await self.attachment_tool.execute(
                        action="parse",
                        file_path=att_path,
                        max_length=10000
                    )
                    
                    if content and "Error" not in content:
                        self.results["extracted_content"][filename] = content
                        print(f"    ✅ Extracted {len(content)} chars")
                    else:
                        print(f"    ❌ Failed to extract content")
                
                print(f"\n✅ Content extracted from {len(self.results['extracted_content'])} files")
                
                # Step 4: Generate report using LLM
                if generate_report and self.results["extracted_content"]:
                    print("\n🤖 Step 4: Generating comprehensive report with LLM...")
                    await self._generate_report()
                else:
                    print("\n⏭️ Step 4: Skipped (no content to analyze)")
            else:
                print("\n❌ No emails found")
        else:
            print("\n❌ No emails found matching criteria")
        
        # Print summary
        self._print_summary()
        
        return self.results
    
    async def _generate_report(self):
        """Generate a comprehensive report using local LLM."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            print("❌ openai package not installed")
            return
        
        client = AsyncOpenAI(
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["api_base"]
        )
        
        # Build content summary
        content_summary = []
        for filename, content in self.results["extracted_content"].items():
            content_summary.append(f"--- {filename} ---\n{content[:2000]}\n")
        
        combined_content = "\n\n".join(content_summary)
        
        prompt = f"""You are a professional email analyst. Please analyze the following email attachments and create a comprehensive summary report.

Attachments analyzed: {len(self.results['extracted_content'])}
Email folder: inbox/reporting
Date: {datetime.now().strftime('%Y-%m-%d')}

CONTENT:
{combined_content}

Please create a structured report with:
1. **Overview**: Brief summary of what these attachments contain
2. **Key Findings**: Main points from each attachment (bullet list)
3. **Action Items**: Any tasks or follow-ups needed (bullet list)
4. **Recommendations**: Suggestions based on the content

Be concise but comprehensive.
"""
        
        try:
            print(f"  Calling LLM: {LLM_CONFIG['model']}...")
            response = await client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[
                    {"role": "system", "content": "You are a professional email analyst assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10000,
                temperature=0.7
            )
            
            self.results["report"] = response.choices[0].message.content
            print("  ✅ Report generated!")
            
        except Exception as e:
            print(f"  ❌ LLM Error: {e}")
            self.results["report"] = f"[Error generating report: {e}]"
    
    def _print_summary(self):
        """Print final summary."""
        print("\n" + "="*70)
        print("WORKFLOW SUMMARY")
        print("="*70)
        
        print(f"\n📧 Emails found: {len(self.results['emails_found'])}")
        print(f"📎 Attachments downloaded: {len(self.results['attachments'])}")
        print(f"📄 Content extracted: {len(self.results['extracted_content'])}")
        
        if self.results["attachments"]:
            print("\n📁 Downloaded files:")
            for f in self.results["attachments"]:
                print(f"   - {os.path.basename(f)}")
        
        if self.results["report"]:
            print("\n" + "="*70)
            print("📊 COMPREHENSIVE REPORT")
            print("="*70)
            print(self.results["report"])
        
        print("\n" + "="*70)
        print("✅ WORKFLOW COMPLETE")
        print("="*70)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Full email analysis workflow")
    parser.add_argument("--folder", default="inbox/reporting", help="Email folder to analyze")
    parser.add_argument("--no-report", action="store_true", help="Skip LLM report generation")
    parser.add_argument("--api-base", default=LLM_CONFIG["api_base"], help="LLM API base URL")
    parser.add_argument("--model", default=LLM_CONFIG["model"], help="LLM model name")
    
    args = parser.parse_args()
    
    # Update config
    LLM_CONFIG["api_base"] = args.api_base
    LLM_CONFIG["model"] = args.model
    
    tester = FullWorkflowTester()
    await tester.run(folder=args.folder, generate_report=not args.no_report)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
