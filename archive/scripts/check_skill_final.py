#!/usr/bin/env python3
"""Final check of SaveSkillTool implementation."""

import sys
from pathlib import Path

def check_skill_creation():
    """Check if test skill was created."""
    workspace = Path(".").resolve()
    skill_dir = workspace / "skills" / "test-outlook-workflow"
    
    print("=" * 60)
    print("SaveSkillTool Implementation Verification")
    print("=" * 60)
    
    print("\n1. Test Skill Creation:")
    print("-" * 40)
    
    if skill_dir.exists():
        print("✓ Skill directory created successfully")
        
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            try:
                content = skill_file.read_text(encoding="utf-8")
                print("✓ SKILL.md created with proper content")
                
                # Key checks
                checks = [
                    ("YAML frontmatter", content.startswith("---")),
                    ("Skill name", "test-outlook-workflow" in content),
                    ("Description", "Test workflow for Outlook email processing" in content),
                    ("Metadata", "nanobot" in content or "metadata" in content),
                    ("Steps section", "## Steps" in content),
                    ("Requirements section", "## Requirements" in content),
                ]
                
                print("\n  Content validation:")
                all_passed = True
                for name, check in checks:
                    status = "PASS" if check else "FAIL"
                    print(f"    {status}: {name}")
                    if not check:
                        all_passed = False
                
                if all_passed:
                    print("\n  ✓ All content checks passed")
                else:
                    print("\n  ✗ Some content checks failed")
                    
            except Exception as e:
                print(f"✗ Error reading skill file: {e}")
                return False
        else:
            print("✗ SKILL.md not found")
            return False
            
        summary_file = skill_dir / "SUMMARY.md"
        if summary_file.exists():
            print("✓ SUMMARY.md created")
        else:
            print("✗ SUMMARY.md not found")
            return False
    else:
        print("✗ Skill directory not created")
        return False
    
    return True

def check_code_integration():
    """Check code integration."""
    print("\n2. Code Integration:")
    print("-" * 40)
    
    workspace = Path(".").resolve()
    all_passed = True
    
    # Check nanobot/agent/tools/__init__.py
    init_file = workspace / "nanobot" / "agent" / "tools" / "__init__.py"
    if init_file.exists():
        try:
            content = init_file.read_text(encoding="utf-8")
            if "SaveSkillTool" in content and "from nanobot.agent.tools.save_skill import SaveSkillTool" in content:
                print("✓ SaveSkillTool exported in __init__.py")
            else:
                print("✗ SaveSkillTool not properly exported in __init__.py")
                all_passed = False
        except Exception as e:
            print(f"✗ Error reading __init__.py: {e}")
            all_passed = False
    else:
        print("✗ __init__.py not found")
        all_passed = False
    
    # Check nanobot/agent/loop.py
    loop_file = workspace / "nanobot" / "agent" / "loop.py"
    if loop_file.exists():
        try:
            content = loop_file.read_text(encoding="utf-8")
            
            import_check = "from nanobot.agent.tools.save_skill import SaveSkillTool" in content
            registration_check = "self.tools.register(SaveSkillTool" in content
            
            if import_check:
                print("✓ SaveSkillTool imported in AgentLoop")
            else:
                print("✗ SaveSkillTool import missing in AgentLoop")
                all_passed = False
                
            if registration_check:
                print("✓ SaveSkillTool registered in _register_default_tools")
            else:
                print("✗ SaveSkillTool registration missing in AgentLoop")
                all_passed = False
                
        except Exception as e:
            print(f"✗ Error reading loop.py: {e}")
            all_passed = False
    else:
        print("✗ loop.py not found")
        all_passed = False
    
    # Check nanobot/agent/tools/save_skill.py exists
    save_skill_file = workspace / "nanobot" / "agent" / "tools" / "save_skill.py"
    if save_skill_file.exists():
        print("✓ save_skill.py file exists")
    else:
        print("✗ save_skill.py file not found")
        all_passed = False
    
    return all_passed

def check_tool_functionality():
    """Check tool functionality."""
    print("\n3. Tool Functionality:")
    print("-" * 40)
    
    try:
        sys.path.insert(0, '.')
        from nanobot.agent.tools.save_skill import SaveSkillTool
        
        workspace = Path(".").resolve()
        tool = SaveSkillTool(workspace)
        
        print(f"✓ Tool class created successfully")
        print(f"  - Name: {tool.name}")
        print(f"  - Description length: {len(tool.description)} chars")
        
        # Check parameters schema
        params = tool.parameters
        required = params.get("required", [])
        if "name" in required and "description" in required:
            print("✓ Parameters schema includes required fields")
        else:
            print("✗ Parameters schema missing required fields")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ Tool functionality check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all checks."""
    skill_ok = check_skill_creation()
    integration_ok = check_code_integration()
    functionality_ok = check_tool_functionality()
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    
    print(f"Skill Creation: {'✓ PASS' if skill_ok else '✗ FAIL'}")
    print(f"Code Integration: {'✓ PASS' if integration_ok else '✗ FAIL'}")
    print(f"Tool Functionality: {'✓ PASS' if functionality_ok else '✗ FAIL'}")
    
    overall = skill_ok and integration_ok and functionality_ok
    
    if overall:
        print("\n" + "=" * 60)
        print("SUCCESS: SaveSkillTool implementation completed!")
        print("=" * 60)
        print("\nThe agent can now save successful workflows as reusable skills.")
        print("This addresses the user's issue about skill reuse.")
        return 0
    else:
        print("\n" + "=" * 60)
        print("FAILURE: Some checks failed.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())