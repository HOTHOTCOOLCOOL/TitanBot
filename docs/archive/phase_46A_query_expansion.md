# Phase 46A: Fallback-Driven Query Expansion (KG 末端语义扩展)

**完成日期**：2026-04-12  
**灵感来源**：BubbleRAG §3.2 Semantic Anchor Grouping（降维实现）  
**决策文档**：ADR-47

## 技术拆解

### 核心变更：`knowledge_workflow.py` — `query_expansion_fallback()`

新增 `async` 方法，作为 `match_knowledge()` 三层回退链（Exact → Substring → Hybrid）的最末端扩展层。

**触发条件**：仅当同步的 `match_knowledge()` 返回 `None` 时，由 `loop.py` 显式调用。

**设计决策**：
- 保持 `match_knowledge()` 同步签名不变，不影响现有 20+ 调用/测试点
- 新方法为 `async`，因为需要调用 LLM `provider.chat()`
- 复用 `workflow_models.key_extraction` 轻量模型路由，不引入新配置项
- 3s `asyncio.wait_for()` 熔断保护，超时静默返回 `None`
- 匹配结果标记 `_match_method = "query_expansion"` 供可观测性链路使用

**流程**：
1. 守卫检查 `self.provider` 和 `self.knowledge_store` 非空
2. 构造精简 prompt，要求推断 1-3 个备选概念词（JSON array）
3. 解析响应，限制最多 3 个扩展词
4. 对每个扩展词调用 `hybrid_retrieve()`，取最高分结果
5. 超过阈值则返回匹配，否则返回 `None`

### 调用点：`loop.py` — `_core_process_message()`

在第 1707 行 `match = kw.match_knowledge(task_key)` 后新增 3 行：

```python
if match is None and task_key:
    match = await kw.query_expansion_fallback(task_key)
```

仅在三层全部 Miss 后触发，P50 延迟完全不受影响。

### 测试覆盖

新增 `tests/test_query_expansion.py`（5 个用例）：
- 隐式概念匹配成功（含 mock vector memory）
- 3s 超时熔断返回 None
- provider=None 静默退出
- 扩展词无匹配返回 None
- `_match_method` 标记验证

回归验证：56/56 existing knowledge workflow + hybrid retrieval tests passed。

## 量化预期

- P50 延迟：零影响（仅在全部 Miss 时触发）
- P95 长尾：增加约 1.5s（LLM 调用 + 重新检索）
- 挽回率：预期约 30% 因隐式概念未命中的语义失败
