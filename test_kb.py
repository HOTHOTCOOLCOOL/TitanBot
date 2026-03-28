import sys
from pathlib import Path
sys.path.append(r'd:\Python\nanobot')
from nanobot.agent.vector_store import VectorMemory
from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.agent.hybrid_retriever import hybrid_retrieve

workspace = Path(r'C:\Users\davidliu\.nanobot\workspace')
vm = VectorMemory(workspace)
vm.full_reindex()
print('Total docs:', vm.stats()['count'])

results = vm.search('去携程搜索2026年4月11日上海飞汉堡经济舱同等行程时长下最便宜的航空公司。', top_k=5, source_filter='knowledge')
print('Vector search results:')
for r in results:
    print(r['score'], r['metadata'])

ks = TaskKnowledgeStore(workspace)
tasks = ks.get_all_tasks()

match, score = hybrid_retrieve(
    query='去携程搜索2026年4月11日上海飞汉堡经济舱同等行程时长下最便宜的航空公司。',
    candidates=tasks,
    vector_memory=vm,
)
print('Hybrid match:', match.get('key') if match else None, 'score:', score)
