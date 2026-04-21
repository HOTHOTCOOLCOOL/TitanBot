# Phase 51 & 52 Manual Test Guide: M-RAG & GroupRAG

**Revision:** 1.0 (2026-04-16)

此指南为非技术人员以及测试人员准备，用于无脑执行针对新落地的 Phase 51 (M-RAG 双索引) 和 Phase 52 (GroupRAG 并发推理) 特性的验收测试。

---

## 1. 准备工作

1. 打开主配置编辑器或手动修改 `workspace/nanobot/config/schema.py` 内部（如果是从 JSON 加载请修改对应的 `config.json` 或者环境变量）。
2. 将以下开关设置为 `true` 开启实验特性：
   - `config.features.marker_indexing = true`
   - `config.features.parallel_reasoning = true`

## 2. Phase 52 并行推理 (GroupRAG) 验收测试
**目标**：验证大模型能否在遇到复杂问题时，**自动或手动触发并发的多子节点（Subagent）并行分析**，并在发生巨大分歧时拦截并要求人类裁决。

### 步骤 2.1: 正常综合分析 (自动无冲突汇总)
1. 在命令行或聊天界面输入指令：
   ```text
   /parallel 请对比分析“使用本地大模型（如 Llama 3）进行数据洗脱”与“使用云端 API（如 GPT-4）”在隐私安全性、成本开销以及扩展性上的优劣。
   ```
2. **期望结果**:
   - 界面立即返回提示：*"Engaging Convergent Reasoning (GroupRAG)... Spawning parallel subagents. Please wait."*
   - 后台等待 10~30 秒（期间可以观察后台日志 `SubagentManager` 拉起了针对每个角度的独立 Agent）。
   - 最终系统抛出一个聚合结论，明确标出 *"### Convergent Reasoning Result"*。

### 步骤 2.2: 冲突检测机制 (HITL 拦截触发)
为了迫使系统内部产生截然相反的结论以测试冲突拦截器，我们需要：
1. 打开 `nanobot/config/schema.py`，将 `parallel_conflict_cosine_threshold` 临时调至 `0.99`（极度容易触发冲突拦截）。
2. 输入完全相同的问题。
3. **期望结果**:
   - 界面在汇总结果下方警报：**[!] CONFLICTING CONCLUSIONS IN PARALLEL TRACES:**。
   - 这表明系统成功阻断了 LLM 去“和泥巴”强行统一相悖的结论，并将原始矛盾呈递给用户。

---

## 3. Phase 51 缓存与双路索引 (M-RAG) 验收测试
**目标**：验证针对普通文档执行 Marker 抽取时，是否生效、是否正确命中了本地哈希缓存从而节省成本。

### 步骤 3.1: 触发抽取与生成缓存
1. 在知识库中随意存入一篇新闻或日志，例如向 agent 发送：
   ```text
   /memory store 今天下午 3 点公司的邮件网关发生了严重的拥堵，导致发送给欧洲区的所有周报邮件退回。原因是上游供应商的服务限流...
   ```
   *注意：后台的 VectorMemory 会尝试使用 MarkerExtractor 进行抽取*。
2. **验证动作**：进入文件路径 `workspace/.marker_cache/`。
3. **期望结果**：在该文件夹内，应该能看到一个新生成的 `hash.json` 缓存文件。打开后可以看到类似 `{"key": "公司邮件网关拥堵原因", "value": "今天下午3点...", "paragraphs": [0]}` 的独立标签对。

### 步骤 3.2: 缓存命中（免费召回）测试
1. 在十分钟后，修改同样长度但不改变实质内容的文本（或将原来的日志原样重新录入）。由于我们用 `prompt_version + content` 做完全哈希，如果是**相同的文本内容**：
2. **期望结果**：后台 `nanobot.log` 会输出：`Successfully generated X markers for ... via LLM` 的类似日志（若有打印）。最明显的是，大模型的计费接口**绝不会**再被调用一次，系统瞬间提取 `.marker_cache` 内的数据。若覆盖率太低导致回退至普通 Chunking（日志报 `Marker coverage too low`），说明 `fallback` 逻辑亦符合设计预期。
