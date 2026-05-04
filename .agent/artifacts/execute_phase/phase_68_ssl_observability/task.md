# Task

- [ ] T01 补红测：`test_ssl_normalizer.py` 覆盖 composite hashing、normalizer fail-closed logic、ContextBuilder 压缩注入。
- [ ] T02 实现 `nanobot/agent/ssl_normalizer.py` 并接入 `SkillsLoader` 的注册/加载流程（包含 hash 计算）。
- [ ] T03 修改 `nanobot/agent/skills.py` (load_skills_for_context) 以消费 `skill_ssl` 实体并实施 1000 chars 预算。
- [ ] T04 修改 `nanobot/agent/knowledge_graph.py`，在 `rebuild_entity_index` 逻辑中显式保护 `skill_ssl` 不被 reindex 抹掉，且必须完整保留其特有的 properties (hash, graph) 负载内容。
- [ ] T05 更新必要文档或契约。
