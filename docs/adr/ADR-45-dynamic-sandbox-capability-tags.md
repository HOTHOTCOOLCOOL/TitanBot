# ADR-45: 动态沙箱与能力标签系统

**状态**: 已采纳 (Accepted)  
**日期**: 2026-04-11  
**Harness 辩证轮次**: 5 阶 (Sonnet Planner → Opus Critic → Gemini V2 → Gemini Validator → Sonnet Final)  
**受影响文件**: `nanobot/agent/capability.py`（新建）、`tools/base.py`、`tools/shell.py`、`tools/registry.py`、`tools/mcp.py`、`plugin_loader.py`、`verification.py`、`middleware/hitl.py`、`coordinator.py`、`sandbox.py`、`sandbox_worker.py`、`config/schema.py`

---

## 背景与问题陈述

Phase 44 完成后，架构安全审查揭示了三个**尚未被任何已有 ADR 覆盖**的结构性痛点：

### 痛点 1：工具能力完全缺乏系统化声明
- `verification.py` 和 `hitl.py` 依靠 **hardcoded 工具名字符串**（如 `if tc.name == "exec"`）匹配拦截，随工具生态增长持续膨胀
- 第三方 Plugin 工具和 MCP 工具动态注册后完全游离于 L1 安全体系之外
- 现有 `RiskTier` 枚举（`tools/base.py`）仅服务于 HITL 触发，与 L1  规则体系完全脱节，形成双重分类孤岛

### 痛点 2：沙箱系统是"一刀切"的静态配置
- `ShellSandbox` 和 `PythonSandbox` 共享全局 `SandboxConfig`，无法按工具差异化设定约束
- `ExecTool._guard_command()` 的安全逻辑嵌在工具内部，游离于统一 L1 验证流水线之外
- `SSRS` 技能需要特定网络权限只能通过"绕过沙箱"实现

### 痛点 3：Coordinator Worker 进程缺乏沙箱感知
- `CoordinatorManager.spawn()` 不向子进程传递任何安全约束
- Worker 以父进程相同权限运行，sandbox_root 仅作路径隔离，与 `SandboxConfig` 完全脱钩

### Harness 辩证发现的额外破口（Opus C1/C8）
- **插件和 MCP"自声明安全"是零日漏洞**：任何恶意插件声明 `capability_tags = NONE` 即可隐身于所有 Tag-Driven 规则之外
- **Draft V1 的 `SandboxProfile.network_allow_hosts`** 在 ShellSandbox 上下文中完全不可执行（无 seccomp / Job Object 支持）

---

## 核心设计原则（从辩证中萃取）

**原则 1：悲观默认（Pessimistic Default）**  
所有动态加载的外部工具（Plugin、MCP）默认分配最高风险标签 `UNTRUSTED_EXTERNAL`，强制触发 HITL。只有系统管理员在 `config.json` 中显式降级才能减轻约束。内置核心工具才可硬编码精确标签。

**原则 2：不做虚假安全承诺**  
ShellSandbox 在缺乏 OS 级隔离（seccomp/Cgroup/Job Object）的情况下，无法在进程启动后阻止网络访问。防御重心前置到 L1 语义拦截（命令字符串分析）和 HITL 审批，不承诺物理沙箱隔离能力。

**原则 3：单一权威（Single Source of Truth）**  
所有安全判定——L1 拦截、HITL 触发、exec 命令黑名单——统一收口到 `verification.py`。废除工具内部分散的安全卫兵代码（`ExecTool._guard_command`）。

**原则 4：继承不可放宽（Non-Escalation Invariant）**  
Coordinator Worker 的安全约束通过启动时 CLI 参数硬锁，与 HTTP payload 完全隔离，Worker 无法在运行时解除已由父进程写入的约束。

---

## 决策

### 变更 1：废除 `RiskTier`，建立统一能力标签体系 `CapabilityTag`

**为什么**：`RiskTier` 是私有于 HITL 系统的枚举，L1 验证规则无法引用它，两套分类系统并存是架构反模式。

**决策**：新建 `nanobot/agent/capability.py`，用 `Flag` 枚举支持位组合：

```python
class CapabilityTag(Flag):
    NONE = 0
    
    # 数据与系统交互流向
    DATA_READ          = auto()  # 读取本地/工作区数据
    DATA_WRITE         = auto()  # 写入本地/工作区数据
    INFO_RETRIEVAL     = auto()  # 外部检索（web_search, outlook.search, ssrs）
    SYS_COMMUNICATION  = auto()  # 向外发送人类通知（send_email, message）
    
    # 敏感执行能力
    SHELL_EXECUTION    = auto()  # 执行 OS Shell 命令或脚本
    CODE_EVALUATION    = auto()  # 在沙箱中求值代码（hooks.py, Python snippets）
    
    # 风险维度
    MUTATIVE           = auto()  # 产生可持久化的状态变更副作用
    DESTRUCTIVE        = auto()  # 高破坏性操作（删除、格式化）
    UNTRUSTED_EXTERNAL = auto()  # 未经审计的外部插件或 MCP 工具
    
    # 组合快捷方式（HITL & L1 判断基准）
    IS_HIGH_RISK = DESTRUCTIVE | UNTRUSTED_EXTERNAL | SHELL_EXECUTION
```

工具基类 `Tool`（`tools/base.py`）改造：

```python
class Tool(ABC):
    @property
    def static_tags(self) -> CapabilityTag:
        """工具固有的不可变标签（由内置工具硬编码声明）。"""
        return CapabilityTag.NONE
    
    def evaluate_dynamic_tags(self, args: dict) -> CapabilityTag:
        """基于运行时参数追加风险标签（取代 get_risk_tier）。"""
        return CapabilityTag.NONE
    
    def get_effective_tags(self, args: dict, config_override: CapabilityTag = CapabilityTag.NONE) -> CapabilityTag:
        """合并三层标签：静态 | 配置覆盖 | 动态参数分析。"""
        return self.static_tags | config_override | self.evaluate_dynamic_tags(args)
```

废除 `get_risk_tier()` 和 `RiskTier` 枚举。

---

### 变更 2：悲观默认 — 外部工具强制标注 `UNTRUSTED_EXTERNAL`

**为什么**：恶意或有缺陷的插件可自声明 `NONE` 标签绕过所有 Tag-Driven 规则。

**决策**：在加载器中强制注入，与工具自身实现无关：

`plugin_loader.py`：
```python
# 任何 Plugin 工具实例加载后，强制追加 UNTRUSTED_EXTERNAL
_PLUGIN_FORCED_TAGS = CapabilityTag.UNTRUSTED_EXTERNAL | CapabilityTag.MUTATIVE

class _ExternalTaggedTool(Tool):
    """Wrapper that forces pessimistic tags on any externally loaded tool."""
    def __init__(self, inner: Tool, forced_tags: CapabilityTag):
        self._inner = inner
        self._forced_tags = forced_tags
    
    @property
    def static_tags(self) -> CapabilityTag:
        return self._inner.static_tags | self._forced_tags
    
    # 代理所有其他 Tool 方法到 self._inner
```

`mcp.py` 的 `MCPToolWrapper` 同样强制覆盖 `static_tags` 返回：
```python
@property
def static_tags(self) -> CapabilityTag:
    return CapabilityTag.UNTRUSTED_EXTERNAL | CapabilityTag.INFO_RETRIEVAL
```

在 `config.json` 中允许系统管理员通过 `capability_overrides.<tool_name>` 降级信任标签，该覆盖在 `get_effective_tags()` 中作为 `config_override` 参数注入。

---

### 变更 3：L1 规则引擎全面 Tag-Driven 化 + `_guard_command` 上卷收口

**为什么**：工具内部安全守卫与 L1 规则并存，是两个权威来源。`ExecTool._guard_command` 应上移到可统一测试、统一维护的 L1 规则层。

**决策**：

`verification.py` 新增规则 `R-SHELL-GUARD`（取代并整合 `ExecTool._guard_command`）：
- 检测所有具有 `SHELL_EXECUTION` 标签的工具调用
- 从调用参数中提取命令字符串（工具通过 `command_arg_name` 类属性声明，默认 `"command"`）
- 应用统一维护的 `_DENY_PATTERNS` 正则集合

现有 L1 规则重构为 Tag-Driven：
```python
def _check_rule_destructive(tool_calls, registry):
    """R-DESTRUCTIVE: 检测 DESTRUCTIVE 标签工具的参数合法性。"""
    for tc in tool_calls:
        tool = registry.get(tc.name)
        if tool and (tool.get_effective_tags(tc.arguments) & CapabilityTag.DESTRUCTIVE):
            # 统一安全参数校验，不再 hardcode 工具名
```

`ExecTool._guard_command` **物理删除**（不再保留）。`ExecTool.static_tags` 声明为 `SHELL_EXECUTION | MUTATIVE | DESTRUCTIVE`。

---

### 变更 4：精确化 R-DEP-FATAL（取代 R-SSRS-001，防止过度封锁）

**为什么**：原始 V1 设计封锁所有 `NETWORK_OUT` 工具，会导致 SSRS 失败后连报错通知邮件也发不出，系统变成不可观测的黑洞。

**决策**：封锁范围精确限定为 `INFO_RETRIEVAL` 标签（用于搜寻替代数据的幻觉行为），明确豁免 `SYS_COMMUNICATION` 标签（合法的故障通知行为）：

```python
def _check_rule_dependency_fatal(tool_calls, messages, registry):
    """
    R-DEP-FATAL: 检测到严重依赖失败后，封锁数据检索类工具，但豁免通知类工具。
    
    封锁标准: CapabilityTag.INFO_RETRIEVAL（搜寻替代数据 = 幻觉行为）
    豁免标准: CapabilityTag.SYS_COMMUNICATION（发送故障通知 = 合法行为）
    """
    dep_fatal_found = _scan_messages_for_dependency_fatal(messages)
    if not dep_fatal_found:
        return None
    
    violations = []
    for tc in tool_calls:
        tool = registry.get(tc.name)
        if not tool:
            continue
        tags = tool.get_effective_tags(tc.arguments)
        if (tags & CapabilityTag.INFO_RETRIEVAL) and not (tags & CapabilityTag.SYS_COMMUNICATION):
            violations.append(
                f"R-DEP-FATAL: 依赖 '{dep_fatal_found['dep_name']}' 已崩溃，"
                f"严禁调用 '{tc.name}' 搜寻替代数据。"
                f"请使用通信工具向用户汇报依赖不可用，然后终止任务。"
            )
    return violations or None
```

工具标签声明示例：
- `outlook.search` → `INFO_RETRIEVAL`（被封锁）
- `web_search` → `INFO_RETRIEVAL`（被封锁）  
- `outlook.send_email` → `SYS_COMMUNICATION | MUTATIVE`（豁免）
- `message` → `SYS_COMMUNICATION`（豁免）

---

### 变更 5：HITL 重构为 Tag-Driven

**为什么**：`hitl.py` 当前依赖 `get_risk_tier()` 方法，与 L1 规则体系使用的是不同的分类轴。废除 `RiskTier` 后 HITL 必须随之重构。

**决策**：`HITLMiddleware.pre_process` 重构为：

```python
async def pre_process(self, ctx: TurnContext) -> None:
    for tc in ctx.tool_calls:
        registry = getattr(ctx, "tool_registry_override", None) or self._agent.tools
        tool = registry.get(tc.name)
        if not tool:
            continue
        
        tags = tool.get_effective_tags(tc.arguments, config_override=self._get_config_tag_override(tc.name))
        is_high_risk = bool(tags & CapabilityTag.IS_HIGH_RISK)
        
        # Phase 33 SEC-BUW-1 保留：强制 HITL for script execution via exec
        # 此逻辑现在可以通过 evaluate_dynamic_tags 在 ExecTool 中实现
        # 当 command 包含 .py / .sh 后缀时动态追加 DESTRUCTIVE 触发此路径
        if not is_high_risk:
            continue
        
        # ... 后续 HITL 暂停与通知逻辑保持不变 ...
```

`ExecTool.evaluate_dynamic_tags` 覆盖：
```python
def evaluate_dynamic_tags(self, args: dict) -> CapabilityTag:
    cmd = str(args.get("command", "")).lower()
    if any(ext in cmd for ext in [".py", ".sh", ".ps1", "python -c", "node -e"]):
        return CapabilityTag.DESTRUCTIVE  # 触发强制 HITL
    return CapabilityTag.NONE
```

---

### 变更 6：务实的 `ExecutionPolicy`（取代 `SandboxProfile`）

**为什么**：在缺乏 OS 级隔离机制的便携 Agent 环境下，声明不可执行的 `network_allow_hosts` 是有害的安全幻觉。

**决策**：引入 `ExecutionPolicy`，只承诺可实际执行的约束：

```python
@dataclass
class ExecutionPolicy:
    """
    工具/技能级执行策略约束（仅声明可实际执行的边界）。
    
    注意：python_allow_network 仅对 PythonSandbox 中的 hooks.py 有效，
    通过 sys.addaudithook 拦截 socket.connect 实现。
    ShellSandbox 中的 exec 命令无法在 Python 层阻止网络访问。
    """
    timeout_seconds: int = 120
    python_allow_network: bool = False   # 仅 PythonSandbox 有效
    workspace_dir_restrict: bool = True  # PythonSandbox file path audit
```

`SandboxConfig` 支持按技能声明 `ExecutionPolicy` 覆盖（SKILL.md frontmatter）：
```yaml
execution_policy:
  timeout_seconds: 30
  python_allow_network: false
```

---

### 变更 7：Coordinator Worker CLI 安全注水

**为什么**：通过 HTTP body 传递沙箱约束可被有毒 payload 规避；Worker 启动后再施加约束存在 TOCTOU 漏洞。

**决策**：  
父进程（`CoordinatorManager.spawn()`）在 `subprocess.Popen()` 的 args 中注入安全标志：
```python
cmd = [
    sys.executable,
    "-I",                           # 已有：隔离模式
    "-m", "nanobot.agent.worker_process",
    "--timeout", str(policy.timeout_seconds),
]
if not policy.python_allow_network:
    cmd.append("--disable-network-socket")  # 新增
```

`worker_process.py` 主函数 **第一行**（在任何 import 之后、业务逻辑之前）解析 CLI 参数并挂载 `sys.addaudithook`：

```python
def _bootstrap_security(argv: list[str]) -> None:
    """CLI 安全引导：必须在所有业务逻辑启动前调用。"""
    disable_network = "--disable-network-socket" in argv
    if disable_network:
        def _block_socket(event, args):
            if event in ("socket.bind", "socket.connect"):
                raise PermissionError("Worker: Network access disabled by parent policy")
        import sys
        sys.addaudithook(_block_socket)

if __name__ == "__main__":
    _bootstrap_security(sys.argv)
    # ... 后续业务逻辑 ...
```

---

## 实施范围摘要

| 优先级 | 文件 | 变更类型 |
|:---:|:---|:---|
| P0 | `nanobot/agent/capability.py` | **[NEW]** `CapabilityTag` 枚举与 `ExecutionPolicy` 数据类 |
| P0 | `nanobot/agent/tools/base.py` | 废除 `RiskTier`，引入 `static_tags` / `get_effective_tags()` |
| P0 | `nanobot/agent/tools/shell.py` | 删除 `_guard_command`，声明 `static_tags` |
| P0 | `nanobot/plugin_loader.py` | 悲观默认包装器 `_ExternalTaggedTool` |
| P0 | `nanobot/agent/tools/mcp.py` | `MCPToolWrapper.static_tags` 强制返回 `UNTRUSTED_EXTERNAL` |
| P1 | `nanobot/agent/verification.py` | 新增 `R-SHELL-GUARD`，`R-DEP-FATAL` 精确化，其余规则 Tag-Driven 化 |
| P1 | `nanobot/agent/middleware/hitl.py` | 以 `CapabilityTag.IS_HIGH_RISK` 取代 `RiskTier.MUTATE_EXTERNAL` |
| P1 | `nanobot/agent/tools/registry.py` | 支持 `config_override` 查询接口 |
| P2 | `nanobot/agent/sandbox.py` | `run_hook()` 接受 `ExecutionPolicy` 参数 |
| P2 | `nanobot/agent/coordinator.py` | spawn 时注入 `--disable-network-socket` CLI 参数 |
| P2 | `nanobot/agent/sandbox_worker.py` | `_bootstrap_security(argv)` 优先执行 |
| P2 | `nanobot/config/schema.py` | `SandboxConfig` 更名 / 增加 `capability_overrides` 字段 |
| P3 | 所有内置工具（20 个）| 声明各自的 `static_tags` |
| P3 | `docs/adr/ADR-45-*.md` | 本文档 |

---

## 分阶段实施路径

**Phase 45A（基础设施，~12h）**：建立 `capability.py`，改造工具基类，实现悲观默认加载器，为所有内置工具声明 `static_tags`。

**Phase 45B（验证层收口，~10h）**：`verification.py` 全面 Tag-Driven 化（含新 `R-SHELL-GUARD`，精确 `R-DEP-FATAL`），`hitl.py` 重构，删除 `ExecTool._guard_command`。

**Phase 45C（执行策略层，~8h）**：`ExecutionPolicy` 集成到 `PythonSandbox`，Coordinator Worker CLI 注水，`worker_process.py` 安全引导。

**灰度策略**："先立新、平行运转、再废旧"。  
Phase 45A 期间，`RiskTier` 与 `CapabilityTag` 并行共存，`get_effective_tags()` 内部保持向后兼容。进入 Phase 45B 时，在删除 `RiskTier` 前先确认所有 HITL 路径已切换完成并通过回归测试。

---

## 验证计划

1. **单元测试 `tests/test_capability_tags.py`**
   - `CapabilityTag` 位运算正确性
   - `get_effective_tags()` 三层合并逻辑
   - 所有内置工具的 `static_tags` 声明不为 `NONE`

2. **Plugin 投毒防御测试**
   - 加载声明 `static_tags = NONE` 的恶意 Plugin，验证被强制升级为 `UNTRUSTED_EXTERNAL`
   - 上述工具触发的操作必须命中 HITL 暂停流程

3. **R-DEP-FATAL 精确性测试**（Phase 44 回归测试基础上扩展）
   - SSRS `DependencyFatal` → `outlook.search` 被封锁（`INFO_RETRIEVAL`）
   - SSRS `DependencyFatal` → `outlook.send_email` 不被封锁（`SYS_COMMUNICATION`）
   - SSRS `DependencyFatal` → `web_search` 被封锁（`INFO_RETRIEVAL`）

4. **Worker 沙箱不可提权测试**
   - 向 Worker HTTP 端点发送要求放宽网络权限的 payload
   - 验证 `sys.addaudithook`（已由 CLI 参数锁定）拦截 `socket.connect` 调用

---

## 未解决问题 / 未来展望

- **`config.json` 中的 `capability_overrides` 权限模型**（P2 细化）：降级 MCP 工具信任等级是否需要 secret 或签名机制，防止配置文件被篡改后武器化？

- **`R-SHELL-GUARD` 参数提取协议**：当 `SHELL_EXECUTION` 工具的命令参数键名不为 `"command"` 时（如未来新工具），如何在不修改 `verification.py` 的情况下声明参数名？建议引入 `command_arg_name: str = "command"` 类属性。

- **技能级 `ExecutionPolicy` 的 SSRS 集成**：`SkillsLoader` 读取 SKILL.md frontmatter 中的 `execution_policy` 字段并实例化为 `ExecutionPolicy`，传递给 `PythonSandbox.run_hook()`（Phase 45C 范畴）。

---

## 参考

- `docs/adr/ADR-44-cron-retry-ssrs-remediation.md` — SSRS 幻觉防线的直接前提（`R-SSRS-001` 被本 ADR 精确泛化）
- `docs/adr/ADR-42B-trace-id.md` — Trace-ID 系统（`parent_trace_id` 基础设施）
- `nanobot/agent/verification.py` — L1 验证规则引擎宿主（本次最重要的改造目标）
- `nanobot/agent/tools/base.py` — 工具基类（`RiskTier` 废除位置）
- `nanobot/agent/middleware/hitl.py` — HITL 审批网关（重构为 Tag-Driven）
- `nanobot/agent/sandbox_worker.py` — Python 沙箱 Worker（新增 `_bootstrap_security`）
