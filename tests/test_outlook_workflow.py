#!/usr/bin/env python
"""
Outlook Workflow Test Script

This script tests the Outlook email processing workflow step by step:
1. Find emails in a specific folder containing specific text
2. Download ALL email attachments and save to a specific directory
3. Extract email attachment content from ALL attachments
4. Use local LLM to analyze all email attachments

Usage:
    python test_outlook_workflow.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool
from PyPDF2 import PdfReader

class OutlookWorkflowTester:
    """Test harness for Outlook email workflow."""
    
    def __init__(self):
        self.outlook_tool = OutlookTool()
        self.attachment_tool = AttachmentAnalyzerTool()
        self.test_results = []
        self.saved_files = []
    
    def log(self, message, success=True):
        """Log test message."""
        status = "✅" if success else "❌"
        print(f"{status} {message}")
        self.test_results.append((message, success))
    
    async def test_step1_find_emails(self, folder="inbox", subject_keyword=None):
        """Step 1: Find emails in a specific folder containing specific text."""
        print("\n" + "="*60)
        print("STEP 1: Find Emails")
        print("="*60)
        
        criteria = {
            "folder": folder,
            "has_attachments": True,
            "max_results": 5
        }
        
        if subject_keyword:
            criteria["subject_contains"] = subject_keyword
        
        print(f"Searching in folder: {folder}")
        if subject_keyword:
            print(f"Subject keyword: {subject_keyword}")
        
        try:
            result = await self.outlook_tool.execute(action="find_emails", criteria=criteria)
            print(f"\nResult:\n{result}")
            
            if "Found" in result and "email(s)" in result:
                self.log("Step 1: Find emails - SUCCESS", True)
                return True
            else:
                self.log(f"Step 1: Find emails - No emails found or error", False)
                return False
        except Exception as e:
            self.log(f"Step 1: Find emails - ERROR: {e}", False)
            return False
    
    async def test_step2_download_all_attachments(self, email_index=0, save_dir=None):
        """Step 2: Download ALL email attachments."""
        print("\n" + "="*60)
        print("STEP 2: Download All Attachments")
        print("="*60)
        
        if save_dir is None:
            save_dir = tempfile.gettempdir()
        
        print(f"Attempting to download ALL attachments from email {email_index}")
        print(f"Save directory: {save_dir}")
        
        try:
            result = await self.outlook_tool.execute(
                action="get_all_attachments",
                email_index=email_index,
                save_directory=save_dir
            )
            print(f"\nResult:\n{result}")
            
            # Parse result to get saved file paths
            if "Saved" in result and "attachment(s)" in result:
                self.saved_files = []
                for line in result.split('\n'):
                    if '->' in line and 'Saved' not in line and 'Errors' not in line:
                        path = line.split('->')[-1].strip()
                        if os.path.exists(path):
                            self.saved_files.append(path)
                
                self.log(f"Step 2: Download all attachments - SUCCESS ({len(self.saved_files)} files)", True)
                return True
            else:
                self.log(f"Step 2: Download all attachments - FAILED: {result}", False)
                return False
        except Exception as e:
            self.log(f"Step 2: Download all attachments - ERROR: {e}", False)
            return None
    
    async def test_step3_extract_all_content(self):
        """Step 3: Extract content from ALL email attachments."""
        print("\n" + "="*60)
        print("STEP 3: Extract Content from ALL Attachments")
        print("="*60)
        
        if not self.saved_files:
            self.log("Step 3: No files to extract", False)
            return {}
        
        extracted_contents = {}
        
        for file_path in self.saved_files:
            if not os.path.exists(file_path):
                print(f"  Skipping {file_path} - file not found")
                continue
            
            print(f"\n--- Extracting: {os.path.basename(file_path)} ---")
            print(f"File size: {os.path.getsize(file_path)} bytes")
            
            try:
                result = await self.attachment_tool.execute(
                    action="parse",
                    file_path=file_path,
                    max_length=10000
                )
                
                print(f"Extracted content (first 300 chars):")
                print("-" * 40)
                print(result[:300] if len(result) > 300 else result)
                print("-" * 40)
                
                if result and "Error" not in result:
                    extracted_contents[file_path] = result
                else:
                    extracted_contents[file_path] = f"[Extraction failed: {result}]"
                    
            except Exception as e:
                print(f"Error: {e}")
                extracted_contents[file_path] = f"[Error: {e}]"
        
        if extracted_contents:
            self.log(f"Step 3: Extract all content - SUCCESS ({len(extracted_contents)} files)", True)
        else:
            self.log("Step 3: Extract all content - FAILED", False)
        
        return extracted_contents
    
    async def test_step4_llm_analysis(self, contents, llm_config=None):
        """Step 4: Use local LLM to analyze ALL email attachments."""
        print("\n" + "="*60)
        print("STEP 4: LLM Analysis for ALL Attachments")
        print("="*60)
        
        if llm_config is None:
            llm_config = {
                "api_base": "http://10.18.34.60:5888/v1",
                "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
                "api_key": "none"
            }
        
        if not contents:
            self.log("Step 4: No content to analyze", False)
            return
        
        print(f"LLM Config:")
        print(f"  API Base: {llm_config['api_base']}")
        print(f"  Model: {llm_config['model']}")
        
        try:
            from openai import AsyncOpenAI
        except ImportError:
            self.log("Step 4: openai package not installed", False)
            print("Install with: pip install openai")
            return
        
        client = AsyncOpenAI(
            api_key=llm_config["api_key"],
            base_url=llm_config["api_base"]
        )
        
        analysis_results = {}
        
        for file_path, content in contents.items():
            filename = os.path.basename(file_path)
            print(f"\n--- Analyzing: {filename} ---")
            
            analysis_content = content[:3000] if len(content) > 3000 else content
            
            prompt = f"""Please analyze this email attachment and provide a brief summary:

Filename: {filename}

Content:
{analysis_content}

Please provide:
1. A brief summary (2-3 sentences)
2. Key points (bullet list)
"""
            
            try:
                response = await client.chat.completions.create(
                    model=llm_config["model"],
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that analyzes email attachments."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=10000,
                    temperature=0.7
                )
                
                result = response.choices[0].message.content
                print(f"\nAnalysis for {filename}:")
                print("-" * 40)
                print(result)
                print("-" * 40)
                
                analysis_results[filename] = result
                
            except Exception as e:
                print(f"Error analyzing {filename}: {e}")
                analysis_results[filename] = f"[Error: {e}]"
        
        if analysis_results:
            self.log(f"Step 4: LLM Analysis - SUCCESS ({len(analysis_results)} files analyzed)", True)
        else:
            self.log("Step 4: LLM Analysis - FAILED", False)
        
        return analysis_results
    
    async def run_full_test(self, folder="inbox", subject_keyword=None, llm_config=None):
        """Run the full workflow test."""
        print("\n" + "="*60)
        print("OUTLOOK WORKFLOW TEST - All Attachments")
        print("="*60)
        
        # Step 1: Find emails
        step1_success = await self.test_step1_find_emails(folder, subject_keyword)
        if not step1_success:
            print("\n⚠️ Step 1 failed")
            self.print_summary()
            return False
        
        # Step 2: Download ALL attachments
        step2_success = await self.test_step2_download_all_attachments()
        if not step2_success or not self.saved_files:
            print("\n⚠️ Step 2 failed")
            self.print_summary()
            return False
        
        # Step 3: Extract content from ALL saved files
        contents = await self.test_step3_extract_all_content()
        if not contents:
            print("\n⚠️ Step 3 failed")
            self.print_summary()
            return False
        
        # Step 4: LLM Analysis for ALL attachments
        await self.test_step4_llm_analysis(contents, llm_config)
        
        self.print_summary()
        return all([r[1] for r in self.test_results])
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, success in self.test_results if success)
        total = len(self.test_results)
        
        for message, success in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status}: {message}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if self.saved_files:
            print(f"\nSaved files ({len(self.saved_files)}):")
            for f in self.saved_files:
                print(f"  - {f}")
        
        if passed == total:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️ {total - passed} test(s) failed")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Outlook email workflow")
    parser.add_argument("--folder", default="inbox", help="Email folder to search")
    parser.add_argument("--keyword", default="Weekly Summary Report - Week 6 2026", help="Subject keyword to search for")
    parser.add_argument("--api-base", default="http://10.18.34.60:5888/v1", help="LLM API base URL")
    parser.add_argument("--model", default="nvidia.nvidia-nemotron-3-super-120b-a12b", help="LLM model name")
    parser.add_argument("--api-key", default="none", help="LLM API key")
    
    args = parser.parse_args()
    
    llm_config = {
        "api_base": args.api_base,
        "model": args.model,
        "api_key": args.api_key
    }
    
    tester = OutlookWorkflowTester()
    success = await tester.run_full_test(
        folder=args.folder,
        subject_keyword=args.keyword,
        llm_config=llm_config
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
