# ADR-43：Provider-Level XML Tool Call Fallback Parser
## 架构决策备忘录 (Architecture Decision Record)

> **状态**: Accepted
> **日期**: 2026-04-09
> **关联 ADR**: ADR-42（洋葱中间件）、ADR-42A（SubagentManager 安全补丁）

---

## 一、背景与问题定义

Nanobot 当前的 `LiteLLMProvider._parse_response()` 仅从 `message.tool_calls` 结构化字段读取工具调用，完全忽略 LLM 在 `content` 中以 XML 形式输出的工具调用。

以下已知场景会导致工具调用静默丢失，Agent Loop 错误地认为 `has_tool_calls == False`，将未解析的 XML 字符串广播给用户：

| 场景 | 触发条件 |
|------|----------|
| Provider 能力退化 | 模型版本降级 / gateway strip 工具字段 |
| OpenRouter/SiliconFlow 中继损坏 | tool_calls 字段被代理层丢弃 |
| 本地 vLLM fine-tune | 不支持 function call 原语，以 XML 模拟 |
| Streaming 累积错误 | delta 合并不完整，部分工具调用丢失 |

---

## 二、架构决策

### 1. Provider-Level 拦截与 "Read-Only" 策略
**决策**：Fallback 仅在 `_parse_response()` / `_parse()` 内处理，只在 `tool_calls == []` 时激活。提取工具调用但**完全不修改 `content`**。
**权衡**：以轻微损耗 UI（残余的 `<tool_use>` XML 标签可能暴露给终端用户）为代价，换取：
- 零数据破坏风险
- 历史会话结构的彻底纯净化（不产生二次格式化带来的状态割裂）
- Streaming 流式输出路径的天然容错

### 2. 多重防护过滤（防提示词注入）
由于放开了 Content 内容层的解析，恶意 System Prompt Injection 可能伪造 XML 诱导执行。
**防护机制**：
- `valid_tool_names` 白名单：提取时必须过滤不存在的工具，拦截所有恶意注入名称。白名单由当次 `chat()` 对话上下文 `tools` 参数直接派生。
- L1/HITL 穿透：提取的 XML Tool Call 依然必须经过 L1 护栏和 Phase 42A 加入的安全管控沙箱（Smart HITL 拦截高危指令如 `exec`/`browser`）。

### 3. 多种流行 XML 格式全面兼容
适配目前开源生态普遍采用的格式：
- **Claude Style**: `<tool_use><name>...</name><input>...</input></tool_use>`
- **General OS-VLLM**: `<tool_call><tool_name>...</tool_name><parameters>...</parameters></tool_call>`
- **JSON-Wrapped (Qwen/DashScope)**: `<tool_call>{...}</tool_call>`

### 4. Deterministic IDs 兼容 WAL
崩溃恢复依赖于工具调用的 `call_xxxxx` ID，随机或默认生成的 ID 会导致 Phase 40B-1 检查点机制受破坏。
**决策**：通过 `hash(content + index)` 生成确定性 ID（`call_xfxxxxx` 前缀指示其来自于 Fallback Parser）。

## 三、实施验证计划
- 接入日志与 APM：`metrics.increment("xml_fallback_activations")`
- 提供完整的单元测试在 `tests/test_xml_fallback_parser.py`

## 四、安全附录与讨论
> Q: 为什么不采用 `_RE_FENCE`（匹配 Markdown ```json 块）的方式进行提取？
> A: 没有任何 XML/结构标志的 Markdown JSON 块无法体现出真正的 "工具调用意图"，盲目解析极易产生大规模 False Positives（例如 AI 只是想给出 JSON 示例）。
