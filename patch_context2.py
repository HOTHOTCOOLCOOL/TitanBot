import sys

with open('nanobot/agent/context.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        # P1: Resolve and inject prerequisites
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

replacement = '''        # P1: Resolve and inject prerequisites
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
            budget = getattr(self, "_SKILL_INJECTION_BUDGET", 8000)
            injected_skills = []
            current_len = 0
            
            for skill_name in final_skills:
                # Approximate length based on load_skills_for_context output
                content_raw = self.skills.load_skill(skill_name)
                if content_raw:
                    stripped = self.skills._strip_frontmatter(content_raw)
                    block = f"### Skill: {skill_name}\\n\\n{stripped}"
                    block_len = len(block) + 4
                    
                    if current_len + block_len > budget:
                        from loguru import logger
                        logger.warning(f"Skill injection budget exceeded ({current_len} > {budget}). Dropping '{skill_name}' and subsequent skills.")
                        break
                        
                    injected_skills.append(skill_name)
                    current_len += block_len

            if injected_skills:
                always_content = self.skills.load_skills_for_context(injected_skills)
                if always_content:
                    parts.append(f"# Active Skills\\n\\n{always_content}")'''

target_rn = target.replace('\n', '\r\n')
replacement_rn = replacement.replace('\n', '\r\n')

if target_rn in content:
    content = content.replace(target_rn, replacement_rn)
elif target in content:
    content = content.replace(target, replacement)
else:
    print('Failed to find target block in context.py')
    sys.exit(1)

target2 = '''    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "KNOWLEDGE.md", "docs/rules/ARCHITECTURE.md"]
    _REASONING_TEMPLATE_MAX_CHARS = 1000'''

replacement2 = '''    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "KNOWLEDGE.md", "docs/rules/ARCHITECTURE.md"]
    _REASONING_TEMPLATE_MAX_CHARS = 1000
    _SKILL_INJECTION_BUDGET = 8000'''

target2_rn = target2.replace('\n', '\r\n')
replacement2_rn = replacement2.replace('\n', '\r\n')

if target2_rn in content:
    content = content.replace(target2_rn, replacement2_rn)
elif target2 in content:
    content = content.replace(target2, replacement2)
else:
    print('Failed to find target2 block in context.py')
    sys.exit(1)

with open('nanobot/agent/context.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched context.py')
