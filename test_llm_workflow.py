#!/usr/bin/env python
"""
LLM-Driven Outlook Workflow Test

This script simulates how nanobot would handle an Outlook email analysis task:
1. The LLM receives a user request
2. The LLM decides which tools to call and in what order
3. Tool results are fed back to the LLM
4. The LLM continues until the task is complete

This is a simplified simulation of the nanobot agent loop.

Usage:
    python test_llm_workflow.py

Requirements:
    - Outlook application installed and running
    - Required packages: pywin32, PyPDF2, python-docx, pandas, openai
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool


class LLMWorkflowSimulator:
    """
    Simulates an LLM-driven workflow where the LLM decides
    which tools to call based on user requests.
    """
    
    def __init__(self, llm_config: dict = None):
        self.outlook_tool = OutlookTool()
        self.attachment_tool = AttachmentAnalyzerTool()
        self.llm_config = llm_config or {
            "api_base": "http://10.18.34.60:5888/v1",
            "model": "minimax-m2.5-mlx",
            "api_key": "none"
        }
        self.conversation_history = []
        self.tool_results = []
    
    async def call_llm(self, system_prompt: str, user_prompt: str) -> dict:
        """Call the LLM and get response."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            print("❌ openai package not installed")
            return {"error": "openai not installed"}
        
        client = AsyncOpenAI(
            api_key=self.llm_config["api_key"],
            base_url=self.llm_config["api_base"]
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Add conversation history
        messages.extend(self.conversation_history)
        
        # Add tool results if any
        if self.tool_results:
            tool_result_text = "\n\n".join([
                f"Tool: {r['tool']}\nResult: {r['result']}"
                for r in self.tool_results
            ])
            messages.append({"role": "assistant", "content": f"Here are the tool results from previous steps:\n{tool_result_text}"})
        
        try:
            response = await client.chat.completions.create(
                model=self.llm_config["model"],
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # Try to parse as JSON if it looks like tool calls
            return {"content": content, "raw": response}
            
        except Exception as e:
            return {"error": str(e)}
    
    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return the result."""
        print(f"\n🔧 Executing tool: {tool_name}")
        print(f"   Arguments: {json.dumps(arguments, indent=2)}")
        
        try:
            if tool_name == "outlook":
                result = await self.outlook_tool.execute(**arguments)
            elif tool_name == "attachment_analyzer":
                result = await self.attachment_tool.execute(**arguments)
            else:
                result = f"Unknown tool: {tool_name}"
            
            print(f"   Result: {result[:200]}..." if len(result) > 200 else f"   Result: {result}")
            
            # Store tool result
            self.tool_results.append({
                "tool": tool_name,
                "arguments": arguments,
                "result": result
            })
            
            return result
            
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            print(f"   Error: {error_msg}")
            return error_msg
    
    def build_system_prompt(self) -> str:
        """Build the system prompt for the LLM."""
        return """You are an AI assistant that helps with Outlook email tasks.

Available tools:
1. outlook - For interacting with Microsoft Outlook
   Actions:
   - find_emails: Search for emails with criteria (folder, subject_contains, from_email, received_after, received_before, has_attachments, max_results)
   - get_attachment: Download attachment from a found email (email_index, attachment_index)
   - send_email: Send an email (recipient, subject, body, attachment_paths)
   - list_folders: List all email folders

2. attachment_analyzer - For analyzing email attachments
   Actions:
   - parse: Extract text content from files (file_path, max_length)
   - get_info: Get file information (file_path)
   - list_supported: List supported file formats

IMPORTANT:
- After calling find_emails, use the email index from the results in get_attachment
- The email index refers to the position in the search results, not the folder
- Always check if the user wants analysis or just extraction

Workflow:
1. Find emails matching user criteria
2. Report found emails to user and ask which to analyze
3. Download the attachment
4. Extract content using attachment_analyzer
5. Provide analysis or ask if user wants to send the analysis via email
"""
    
    async def run_workflow(self, user_request: str, max_iterations: int = 10):
        """Run the LLM-driven workflow."""
        print("\n" + "="*60)
        print("LLM-DRIVEN OUTLOOK WORKFLOW")
        print("="*60)
        print(f"\n📝 User Request: {user_request}")
        
        system_prompt = self.build_system_prompt()
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            
            # Build user prompt with context
            context = f"""User request: {user_request}

Previous tool results:
{chr(10).join([f"- {r['tool']}: {r['result'][:100]}..." for r in self.tool_results]) if self.tool_results else "None yet"}

What tool would you like to call next? 
If you need more information from the user, ask them.
If the task is complete, say so and provide a summary.

Format your response as JSON:
{{"action": "call_tool" | "ask_user" | "complete", "tool": "tool_name", "arguments": {{...}}, "message": "optional message"}}
"""
            
            response = await self.call_llm(system_prompt, context)
            
            if "error" in response:
                print(f"❌ LLM Error: {response['error']}")
                break
            
            content = response.get("content", "")
            print(f"\n🤖 LLM Response: {content[:300]}...")
            
            # Try to parse the LLM response as JSON
            try:
                # Look for JSON in the response
                if "{" in content:
                    json_start = content.find("{")
                    json_end = content.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = content[json_start:json_end]
                        decision = json.loads(json_str)
                    else:
                        decision = {"action": "complete", "message": content}
                else:
                    decision = {"action": "complete", "message": content}
            except json.JSONDecodeError:
                # If not JSON, treat as completion
                decision = {"action": "complete", "message": content}
            
            action = decision.get("action", "complete")
            
            if action == "call_tool":
                tool = decision.get("tool", "")
                args = decision.get("arguments", {})
                
                if tool == "outlook" or tool == "attachment_analyzer":
                    # Handle nested action in arguments
                    if "action" in args:
                        result = await self.execute_tool(tool, args)
                    else:
                        result = await self.execute_tool(tool, args)
                else:
                    print(f"❌ Unknown tool: {tool}")
                
            elif action == "ask_user":
                print(f"\n❓ LLM asks: {decision.get('message', 'Do you want to continue?')}")
                # In a real agent, this would wait for user input
                # For simulation, we'll auto-continue
                print("   (Auto-continuing for simulation)")
                
            elif action == "complete":
                print(f"\n✅ Task Complete!")
                print(f"📊 Summary: {decision.get('message', content)}")
                break
            else:
                print(f"⚠️ Unknown action: {action}")
        
        if iteration >= max_iterations:
            print(f"\n⚠️ Reached maximum iterations ({max_iterations})")
        
        return self.tool_results


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test LLM-driven Outlook workflow")
    parser.add_argument("--request", 
                       default="请帮我查找收件箱中主题包含'Test'的邮件，下载附件并分析内容",
                       help="User request in Chinese or English")
    parser.add_argument("--api-base", default="http://10.18.34.60:5888/v1", help="LLM API base URL")
    parser.add_argument("--model", default="minimax-m2.5-mlx", help="LLM model name")
    parser.add_argument("--api-key", default="none", help="LLM API key")
    parser.add_argument("--iterations", type=int, default=10, help="Max iterations")
    
    args = parser.parse_args()
    
    llm_config = {
        "api_base": args.api_base,
        "model": args.model,
        "api_key": args.api_key
    }
    
    # Check if openai is installed
    try:
        import openai
    except ImportError:
        print("❌ openai package not installed")
        print("Please install: pip install openai")
        return 1
    
    simulator = LLMWorkflowSimulator(llm_config)
    await simulator.run_workflow(args.request, args.iterations)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
