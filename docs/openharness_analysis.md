# OpenHarness 架构借鉴分析报告

基于对 `HKUDS/OpenHarness` 源码及架构的深入分析，并结合 Nanobot 坚持的 “单一代理 (single-agent)” 和 “零外部基础设施 (zero-extra-infrastructure)” 原则，以下是我们可以在 Nanobot 中借鉴的高价值/低成本思路：

## 1. 高投资回报率 (High ROI) 的可借鉴点 🌟

### 1.1 生命周期 Hook 机制 (PreToolUse / PostToolUse)
- **分析**：OpenHarness 在 `hooks/executor.py` 中实现了一套极其优雅的 Hook 拦截机制，支持在工具调用前（PreToolUse）和调用后（PostToolUse）触发事件。这不仅可以通过基于规则的命令（CommandHook）拦截高危操作（如 `rm -rf /`），还可以通过大模型（AgentHook/PromptHook）进行动态安全审计。
- **借鉴建议**：Nanobot 目前已经有 `ApprovalStore` (HITL) 进行高危操作拦截，但如果引入基于生命周期的 `Hook` 机制，我们可以：
  1. 将硬编码的安全检查从具体的工具类解耦出来。
  2. 实现 **“大模型双重确认” (LLM-based validation)** 作为 Hook，让模型在执行 Shell/File 等敏感工具前自我审计。

### 1.2 基于 Glob 的路径权限隔离 (Path-Level Rules)
- **分析**：在 `permissions/checker.py` 中，OpenHarness 使用结构化的 `PathRule` (`{"pattern": "/etc/*", "allow": false}`) 进行极轻量级的细粒度路径控制。
- **借鉴建议**：这完全符合我们 “零外加基础设施” 的理念。目前 Nanobot 可以考虑在 `filesystem.py` 或核心权限中心加入基于全局配置文件（如 `settings.json`）的路径黑白名单机制，实现比简单的 `READ_ONLY` 或 `WRITE` 更可靠的沙盒级路径防护，防止 Indirect Prompt Injection 导致越权读取。

### 1.3 兼容 Claude 插件生态 (claude-code/plugins)
- **分析**：OpenHarness 复用了 Anthropic 官方的 `claude-code` 插件格式 (`.claude-plugin/plugin.json`)，支持即插即用的 Hook、Commands 及 MCP server。
- **借鉴建议**：虽然我们摒弃了“孤立的 Skill Agent”和庞大的外围工具链，但引入标准的 `.json` 插件清单文件，可以让 Nanobot 未来在不改变核心逻辑的前提下，通过简单的 JSON 定义注入新的 Tool 或系统提示词，大幅增强平台的扩展性。

## 2. 需谨慎考虑 / 建议舍弃的点 (Misaligned with Nanobot) ⚠️

### 2.1 Swarm Coordinator (多智能体协同 / Subagent)
- **分析**：OpenHarness 包含了完善的子代理生成与委托、团队注册表等功能。
- **决策**：**直接舍弃**。我们近期决议 Nanobot 坚守 single-agent 架构。引入子系统会大幅增加状态管理、打断控制与回溯逻辑的复杂度，违背当前的技术栈选型。

### 2.2 React/Ink TUI (复杂的前端界面)
- **分析**：OpenHarness 提供了一个漂亮的 React-based 终端用户界面。
- **决策**：**暂不借鉴**。Nanobot 目前采用流式传输和相对简单的终端交互，保持环境依赖极简（Python 原生）最符合我们当前的轻量化发展规划。

## 3. 具体实施建议 (Actionable Next Steps)

如果我们要提取上述的高回报特性，可以考虑加入后续的开发阶段：
1. **安全与审查能力扩展**：借鉴 OpenHarness 的 `checker.py`，在执行敏感 Tool 前置基于泛型的路径验证，进一步加固 Phase 33 的安全底座。
2. **抽象 Hooks 机制**：重构我们在 `loop.py` 中的执行前拦截逻辑，剥离为轻量级的 `PreToolUse` 事件流，为之后零成本接入各种审查策略铺平道路。
