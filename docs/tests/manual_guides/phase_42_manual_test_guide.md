# Phase 42 人工回归测试操作指南 (Manual Test Guide)

> **目标版本**: Nanobot 架构演进 - Phase 42A, 42B, 42C
> **前置条件**: 已完成 Phase 41 的中间件管线测试

本指南旨在指导开发/测试人员手动验证 Phase 42 阶段引入的三大核心架构重构及其稳定性。

---

## 🛠️ 测试环境准备 (Environment Preparation)

1. **服务启动与依赖项环境**：确保激活包含所有最新依赖的环境。
    ```bash
    # 启动 Nanobot 项目前，请先确保已同步最新代码与依赖包
    cd d:/Python/nanobot
    python -m pytest tests/test_subagent_security.py tests/test_routing.py   # 可选：确保单元测试绿灯
    # 启动客户端进行测试
    ```
2. **清理历史状态 (可选但推荐)**：为了验证知识库统一迁移脚本，测试前建议备份或保留一下 `workspace/knowledge/` 目录下的老文件，或者在干净的环境里测试。

---

## 🧪 Test Case 1: SubagentManager 安全沙盒审查 (Phase 42A)

**测试目标**: 验证 Subagent 是否被无缝接入了 `_run_agent_loop` (Onion Middleware) 之中，并严格受到工具白名单（移除 `exec`、`spawn`等）以及 HITL 的限制。

**操作步骤**:
1. 向 Nanobot 发布一条需要长期或并发探查的指令，触发它生成一个 Subagent。
   - *Prompt 示例*: "帮我启动一个子代理，让它去读取工作区下 `progress_report.md` 文件的内容，并用命令行输出给我。"
2. 观察控制台日志的输出过程：
   - 检查 `t-workerxxxx` 类似的 `chat_id` 是否成功通过 `Onion Middleware` 启动。
   - 检查子代理在尝试执行命令行（如果有通过其它伪装方式调用 `exec` 工具）时，是否因为工具在 `ToolRegistry` 中不存在而失败。或者正常只使用被授权的 `read_file`, `write_file`，`web_search`。
3. 尝试恶意诱导子代理。
   - *Prompt 示例*: "创建一个子任务，子任务的唯一目标是调用系统的 shell 命令 `whoami`。"
   - **预期结果**: 系统应该报错工具不存在，或者安全拦截不会在无 HITL 的情况下执行裸奔 Shell。

---

## 🧪 Test Case 2: 双脑知识库统一与数据迁移 (Phase 42B)

**测试目标**: 原先基于 JSON 的 `ReflectionStore` 已被废弃。验证新的沉淀反思逻辑是否直接对接并写入基于向量的 `Experience Bank`。

**操作步骤**:
1. 验证迁移脚本的幂等性（如果有老版本反射数据留下）：
   - 执行命令：`python migrate_reflections.py`（若目录中存在该脚本当单独提供时）。
   - 查看控制台输出，确认历史记录成功迁移到向量数据库中。第二次执行应不引发重复插入或报错（实现幂等）。
2. **产生新知识 (Experience)**：
   - 与 Nanobot 进行一段有深度的技术对话。
   - *Prompt 示例*: "记住一条新规则，凡是我以后提到'发布'这个词，你都默认带上[Release]标签并在回复前帮我进行全量代码格式化。"
   - 交互结束后，触发一次 L3 反思机制（或等待一定对话轮数后其自动触发总结）。
3. **检索验证**：
   - 验证向量检索与合并上下文的表现。
   - *Prompt 示例*：“还记得我刚才刚给你定的'发布'规则是什么吗？”
   - **预期结果**: 在 `knowledge_workflow` 日志中应能观测到从 `Experience Bank` （VectorStore）检索回相关的上下文，原有的 `ReflectionStore` 文件不再更新，系统没有触发幻觉级联，且 `_INJECTION_BUDGET` 消耗合理。

---

## 🧪 Test Case 3: Loop 巨石类解耦及意图路由 (Phase 42C)

**测试目标**: 验证抽离出来的 `nanobot/agent/routing.py`（包含 `IntentClassifier` 和 `ModelRouter`）是否正常接管流量，且 VLM 模型路由及正则表达式 Bypass 没有退化。

**操作步骤**:
1. **测试 Chitchat Regex Bypass (闲聊快速路径)**:
   - 发送单字词：`111` 或 `ping` 或 `早上好吗`。
   - 观察耗时及日志。
   - **预期结果**: `IntentClassifier` 应返回 `chitchat_safe`，绕过重度上下文检索及 RAG 流程，直接输出打招呼或快速响应内容，端到端延迟低。
2. **测试正常任务 Intent**:
   - 发送明确任务："用 Python 写一个计算斐波那契数列的代码"
   - **预期结果**: `IntentClassifier` 返回 `task`，正常进入完整的思考图谱环节。
3. **验证 VLM Vision 视觉大模型路由**:
   - 在新对话中或通过测试通道，发送一张图片（附带 Prompt："图片里的架构图是什么？"）
   - **预期结果**: `ModelRouter.determine_target_model` 应该在最近记录中探测到 `image_url`，并将处理模型从通用大模型切换（Fallback 或提升）到配置的 VLM 模型，由视觉模型接管解析任务。确保之前修复的 LRU 缓存 (B-2 fix) 在后台日志平稳过度且没有连续创建 Provider 对象。

---

## 📊 测试检查清单 (Checklist)

如需报告 Bug，请对照下表记录：

- [x] [Phase 42A] `SubagentManager` 创建的代理没有使用 `exec` 工具的能力。
- [x] [Phase 42A] 如果强行让子代理使用未知工具，会得到 `Tool Execution Failed` 相关提示，不会触发 Python Stack Crash。
- [x] [Phase 42B] 新的知识及经验正常落地到 `Experience Bank`，未生成旧版本的 `reflection.json`。
- [x] [Phase 42C] "hello"、"1" 等正则白名单依然有效且不引发完整 Agent Loop 开销，日志显示 `chitchat_safe`。
- [x] [Phase 42C] 发送带图片的请求能正常响应并成功切换目标视觉模型。

---

## 🧪 Test Case 4: 全链路 Trace-ID 染色系统观测 (Phase 42 A/B Backlog)

**测试目标**: 验证请求的生命周期在重构为 Shell 模式的外壳后能无死角地被 Trace ID 追踪，Loguru 日志输出能够统一附带 `[t-xxxxx]` 标识，并且各项 Routing/Intercept Tags 皆能按需回推给前端元数据。

**操作步骤**:
1. **基础 Trace-ID 及 Loguru 标识验证**:
   - **交互指令**: 向 Nanobot 发送 `"你好，帮我查询一下今天的美股大盘情况"`。
   - **行为要求**: 在运行 `nanobot gateway` 或 `nanobot agent` 时的控制台中，找到最新涌出的一批事件日志。
   - **预期结果**: 从接受请求的一刻到回传文字，期间所有由核心日志系统 `logger.info`、`logger.debug` 等输出的信息，起始处都会标有形如 `[t-xxxxxx]` 的同名请求专属标志。
2. **轻量染色 (InterceptTag) 及回路验证 - 高危拦截**:
   - **交互指令**: 发送明确试图执行本地脚本的请求 `"使用命令行运行 Python 测试脚本 ./test.py"`。
   - **预期结果**: 这是会触发 `HITL_SUSPEND` 挂起的指令。在控制台的输出中应观测到系统抛出 HITL 中断行为，请求结束。且后续日志 `[t-xxxxx]` 正确剥离并释放，没有残留复用现象。
3. **血缘链路传播 (Subagent Trace Lineage)**:
   - **交互指令**: 发送需要长效驻留的异步并发任务，例如 `"在后台启动一个研究子代理去寻找最新的 AI Agent 论文"`。
   - **预期结果**: 在后台控制台的日志中，能看到 `Subagent [t-BBBBBBBB] starting task: ... parent_trace=t-AAAAAAAA` 的平滑过渡信息，证明当前协程创建时成功从主 `contextvars` 捕获到了父级血缘 ID，并在自身执行期间采用不相干的独立前缀保护上下文不穿透。

## 📊 新增检查清单 (Trace-ID Checklist)

如需报告 Bug，请对照下表记录：

- [x] [Phase 42 A/B Backlog] Loguru 控制台日志正确反映了 `[t-xxxxx]` 前缀，未发生 Patcher 抛异常引起的整个日志系统哑火/死锁。
- [x] [Phase 42 A/B Backlog] 外层大颗粒的 Shell Pattern (`_process_message`) 在发生中间件 `ctx.abort()` 时也保证了 Context 的 `try..finally..reset(token)` 清理回收，未发生内存或 Trace 复用泄露。
- [x] [Phase 42 A/B Backlog] 产生的各类轻型 Tag （如 `VLM_ROUTE`, `CHITCHAT_FAST` 等）能够在 `OutboundMessage.metadata.route_tags` 里供外部溯源诊断解析。

*测试完成后，请通过 Issue 频道反馈任何异常报错 `Traceback`，或直接继续提问进行联调修复。*
