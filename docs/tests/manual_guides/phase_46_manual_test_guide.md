# Phase 46 专项人工测试指南 (Query Expansion & Experience Consolidator)

本指南详述了针对 Phase 46A (Fallback-Driven Query Expansion) 与 Phase 46B (Offline Experience Consolidator) 的功能验收方法。请按照以下步骤逐步执行。

## 测试前置条件
1. 确保最新网关服务已重启：`nanobot gateway --verbose`
2. 当前目录位于项目根目录：`d:\Python\nanobot`
3. 知识系统 (`knowledge`, `experience bank`, `trace_archive`) 已准备完毕。可以通过发一些带特殊实体的提问构建一两个测试数据。

---

## Part 1: Phase 46A - Query Expansion (查询扩展)

### 验证指标
当底层精确匹配（Exact）、子串匹配（Substring）、基础混合匹配（Hybrid）全盘失败时，系统能够静默调用轻量 LLM 进行补救，识别具有深意关联的概念词，从而在 `knowledge_graph` 中检索到相关文档卡片，且延迟应被成功熔断在 3 秒。

### 操作步骤

**1. 准备冷知识库 (测试环境)**
往某个 Knowledge 或者 Experience 里增加一条非常偏口语化或是别名的知识条目：
```bash
# 在 CLI 中让 Nanobot 记忆
nanobot agent -m "请记住我们的代号叫『南极洲破冰行动』，其实指的是年底服务器迁移计划。"
```
等待系统记录到 `ExperienceBank` 或 `Memory.md` 中。

**2. 发起常规模糊请求**
发送完全不包含原词的变体词：
```bash
nanobot agent -m "请告诉我年底机房倒腾那个大动作的代号叫啥来着？"
```

**3. 期望与观察结果**
- **期望结果**：系统能准确回答出“南极洲破冰行动”或者“年底服务器迁移计划”。
- **后台日志观察**：
  在控制台启动了 `--verbose` 参数或日志面板内，你应该会看到**三层全盘 MISS (Zero Match)** 的日志。
  然后出现 `Fallback-Driven Query Expansion` 被激活的相关日志，它生成了备选词 `["服务器迁移", "年底机房"]`，随后再次发起了 `hybrid_retrieve` 命中记录。最后成功将 `_match_method` 记为 `"query_expansion"`。
- **超时截断验证**：断开网络或修改 `provider` 卡住它，你将看到因为 `asyncio.wait_for(..., timeout=3.0)` 的介入，它只卡了 3 秒钟就在后台抛出 Timeout 并静默放弃，丝毫不干扰 `AgentLoop` 后续的大脑自主查询。

---

## Part 2: Phase 46B - Offline Experience Consolidator (离线经验整编器)

### 验证指标
Worker SubAgent 能够在隔离的环境中被 Cron 准时或强制调起，基于最近一批挂掉的 Trace 准确产出一条包含 `[Auto-Generated]` 的防坑战术指南推入 `Experience Bank`。

### 操作步骤

**1. 手动制造错误并生成 Trace 记录**
我们需要刻意诱导主模型产生一次执行错误并写入 `memory/traces/` 目录。
为了确保离线复盘系统（Experience Consolidator）能够捕获完整的失败上下文，我们必须使用被判定为“高复杂度”（High-Complexity）的 `exec` 工具，并强制让它返回以 `Error:` 开头的标准输出。

```bash
nanobot agent -m "请严格使用 exec 工具，毫不修改地执行以下命令：python -c \"print('Error: manual failure')\""
```
大模型会下发带有该 python 命令的 `exec` Tool Call。沙箱执行后会捕获到标准输出 `Error: manual failure`，这会稳定触发系统级的错误判定（`outcome="error"`）。随后，由于 `exec` 属于高复杂度工具，必定会触发 Phase 37 级的深度 Trace 转储（`dump_debug_trace`），这为下一步离线经验整编器提供了最完美的包含 `final_content` 的“反面教材” Trace。

**2. 探测 Cron Job 被正确注册**
在 CLI 打开另一个终端验证：
```bash
nanobot channels status    # (虽然叫channels_status，可以通过接口看)或看 gateway 日志
```
- **期望**：启动日志应该打印 `added job 'Offline Experience Consolidation' (id: xxx)`。

**3. 强制唤醒 /consolidate_experience 工作流**
不再干等 凌晨 3点（`0 3 * * *`），直接使用 CLI 发送触发器命令。
```bash
nanobot agent -m "/consolidate_experience"
```
- **期望结果 1**：客户端瞬间会回复文本：`Offline Experience Consolidation task started.`，而无需等待它做完！这是一个基于 `_safe_create_task` 挂载的背景长任务。

**4. 观察 SubAgent 的后台运作**
- **期望结果 2**：盯着网关 Server 日志。你会看到：
  - `SubAgent experience consolidation triggered with 1 failed traces.`(抓到了你刚故意报错的那条 Trace)。
  - `Spawned subagent [t-xxxxx]: Offline Experience Consolidation...`
  - SubAgent 工作结束，被赋予了 `SaveExperienceTool` 并顺利调用成功。

**5. 验收 Experience Bank 落盘结论**
可以向小助手验证，也可以直击底层文件。
```bash
# 查询刚才它到底学会了什么
nanobot agent -m "/kb list"
```
- **期望结果 3**：列表中势必有新增的一条数据，或者是检查 `memory/experience_bank.json` 文件。内容里带有触发词，以及明显包含有 `[Auto-Generated]` 标签的建议（比如："When file fetching fails heavily, verify path existence first."）。此标签旨在让人类开发管理员能周期性地审查并清理 AI 的自主学习成果。

### 验收成功标志
如以上步骤能够不受卡顿（Phase 46A）、不破坏架构限制（SubAgent的工具局部注入，Phase 46B），并完全符合预期产出，则说明 Phase 46 的语义拓展和自我归因迭代机制部署完美闭环运转！

---

## 🛑 Lessons Learned (架构测试大坑复盘)

在执行 Phase 46B 的验收时，我们曾遭遇过严重的“Trace 丢失”现象。以下是项目中潜藏的重大架构断层，特此记录以防后患：

1. **Trace 轮转淘汰 Bug (`st_mtime`)**：此前的 `TraceArchive._cleanup` 淘汰策略使用了简单的文件名字母排序，这导致最新生成的类似 `trace_t-23bf...` 的高位 UUID 文件被错误地当做“老文件”直接销毁。目前通过修改为真实的修改时间 (`st_mtime`) 轮转已彻底修复该问题。
2. **Phase 37 与 Phase 44 的深层格式代差**：离线经验整编器依赖包含详尽错误与堆栈的 `dump_debug_trace`（含有 `final_content` 字段）来读取分析，但这套深层 Dump 机制仅对高危极客能力（`_HIGH_COMPLEXITY_TOOLS`: browser, exec等）开放。这意味着如果你用类似 `list_dir` 的轻量级工具做错误诱导，系统只会在最后写入一个轻量级的 `dump_tool_calls`。轻量级 Trace 缺少 `outcome` 和 `final_content`，最终会被离线整编器当做正常流量直接忽略。
3. **连击阈值避让陷阱**：主模型过于优异且“宽容”！如果你发出的报错指令没有打破熔断底线 (`streak >= 3`)，大模型会在单回合内平滑地将报错当作“正确结果”转发回来（`FINISH`）。于是，系统层并不判定该次任务遭遇硬性死亡，这就再次避开了高强度 Debug Trace 的生成。
4. **Daemon 守护内存隔离**：在后台网关服驻留期间，本地直接修改代码（如给 `commands.py` 添加探针后门）均不可见，务求重启进程方可加载生效。
5. **底层 API 签名不同步 (Technical Debt)**：在最初开发 `SaveExperienceTool` (Phase 12+) 和强化 `TaskKnowledgeStore.add_experience` (Phase 29+) 时缺乏系统集成测试。导致前者传入了 `trigger/prompt`，而后者要求 `context_trigger/tactical_prompt`，引发子 Agent 虽然提取成功，但保存时隐式崩溃（被守护进程掩盖）。**教训：涉及跨模块的数据写入能力，必须补充端到端参数契约测试。**
6. **双轨数据 UI 遗漏**：虽然底层的 `TaskKnowledgeStore` 演化出了 `tasks` (工作流) 和 `experiences` (应对战术) 两套记忆模型，但前端的 `/kb list` CLI 指令依然停留在 Phase 29 前的旧时代，只遍历 `tasks`。导致落盘成功后，人眼无法在 UI 上得到正反馈。**教训：后端数据结构发生重大拓宽时，必须地毯式排查所有读取该数据的展示层 (CLI / Web UI)。**

**最佳实践**：测试高阶离线分析架构，**不要尝试用低级错误糊弄系统**。只有真正的技术危机（如底层异常强行打出的 Trace文件）才能触及离线整编的雷达探测网。同时，不要只迷信模型生成代码的速度，缺乏强一致性测试的速成代码终成架构中的“幽灵雷”。
