# Nanobot 阶段性回顾与反思报告 (Phase 37 Retro Audit)

> **审计日期**: 2026-04-04
> **阶段位置**: Phase 37 (Execution Trace Archive)
> **状态**: 待在新会话中评估与修复

回顾并分析当前架构和近期实现（特别是 Phase 31-37 各个安全、检索、Hook 层），我们发现在目前的系统中存在 **5 个关键性问题**，涵盖了功能 Bug、安全隐患、架构设计遗漏以及需要改进的空间。

---

## 1. 安全隐患与系统 Bug (Security Vulnerabilities & Bugs)

> [!CAUTION]
> **Bug 1: L1 敏感路径沙箱拦截被 `edit_file` 绕过 (Critical)**
>
> - **位置**: `nanobot/agent/verification.py` -> `_check_rule_sensitive_path` (R07) 和 `nanobot/agent/tools/filesystem.py`
> - **分析**: Phase 35v2 中提到 “R07 规则补全 `edit_file` 工具的敏感路径检查”。然而在 L1 拦截器中，对 `edit_file` 工具读取路径参数使用的是 `tc.arguments.get("file_path", "")`，而实际 `EditFileTool` 定义的 JSON Schema 必填参数名为 **`"path"`**。
> - **后果**: 当大模型调用 `edit_file` 编辑并覆写敏感系统文件时，L1 获取到的 `file_path` 为空字符串，从而**完全绕过**了路径黑名单 (Deny-list) 的安全防御。

> [!WARNING]
> **Bug 2: macOS 特有高危指令逃逸了主 L1 防御层 (Medium)**
>
> - **位置**: `nanobot/agent/verification.py` -> `_DESTRUCTIVE_PATTERNS`
> - **分析**: Phase 36 为 macOS 引入了跨平台降级和沙箱优化。虽然我们在 `shell.py` 工具层的 `_guard_command` 中动态判断了 `sys.platform == "darwin"` 并拦截了 `osascript`、`launchctl` 等指令；但核心系统级文件 `verification.py` 的 Pre-execution L1 层中的 `_DESTRUCTIVE_PATTERNS` **并未同步引入这些规则**。
> - **后果**: 大模型生成的破坏性 macOS 指令依然可以通过 L1 前置拦截，仅仅在到达子模块 `shell.py` 执行时才被拦下。这极大地违背了架构设计中 “任何高危和破坏性探索应立刻在 L1 层被拒止 (Pre-execution Rigid Rule)” 的统一防御纵深理念。

---

## 2. 设计漏洞 (Design Flaws)

> [!IMPORTANT]
> **Flaw 1: 物理 RPA 操作完全绕过了 Smart HITL 人类审批 (High)**
>
> - **位置**: `nanobot/agent/tools/rpa_executor.py`
> - **分析**: Smart HITL 审批（Phase 32）强烈依赖于 `Tool` 基类中 `get_risk_tier()` 确定的风险等级。如果是 `MUTATE_LOCAL/1`（默认值），则直接放行；重写为 `MUTATE_EXTERNAL/2` 或 `DESTRUCTIVE/3` 才会触发审批中断。`exec` 和 `outlook(send)` 都被妥善标为了高危，但是 `RPAExecutorTool` （即 `rpa` 工具）**却没有重写 `get_risk_tier`**！
> - **后果**: 大模型可以无视 HITL 白名单拦截机制，自主控制物理鼠标和键盘执行任意高危操作（例如：通过模拟键鼠打开应用、格式化数据、发出敏感指令），且完全不会暂停 Agent Loop 寻求人类授权。作为接管系统的最底层越权代理，这是安全沙箱层面的严重疏漏。

> [!NOTE]
> **Flaw 2: Key 提取缓存机制忽略了会话上下文 (High - 逻辑缺陷)**
>
> - **位置**: `nanobot/agent/knowledge_workflow.py` -> `extract_key()`
> - **分析**: 在执行 Knowledge Base 检索前，系统使用带有 LRU 的对象 `_key_extraction_cache` 去缓存用户请求。但是其哈希键是 `cache_key = user_request.strip()[:200]`。`extract_key` 内部真实调用 LLM 时是**强依赖于 `history` 参数**进行语义消歧的。
> - **后果**: 给定如 "再跑一次"、"马上部署"、"查一下这个" 等短语令，只要之前的操作中包含了此短语并缓存了这个 key，那么无论当下的会话记录是什么，缓存都会直接在毫无关联的场景中无视 `history`，强行返回之前错误的 Task Key 进而导致“缓存幻觉”。

---

## 3. 可以改进的空间 (Areas for Improvement)

> [!TIP]
> **Improvement 1: 执行流 Trace Archive 的 JSON 截断损坏**
>
> - **位置**: `nanobot/agent/trace_archive.py`
> - **分析**: 当前 Phase 37 在保存线下 Debug trace 时，采用直接字符串级截断：`if len(content) > self.MAX_TRACE_SIZE: content = content[: self.MAX_TRACE_SIZE]`。这种粗暴地从中间切断 JSON 结构的行为，会导致输出的 `trace_*.json` 变为完全无效的格式。开发者事后排查时必然抛出 `JSONDecodeError`。
> - **建议**: 应在进行 `json.dumps()` 前，检查内部字典，手动裁剪 `trace` 对象内（特别是 `tool_chain` 文本或报错流）的长度，使其能够正常闭合并保持符合 JSON 结构规范。

> [!TIP]
> **Improvement 2: Remote HITL 的广播防重叠与无锁机制**
>
> - **位置**: `nanobot/agent/loop.py`
> - **分析**: 在当前多端审批广播中（Smart HITL Broadcast），Agent 利用 `for target in config.master_identities` 全局广播鉴权卡片。一旦开启了多并发的 Actor 模型 (即将进行的 Phase 38 Coordinator 架构) 或有多位管理员并发在线，并没有提供相应的令牌/独占处理锁。
> - **建议**: 当某个人类管理员点击 Approve 或 Reject 时，系统应该确保该审批被原子化响应并作废其他消息的审批状态。

---

## 4. Harness 论证与最终实施方案 (Implementation Plan - Final Version)

> **论证结果**: 经过架构师与审查员的两轮 Harness Workflow 对弈，我们重构了存在短视缺陷的初始修补方案。得出以下经过严谨验证的最终改进计划。请在下一会话 (Bugfix Sprint) 中严格参照此计划执行。

### 一、 安全沙箱层与防御重构
- **Bug 1 接口化根除拦截绕过**: 引流至面向接口的方式。在 `Tool` 基类中新增 `extract_target_paths(self, arguments: dict) -> list[str]`。涉及 IO 写入的子类必须重写并返回其影响的真实路径列表。L1 拦截器直接调用此通用接口进行黑名单比对，彻底终结基于参数名瞎猜的漏洞。
- **Bug 2 OS感知黑名单配置**: 解耦 `_DESTRUCTIVE_PATTERNS`，将其重构成系统级映射 `_DESTRUCTIVE_PATTERNS_MAP = {"windows": [...], "darwin": [...]}` 根据 `sys.platform` 加载不同的防御词库，实现底层拦截的跨平台隔离。

### 二、 逻辑与极致漏洞填补
- **Flaw 1 RPA 动态风险分级**: 取消全局的一刀切级别拦截，调整 `Tool` 组件使其支持 `evaluate_risk(self, arguments)` 运行时评估。RPA 工具抓取到 `click` 或 `type_text` 操作时拉高至 `DESTRUCTIVE` (触发 HITL)，仅在单纯 `read_screen` 截图时判定低风险并放行自动化。
- **Flaw 2 彻底废除伪缓存**: 移除 `_key_extraction_cache` 机制，强制所有的意图分离走 LLM 思维链路由。从根本上断绝复杂、包含隐藏对象的上下文 Hash 叠加造成的幻觉穿透。

### 三、 底层优化与多进程保障
- **Improvement 1 流式截断取代字典截断**: 放弃在 `trace_archive` 中通过 dict 大小或者递归修剪的愚蠢动作。在最源头产生的部位 (如 `shell` 执行节点或者 Python 脚本执行回传点) 若察觉流输出过大，立刻行使短切拼接 `[...Truncated System Output due to size...]`。
- **Improvement 2 本地原子并发锁锁存状态**: 为阶段 38 分布式部署做前置铺垫。在多端 HITL 判定响应时，使用生成 `.nanobot/tmp/approval_{uuid}.lock` 与 `os.O_CREAT | os.O_EXCL` 的方式加持文件系统锁级的一致性，防止多端管理并发造成脏读放行。

---

**下一阶段建议行动点**: 
请在新会话中调用以上 **Harness 最终实施方案** 开启代码实现迭代。首先落地 **Bug 1 (沙箱接口抽离)** 与 **Improvement 2 (原子锁)**。
