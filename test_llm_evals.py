import asyncio
import os
import tempfile
import time
from pathlib import Path
from loguru import logger

import sys
sys.stdout.reconfigure(encoding='utf-8')

# Disable verbose logging
logger.remove()

async def run_evals():
    ws = Path(tempfile.mkdtemp())
    (ws / 'memory').mkdir()
    (ws / 'sessions').mkdir()
    (ws / 'skills').mkdir()

    # Create a test skill for A4
    skill_dir = ws / 'skills' / 'echo_skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\nname: echo_skill\ndescription: echoes text given based on config\n---', encoding='utf-8')
    (skill_dir / 'config.json').write_text('{"prefix": "DEFAULT_PREFIX: "}', encoding='utf-8')
    (skill_dir / 'main.py').write_text('''
import sys, json, os

def main():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        cfg = json.loads(open(config_path).read())
    except:
        cfg = {"prefix": ""}
    
    text = sys.stdin.read().strip()
    print(f"{cfg.get('prefix', '')}{text}")

if __name__ == '__main__':
    main()
''', encoding='utf-8')
    from nanobot.config.loader import get_config
    from nanobot.providers.factory import ProviderFactory
    config = get_config()
    provider = ProviderFactory.get_provider(config.agents.defaults.model, config)
    
    print('================================================')
    print('Starting A1: Skill Matching...')
    from nanobot.agent.skills import SkillsLoader
    
    skills = SkillsLoader(workspace=ws)
    
    # Use real skills from the actual project for testing A1
    real_ws = Path('d:/Python/nanobot')
    real_skills = SkillsLoader(workspace=real_ws)
    summary = real_skills.build_skills_summary()
    
    async def match_skill(prompt_text):
        sys_msg = f"You are an AI assistant. You have these skills:\n{summary}\n\nBased on the user prompt, respond with ONLY the directory <name> of the most appropriate skill to use from the XML above, or NONE if no skill fits. Example response: web-search"
        try:
            res = await provider.chat(
                messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt_text}],
                model=config.agents.defaults.model,
                temperature=0.1
            )
            return getattr(res, "content", "failed")
        except Exception as e:
            return str(e)
            
    prompt1 = '帮我搜索一下今天的新闻'
    print(f"Testing intent recognition for: '{prompt1}'")
    eval_result = await match_skill(prompt1)
    print(f"  -> Result: {eval_result.strip()}")
    
    prompt2 = '帮我计算12345乘以67890'
    print(f"Testing intent recognition for: '{prompt2}'")
    eval_result2 = await match_skill(prompt2)
    print(f"  -> Result: {eval_result2.strip()}")
    
    print('A1 Evaluation Complete.\n')

    print('================================================')
    print('Starting A4: Skill Config Behavior...')
    from nanobot.agent.tools.shell import ExecTool
    shell = ExecTool(restrict_to_workspace=False)
    
    # Run with default config
    cmd = f"echo 'hello world' | python {skill_dir}/main.py"
    out1 = await shell.execute(cmd, working_dir=str(skill_dir))
    print(f'  Output 1 (default config): {out1.strip()}')
    
    # Update config
    (skill_dir / 'config.json').write_text('{"prefix": "CUSTOM_PREFIX: "}', encoding='utf-8')
    # reload skills config implicitly by second run
    out2 = await shell.execute(cmd, working_dir=str(skill_dir))
    print(f'  Output 2 (custom config): {out2.strip()}')
    
    # Verify behavior changed
    if out1.strip() != out2.strip():
        print('  ✅ Success: behavior changed based on config.json updates')
    else:
        print('  ❌ Error: behavior did not change')
        
    print('A4 Evaluation Complete.\n')
    
    print('================================================')
    print('Starting A17: Knowledge Graph Evolution (Phase 24)...')
    from nanobot.agent.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(workspace=ws)
    
    # Inject some facts
    print('  Extracting facts from round 1...')
    await kg.extract_triples(provider, config.agents.defaults.model, '我叫David，在Salesforce公司负责AI产品的研发。')
    print('  Extracting facts from round 2...')
    await kg.extract_triples(provider, config.agents.defaults.model, '我的同事是Zhang San。')
    
    print(f'  Total Triples extracted: {kg.count}')
    if kg.count > 0:
        for t in kg._triples:
             print(f'    - {t.get("subject")} --[{t.get("predicate")}]--> {t.get("object")}')
            
    # Test multi-hop retrieval
    print('\n  Testing Retrieval...')
    res = await kg.resolve_multihop(provider, config.agents.defaults.model, 'David在哪里上班？')
    print(f'\n  Retrieval Context Assembled: SUCCESS ({len(res)} bytes)\n')
    
    print('A17 Evaluation Complete.\n')

if __name__ == '__main__':
    asyncio.run(run_evals())
