# Progress Report
 
 - [x] Phase 44: Cron重试引擎加固与SSRS幻觉防线测试验证通过。
 - [x] Phase 45: 动态沙箱能力标签系统构建完成；(45A) 基础设施、(45B) L1高危Shell拦截规则落地并验证通过。
 - [x] Phase 45C: ExecutionPolicy and Coordinator security injection completed and verified against architectural pitfalls.
 - [x] Phase 44 & Phase 45 全量回归测试与操作演练全部通过 (60/60 test cases passed, bug-hitl & buw bugs fixed).
 - [x] Phase 38: Manager-SubAgent 架构全量人工测试用例验收通过。
 - [x] Phase 46: Fallback-Driven Query Expansion & Offline Experience Consolidator 架构级交叉验证完毕，修复 API 签名与 UI 展示遗漏。
 
 ## 📅 Next Steps / Backlog (后续计划)
 
 - [x] **Phase 38A: Manager Base Abstraction (技术债偿还)**
   - 统一 `SubagentManager` 与 `CoordinatorManager` 的底层接口，提取可配置特权的 `WorkerToolset`，强化 `/task` RPC 协议以支持异构模型配置与 Trace 上下文链路。
 - [x] **Phase 38B: Manager-SubAgent Orchestration (多模型协作)**
   - 将现有 Worker 架构升维为支持结果精炼、能力安全继承的 SubAgent 并发编排模式，利用主从多级 LLM 彻底解决复杂任务的上下文膨胀。
 - [ ] **Phase 36: Worker Security v2 (Docker seccomp)** *(P3)*
   - (原 OS Sandbox) 仅在未来 Linux 生产环境部署时，补充基于 Docker seccomp 的轻量级防护。目前 Windows 开发环境无限期搁置。
 - [x] **Phase 37: Execution Trace Archive**
   - 已拆解并在此前阶段通过 L3 Experience Bank 提炼与独立 Trace Archive 落盘完结，彻底放弃引入 SQLite。
 - [x] **Phase 46A: Fallback-Driven Query Expansion (KG 末端语义扩展)** *(P0)*
   - `match_knowledge()` 三层全 Miss 后触发 LLM 推断隐式概念词，静默二次 `hybrid_retrieve()`，3s timeout 熔断保护，主路径 P50 零影响。
 - [x] **Phase 46B: Offline Experience Consolidator (离线经验整编器)** *(P1, ~2天)*
 - [x] **Phase 47: 论文分析架构决策与演进评级 (Paper Analysis & Architecture Audit)** *(P1)*
   - 完成了《SkillClaw》《BubbleRAG》等前沿 Agent 论文分析，并落地为 ADR-47 及后续的 46A/46B。
 - [x] **Phase 48: Dashboard 配置编辑器 (Config Editor UI)** *(P1)* 
   - 实现了基于乐观锁和脱敏合并机制的双模式配置编辑器，解决权限配置的不透明性。
  - [ ] **Phase 49: In-Flight Context Condensation (IFCC)** *(P1, ~1.5天)*
    - 来源: MemPO (arXiv 2603.00680v3)，借鉴 `<mem>` 标签信号，纯工程实现无需 RL 训练。
    - 核心: 模型步骤完成后输出 `<mem>结论</mem>`，写入 Message.milestone_summary；_trim_history() 截断时将有 Milestone 的消息降级为骨架而非丢弃，防止"遗忘循环"。
    - 安全: 解析器严格 role-gate，仅处理 role='assistant' 输出，阻断 Prompt Injection。
    - 详见 `docs/adr/ADR-49-ifcc-context-condensation.md`
 - [ ] **Phase 50: Knowledge Graph Wiki Export (KG-Wiki)** *(P2, ~4天)*
   - 来源: Karpathy LLM Wiki (2026)，借鉴 Wiki 可见性理念，不照搬其"Markdown 作为后端核心"设计。
   - 核心: `wiki_syncer.py` 旁路观测模式 — 基于 `graph.json.updated_at` 时间戳对比，纯代码将 L7 KG 实体投影为 Obsidian 兼容 Markdown Vault（YAML Frontmatter 解决 Alias 映射，`sanitize_title` 防 Windows 非法字符）。
   - 触发: CLI (`nanobot wiki sync`)、Dashboard Sync 按钮、Cron 旁路任务 — 三者均不经 AgentLoop，零 LLM 调用，零主路径影响。
   - 开关: `config.features.wiki_export = false`（默认关闭，显式 opt-in）。
   - 详见 `docs/adr/ADR-50-kg-wiki-export.md`
