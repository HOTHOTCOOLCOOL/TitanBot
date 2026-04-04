# Phase 39: 延迟优化与智能分层降级方案 (Final Version)

> 2026-04-04 经由 harness 混合模型碰撞论证产生的最终架构方案。

## 核心重构设计 (Addressing Failures)

### 1. L0 极白名单引擎 (Strict Whitelist Bypass)
**解决问题：** LLM 的 TTFT 刚性下限，以及单纯基于长度判断引发的指令截断（假阳性哑巴化）风险。
**实施路径：**
- 在 `loop.py` (`_execute_with_llm`) 顶部引入严苛的白名单正则校验，仅捕获完全不存在操作语义的闲聊，例如：`r"^(你好|在吗|早上好|hello|hi|测试|在不在)[！？\s~]*$"`。
- 一旦匹配成功，标注为 `intent = "chitchat_safe"`，完全跳过缓慢的 `rewrite_query_with_anchors` 语义改写网络请求。

### 2. 动态模型轮切与无损降级 (Dynamic Routing & Zero-Degradation Tooling)
**解决问题：** 粗暴剥离系统物理工具导致智能体完全致盲，且加载主模型自身仍无法解决长耗时。
**实施路径：**
- 针对 `chitchat_safe` 意图，**不再篡改和剔除** `session` 或者 `loop` 中的 `tools` 列表。
- 取而代之，通过配置读取一个微型模型（如 `gemini-3.0-flash` 或本地极速模型）。当回合触发白名单时，利用 `ProviderFactory` 动态生成或获取廉价微型通道，仅将**本回合**的 `target_model` 替换。既彻底瓦解载入延迟，又保留了系统万一需要跨越调用的“后备视力”。

### 3. 外置异步化与解耦池化防死锁 (Decoupled Pre-Fetching)
**解决问题：** 强行魔改 `ContextBuilder` 导致大面积兼容雪崩；暴力加锁卡死整个异步事件流。
**实施路径：**
- **非侵入式前置：** 在 `loop.py` 调用同步的 `build_messages` 之前，使用 `asyncio.get_running_loop().run_in_executor()` 或 `asyncio.to_thread()`，在独立线程中前置拉取 `vector_memory.search` 和 `knowledge_graph.get_entity_context`。
- **透明投递：** 拓展 `build_messages` 的能力，允许外部直接将获取到的文本结果以 `pre_fetched_rag` 和 `pre_fetched_kg` 等 Kwargs 传入，使其跳过内部计算。保留原方法的同步性，实现下游零感知。

### 4. 基于熵密度的自适应记忆提取 (Entropy-Based Knowledge Extraction)
**解决问题：** 一刀切阻止闲聊回合的记忆写入，可能漏掉用户在短句夹带的关键偏好数据。
**实施路径：**
- 取消粗暴的 `if intent != "chitchat_safe"` 拦截跳过行为，继续让所有状态流动至 `verification.post_reflect`。
- 在 `post_reflect` 的信息提取系统提示词中注入高压门槛约束：“*仅当内容携带高密度的信息熵（例如明确的个人偏好、业务逻辑设定）时才执行写入。绝对忽略日常闲聊、早午安问候或无逻辑价值的短句。*”
- 将对闲聊状态的免疫防御权下放到 LLM Semantic 层面，彻底杜绝短特征偏好漏记。
