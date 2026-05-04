import sys

with open('tests/test_phase68_paper_integration.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_tests = '''    def test_dependency_ordering_in_payload(self, tmp_workspace, monkeypatch):
        # Override get_always_skills to prevent picking up actual workspace skills
        monkeypatch.setattr("nanobot.agent.skills.SkillsLoader.get_always_skills", lambda self: [])
        
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b")
        
        builder = ContextBuilder(workspace=tmp_workspace)
        prompt = builder.build_system_prompt(skill_names=["skill_a"])
        
        # Ensure both are present
        assert "### Skill: skill_b" in prompt
        assert "### Skill: skill_a" in prompt
        
        # Ensure prerequisite b is injected BEFORE target a
        idx_b = prompt.index("### Skill: skill_b")
        idx_a = prompt.index("### Skill: skill_a")
        assert idx_b < idx_a

    def test_injection_budget_constraint(self, tmp_workspace, monkeypatch):
        # Override get_always_skills
        monkeypatch.setattr("nanobot.agent.skills.SkillsLoader.get_always_skills", lambda self: [])
        
        # Create a chain of skills
        _create_skill(tmp_workspace, "skill_a", deps=["skill_b"])
        _create_skill(tmp_workspace, "skill_b", deps=["skill_c"])
        _create_skill(tmp_workspace, "skill_c")
        
        builder = ContextBuilder(workspace=tmp_workspace)
        # Force a tiny budget that only fits skill_c (and maybe one more)
        monkeypatch.setattr(builder, "_SKILL_INJECTION_BUDGET", 50) 
        
        prompt = builder.build_system_prompt(skill_names=["skill_a"])
        
        # skill_c should be present since it's the deepest dependency
        assert "### Skill: skill_c" in prompt
        # skill_a should be dropped because the budget is exhausted
        assert "### Skill: skill_a" not in prompt
'''

if "test_dependency_ordering_in_payload" not in content:
    content += new_tests

with open('tests/test_phase68_paper_integration.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched test file')
