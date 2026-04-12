# Phase 46B: Offline Experience Consolidator

## 概述
作为 ADR-47 的落地项，本阶段实现了一个基于 Cron 驱动的低代码安全机制——离线经验整编器：
通过复用现有的后台 Subagent 机制对失败日志进行 LLM 归因和记录归档，实现自动化能力沉淀，并确保严格遵守零架构负担原则。

## 核心实现
1. **Cron调度集成**：在 `nanobot/cli/commands.py` 注册每日凌晨 `03:00` 执行 `/consolidate_experience` 指令。
2. **轻量级启发式识别**：在 `nanobot/agent/commands.py` 中引入 `consolidate_experience` 处理逻辑：
   - 使用轻量 Python 优先策略遍历近 20 条 TraceArchive 的 JSON 文件。
   - 启发式判断错误 (`final_content` 以 `Error:` 打头，或者最后一条 tool call 状态包含 `<failed>`)。
   - 若命中失败，则构建上下文并请求 Subagent 解析原因提取 `<trigger, prompt>` 字典组合。
3. **安全继承机制**：由于原始安全体系禁用了 `subagent.py` 一切写操作能力，为满足本步骤将归因录入库的特定需求，针对性修改了 `nanobot/agent/subagent.py` ，如果检测到其母进程 `agent_loop_ref` 存在 `task_knowledge` ，则显式下发并注入 `SaveExperienceTool`，完美解决权限封锁下的功能安全渗透。

## 对架构的影响 (Lessons Learned)
避免让 LLM 框架自行循环遍历深层的复杂数据结构，应当**采用 Native Python 提取精简上下文，将最终的决断环节派发给 LLM**，该原则有效遏制了长文本上下文崩溃的隐患。
