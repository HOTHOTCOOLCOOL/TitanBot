# 🧪 Manual Test Plan — Part 3: Memory & Knowledge

> **范围**: Memory / Vector Store / Memory Manager / Knowledge / KG / Reflection / Experience / Hybrid Retrieval / Outcome / Task Knowledge
> **预计耗时**: 4-6 小时

---

## 21. Memory Store (`agent/memory.py`)

### T21.1 — MEMORY.md 读写
| 项 | 内容 |
|---|---|
| **步骤** | 通过 Agent "记住我喜欢咖啡"，检查 `memory/MEMORY.md` |
| **预期** | 文件中新增该信息 |

### T21.2 — Daily Log 写入
| 项 | 内容 |
|---|---|
| **步骤** | 正常对话一轮后，检查 `memory/YYYY-MM-DD.md` |
| **预期** | 当日日志文件存在且有内容 |

### T21.3 — Preferences 持久化
| 项 | 内容 |
|---|---|
| **步骤** | 通过 `/api/preferences` 或 Agent 行为设置偏好 |
| **预期** | `memory/preferences.json` 有对应内容 |

---

## 22. Vector Store (`agent/vector_store.py`)

### T22.1 — Embedding 存储与检索
| 项 | 内容 |
|---|---|
| **前置** | BAAI/bge-m3 模型（或自定义 embedding_model）可用 |
| **步骤** | 存储一条知识 "TitanBot 是一个 AI Agent 框架"，再搜索 "AI Agent" |
| **预期** | 搜索结果中包含刚存储的条目，相似度分数 > 0.5 |

### T22.2 — 自定义 Embedding 模型路径
| 项 | 内容 |
|---|---|
| **步骤** | 配置 `agents.defaults.embedding_model` 为本地模型路径 |
| **预期** | Vector store 使用指定模型，不下载默认模型 |

### T22.3 — Knowledge Completion (P29-4)
| 项 | 内容 |
|---|---|
| **步骤** | `VectorMemory.search_with_completion` 搜索后缺失验证 |
| **预期** | 检索结果不足时触发补充召回 |

---

## 23. Memory Manager (`agent/memory_manager.py`)

### T23.1 — 自动 Consolidation
| 项 | 内容 |
|---|---|
| **步骤** | 在一个 session 中达到 consolidation 阈值的消息数 |
| **预期** | 自动触发 consolidation，生成摘要写入 memory |

### T23.2 — Deep Consolidation
| 项 | 内容 |
|---|---|
| **步骤** | 发送 `/deep_consolidate` |
| **预期** | 后台任务执行，合并多日 daily logs 为高质量总结 |

### T23.3 — Session Summary 生成
| 项 | 内容 |
|---|---|
| **步骤** | `/new` 后检查 memory 目录 |
| **预期** | 之前 session 的摘要被保存 |

---

## 24. Knowledge Workflow (`agent/knowledge_workflow.py`)

### T24.1 — 知识存储 (学习流程)
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 save_experience 或 task_memory 存储知识 |
| **预期** | 知识条目出现在知识库中 |

### T24.2 — 知识匹配
| 项 | 内容 |
|---|---|
| **步骤** | 存储一条知识后，发送相关问题 |
| **预期** | `match_experience` 返回匹配的知识，注入 system prompt |

### T24.3 — 知识去重
| 项 | 内容 |
|---|---|
| **步骤** | 尝试存储两条几乎相同的知识 |
| **预期** | 知识判官 (`knowledge_judge.py`) 拦截并合并 |

### T24.4 — 知识版本化
| 项 | 内容 |
|---|---|
| **步骤** | 更新同一个知识条目两次 |
| **预期** | 版本号递增，旧版本可追溯 |

### T24.5 — 知识分解 (Decomposition)
| 项 | 内容 |
|---|---|
| **步骤** | 存储一条复合知识（含多个子事实） |
| **预期** | 知识被分解为多个原子条目 |

### T24.6 — Experience 阈值问题 (已知隐患)
| 项 | 内容 |
|---|---|
| **步骤** | 查看 `match_experience` 的相似度阈值 |
| **验证** | 确认阈值是否仍偏低（progress_report 提到 0.53 太低，需 ≥ 0.65） |
| **预期** | ⚠️ **这是一个已知 bug**，如果阈值仍 < 0.65 则记录 |

---

## 25. Knowledge Graph (`agent/knowledge_graph.py`)

### T25.1 — Triple 存储
| 项 | 内容 |
|---|---|
| **步骤** | 触发知识提取流程（对话中涉及实体关系） |
| **预期** | `memory/graph.json` 中新增 triple |

### T25.2 — Bridging Facts (P29-3)
| 项 | 内容 |
|---|---|
| **步骤** | 检查 `KnowledgeGraph.generate_bridging_facts` |
| **预期** | 从现有 triples 可推导多跳关联事实 |

### T25.3 — Entity Summary
| 项 | 内容 |
|---|---|
| **步骤** | 查看 graph.json 中实体是否有 summary 字段 |
| **预期** | 高频实体有自动生成的描述摘要 |

### T25.4 — Dashboard API 读取
| 项 | 内容 |
|---|---|
| **步骤** | `GET /api/knowledge_graph` |
| **预期** | 返回 triples 列表和 count |

---

## 26. Reflection Store (`agent/reflection.py`)

### T26.1 — 反思存储
| 项 | 内容 |
|---|---|
| **步骤** | Agent 任务失败后，检查 `memory/reflections.json` |
| **预期** | 新增反思条目：trigger, failure_reason, corrective_action |

### T26.2 — 反思注入 (L0)
| 项 | 内容 |
|---|---|
| **步骤** | 发送与之前失败类似的请求 |
| **预期** | System prompt 中注入 "⚠️ Avoid Past Mistakes" 部分 |

### T26.3 — Dashboard 读取反思
| 项 | 内容 |
|---|---|
| **步骤** | `GET /api/reflections` |
| **预期** | 返回反思列表和 count |

---

## 27. Experience Bank

### T27.1 — 手动保存经验
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 `save_experience` 工具 |
| **预期** | Experience bank 新增一条 tactical prompt |

### T27.2 — 经验匹配注入
| 项 | 内容 |
|---|---|
| **步骤** | 发送与经验 trigger 匹配的请求 |
| **预期** | System prompt 出现 "💡 Helpful Experience" |

### T27.3 — 自动经验 (P29-5)
| 项 | 内容 |
|---|---|
| **步骤** | 触发 circuit breaker |
| **预期** | 自动生成 `error_recovery` 类型经验 |

---

## 28. Hybrid Retriever (`agent/hybrid_retriever.py`)

### T28.1 — 五层检索顺序
| 项 | 内容 |
|---|---|
| **步骤** | 开 debug 日志，发送一个知识库查询 |
| **预期** | 日志显示检索层级：精确匹配 → 子串 → Jieba → BM25 → Dense (如果配了) |

### T28.2 — 无结果兜底
| 项 | 内容 |
|---|---|
| **步骤** | 搜索一个完全不相关的查询 |
| **预期** | 空结果返回，不报错 |

---

## 29. Outcome Tracker (`agent/outcome_tracker.py`)

### T29.1 — 负面反馈检测 (P29-1 Directive Signal)
| 项 | 内容 |
|---|---|
| **步骤** | 用户回复 "不对" / "错了" 表示不满 |
| **预期** | outcome_tracker 检测到负面信号，触发 LLM 提取 actionable rule |

---

## 30. Task Knowledge (`agent/task_knowledge.py`)

### T30.1 — Task Memory 存储
| 项 | 内容 |
|---|---|
| **步骤** | Agent 调用 `task_memory` 工具存储任务状态 |
| **预期** | 任务知识被持久化到 workspace |

### T30.2 — 溯源字段 (P29-6)
| 项 | 内容 |
|---|---|
| **步骤** | 检查存入的知识条目是否有 `derived_from` 字段 |
| **预期** | 字段指向源知识条目，实现知识溯源 |

### T30.3 — Task Memory action CRUD
| 项 | 内容 |
|---|---|
| **步骤** | 通过 task_memory 工具分别执行 store / search / update 操作 |
| **预期** | 各操作返回正确结果 |
