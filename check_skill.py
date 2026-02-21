#!/usr/bin/env python3
"""Check if test skill was created."""

import sys
from pathlib import Path

# Check if test skill was created
workspace = Path(".").resolve()
skill_dir = workspace / "skills" / "test-outlook-workflow"

print(f"Checking skill directory: {skill_dir}")

if skill_dir.exists():
    print("✓ Skill directory exists")
    
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        print("✓ SKILL.md exists")
        content = skill_file.read_text(encoding="utf-8")
        print(f"\nSkill file preview (first 500 chars):")
        print("-" * 50)
        print(content[:500])
        print("-" * 50)
        
        # Check for key elements
        checks = [
            ("YAML frontmatter", content.startswith("---")),
            ("Skill name", "test-outlook-workflow" in content),
            ("Description", "Test workflow for Outlook email processing" in content),
            ("Metadata", "nanobot" in content or "metadata" in content),
            ("Steps section", "## Steps" in content),
        ]
        
        print("\nContent checks:")
        for name, check in checks:
            status = "✓" if check else "✗"
            print(f"  {status} {name}")
    else:
        print("✗ SKILL.md not found")
        
    summary_file = skill_dir / "SUMMARY.md"
    if summary_file.exists():
        print("✓ SUMMARY.md exists")
    else:
        print("✗ SUMMARY.md not found")
else:
    print("✗ Skill directory not found")
    
# Check nanobot/agent/tools/__init__.py
init_file = workspace / "nanobot" / "agent" / "tools" / "__init__.py"
if init_file.exists():
    content = init_file.read_text()
    if "SaveSkillTool" in content:
        print("\n✓ SaveSkillTool exported in __init__.py")
    else:
        print("\n✗ SaveSkillTool not exported in __init__.py")
        
# Check nanobot/agent/loop.py
loop_file = workspace / "nanobot" / "agent" / "loop.py"
if loop_file.exists():
    content = loop_file.read_text()
    import_check = "from nanobot.agent.tools.save_skill import SaveSkillTool" in content
    registration_check = "self.tools.register(SaveSkillTool" in content
    
    print(f"\nAgentLoop checks:")
    print(f"  {'✓' if import_check else '✗'} SaveSkillTool import")
    print(f"  {'✓' if registration_check else '✗'} SaveSkillTool registration")