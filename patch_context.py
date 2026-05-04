import sys

with open('nanobot/agent/context.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\\n\\n{always_content}")'''

replacement1 = '''        # Skills - progressive loading
        # 1. Always-loaded skills and explicitly requested skills
        target_skills = self.skills.get_always_skills()
        if skill_names:
            for s in skill_names:
                if s not in target_skills:
                    target_skills.append(s)
                    
        # P1: Resolve and inject prerequisites
        final_skills = []
        for s in target_skills:
            deps = self.skills.resolve_dependencies(s)
            for dep in deps:
                if dep not in final_skills:
                    from loguru import logger
                    logger.debug(f"Injected prerequisite skill '{dep}' for target skill '{s}'")
                    final_skills.append(dep)
            if s not in final_skills:
                final_skills.append(s)

        if final_skills:
            always_content = self.skills.load_skills_for_context(final_skills)
            if always_content:
                parts.append(f"# Active Skills\\n\\n{always_content}")'''

target2 = '''NEVER just describe what you would do - actually call the tools and DO it!

Always be helpful, accurate, and concise. When using tools, think step by step: what you know, what you need, and why you chose this tool.
When remembering something important, use the `memory` tool with action='store'. Background processes will later distill it into preferences.json.'''

replacement2 = '''NEVER just describe what you would do - actually call the tools and DO it!

**P0 Pseudo-Plan Guided Retrieval**: Before you call ANY tool for a complex task, you MUST emit a `<think>` block containing a numbered or bulleted list representing your pseudo-plan. You must outline the steps you intend to take.

Always be helpful, accurate, and concise. When using tools, think step by step: what you know, what you need, and why you chose this tool.
When remembering something important, use the `memory` tool with action='store'. Background processes will later distill it into preferences.json.'''

target1_rn = target1.replace('\n', '\r\n')
replacement1_rn = replacement1.replace('\n', '\r\n')
target2_rn = target2.replace('\n', '\r\n')
replacement2_rn = replacement2.replace('\n', '\r\n')

if target1_rn in content:
    content = content.replace(target1_rn, replacement1_rn)
elif target1 in content:
    content = content.replace(target1, replacement1)
else:
    print("Could not find target1")
    sys.exit(1)

if target2_rn in content:
    content = content.replace(target2_rn, replacement2_rn)
elif target2 in content:
    content = content.replace(target2, replacement2)
else:
    print("Could not find target2")
    sys.exit(1)

with open('nanobot/agent/context.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done.')
