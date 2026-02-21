#!/usr/bin/env python3
"""Test script to verify SaveSkillTool integration."""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, '.')

async def main():
    # Test 1: Import the tool
    print("Test 1: Import SaveSkillTool")
    try:
        from nanobot.agent.tools.save_skill import SaveSkillTool
        print("✓ SaveSkillTool imported successfully")
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return 1
    
    # Test 2: Create tool instance
    print("\nTest 2: Create tool instance")
    workspace = Path(".").resolve()
    try:
        tool = SaveSkillTool(workspace)
        print(f"✓ Tool created: name={tool.name}")
        print(f"✓ Description: {tool.description[:100]}...")
    except Exception as e:
        print(f"✗ Tool creation failed: {e}")
        return 1
    
    # Test 3: Check tool parameters schema
    print("\nTest 3: Check parameters schema")
    try:
        params = tool.parameters
        print(f"✓ Parameters schema: {type(params)}")
        required = params.get("required", [])
        print(f"✓ Required params: {required}")
        if "name" in required and "description" in required:
            print("✓ Required params include name and description")
        else:
            print("✗ Missing required params")
            return 1
    except Exception as e:
        print(f"✗ Parameters check failed: {e}")
        return 1
    
    # Test 4: Test tool execution
    print("\nTest 4: Test tool execution")
    test_data = {
        "name": "test-outlook-workflow",
        "description": "Test workflow for Outlook email processing",
        "summary": "This is a test skill created to verify the save_skill tool works correctly.",
        "steps": [
            {
                "action": "Test step 1",
                "tools": ["read_file", "exec"],
                "notes": "Test note"
            }
        ],
        "requirements": {
            "bins": ["python"]
        },
        "tags": ["test", "email", "automation"]
    }
    
    try:
        result = await tool.execute(**test_data)
        print(f"✓ Tool execution successful")
        print(f"✓ Result preview: {result[:200]}...")
        
        # Check if skill was created
        skill_dir = workspace / "skills" / "test-outlook-workflow"
        if skill_dir.exists():
            print(f"✓ Skill directory created: {skill_dir}")
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                content = skill_file.read_text(encoding="utf-8")
                if "test-outlook-workflow" in content:
                    print("✓ Skill file contains correct name")
                if "Test workflow for Outlook" in content:
                    print("✓ Skill file contains description")
                print(f"✓ Skill file created successfully")
                
                # Check frontmatter
                if content.startswith("---"):
                    print("✓ Skill file has YAML frontmatter")
                    
                # Check nanobot metadata
                if "nanobot" in content or "metadata" in content:
                    print("✓ Skill file contains metadata")
            else:
                print("✗ SKILL.md file not found")
                return 1
        else:
            print("✗ Skill directory not created")
            return 1
            
    except Exception as e:
        print(f"✗ Tool execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Test 5: Check integration with AgentLoop
    print("\nTest 5: Check AgentLoop integration")
    try:
        from nanobot.agent.loop import AgentLoop
        print("✓ AgentLoop imported successfully")
        
        # Check if SaveSkillTool is in imports
        import inspect
        source = inspect.getsource(AgentLoop)
        if "from nanobot.agent.tools.save_skill import SaveSkillTool" in source:
            print("✓ SaveSkillTool import found in AgentLoop")
        else:
            print("✗ SaveSkillTool import not found in AgentLoop")
            
        if "self.tools.register(SaveSkillTool" in source:
            print("✓ SaveSkillTool registration found in _register_default_tools")
        else:
            print("✗ SaveSkillTool registration not found")
            
    except Exception as e:
        print(f"✗ AgentLoop check failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "="*50)
    print("All tests passed! ✓")
    print("="*50)
    return 0

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)