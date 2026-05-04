# Epoch 61: Command Control Tiering & Destructive Isolation

**Date:** 2026-04-19
**Status:** Completed
**Manual Acceptance:** Passed on 2026-05-03

## 人工验收结果 (2026-05-03)

- **场景 1 / PERMIT**：`rpa(action=click)` 点击屏幕中心，无高危审批弹窗，实际执行成功并返回物理点击坐标。为消除执行层误伤，本轮同时补入了 PyAutoGUI FailSafe 角落恢复逻辑，确保“鼠标已停在急停角”不会把普通中心点击误报成权限失败。
- **场景 2 / HITL**：`rpa(action=press, keys=['win'])` 被正确提升为 `SENSITIVE`，执行前挂起并弹出 `Action Required`。人工回复 `Reject` 后动作终止，未继续按下 Win 键。
- **场景 3 / L1 HARD BLOCK**：`exec("echo test | cmd")` 在工具执行前被安全层直接拦截，没有进入审批路径。运行日志记录为 2 条 L1 violation，符合现有 pipe-to-shell 规则与 Tag-Driven destructive guard 的双保险设计预期。
- **噪音说明**：同批日志中的 `nanobot.channels.weixin:start:532 ConnectError` 属外部网络/翻墙环境问题，不计入 Phase 61 验收结论。

## 架构变化深度剖析 (Architectural Deep Dive)

本阶段落实了 `ADR-61`，彻底解耦并细分了 Agent 对高危和毁灭性操作的拦截分层控制，以解决旧有 `R-SHELL-GUARD`（只限定于 SHELL_EXECUTION 且无缓冲地带）的痛点，避免大模型幻觉或者 RPA 等工具“走后门”执行超危操作。

### 1. 三度控制体系的落脚
引入 `CapabilityTag.SENSITIVE` ，形成三层次管控：
1. **PERMIT (放行)**：只含有 `MUTATIVE` 或一般操作。引擎直接调用底层沙箱放行。比如普通 UI Click。
2. **HITL (软拦截 / Human-In-The-Loop)**：判定依据是命中 `IS_HIGH_RISK`（即包含 `SENSITIVE | DESTRUCTIVE | UNTRUSTED_EXTERNAL`）。在这里，操作虽然危险但是人类可通过确认允许执行。
3. **L1 HARD BLOCK (硬阻断)**：所有命中 `DESTRUCTIVE` 落到 L1 层通过 `_check_rule_destructive_guard` 的指令，无论工具如何打包、无论人类是否批准（实际上甚至走不到批准那一步），将在真正执行前静态硬阻断并向回抛出错误，强制 LLM 进行重设和思考。

这种模型容忍了由于层叠导致的兜底穿越错误——假设 L1 失灵，也会落入 HITL 的二次人类判断流程。

### 2. 修饰热键嗅探与语义保护 (Dynamic RPA Modifier Sniffing)
改变原有的基于“按键枚举黑名单（如 ctrl+alt+delete）”去试图防御 RPA 工具失控的做法。在 `rpa_executor.py` 的 `evaluate_dynamic_tags` 方法中引入嗅探：
- 只要出现 `win`, `command`, `cmd`, `fn` 或者组合键如 `alt+f4` 等具备强系统级破坏特征的意图，立刻赋予 `SENSITIVE` 及拦截。
- `type` 过长 (> 800字)，也被打标签。因为这代表模型可能放弃正常 `exec` 脚本转而在前台窗口缓慢敲打恶意注入脚本，进行规避（Evade Guard）。

### 3. Worker/Cron 脱敏保护
任何全局修改如果破坏了无 UI 后台（Worker 节点）的独立存活性都是不被允许的（ADR 中反复强调）。
目前的实现是：保留诸如发邮件工具、读写外设的工具的静态 `MUTATIVE` 标签不予更改，确保计划任务在夜晚能顺畅运转。如果有需要邮件审批的业务（例如 HR 或者财务相关发邮件）则把责任推向部署侧，通过 `config.yaml` 注入 `capability_overrides` 来添加 `SENSITIVE`。

## 历史包袱处置 (Legacy Cleanup)
- **`R-SHELL-GUARD` 弃用**：去除了旧版必须指定 `SHELL_EXECUTION` 等强关联条件的拦截，将鉴权的责任分散给每个 Tool 本身的 `get_effective_tags()` 返回结果，真正做到了“只认标（Tag），不认枪（Tool）”。对于没有 registry 的旧代码，fallback 为 `_DESTRUCTIVE_PATTERNS`。

## 后续建议 (Future Thoughts)
可以尝试为沙箱系统增加内存访问级别的底层白盒审查（Hook ctypes），以将物理层（RPA 操作等）做进一步的强制封顶边界（比如禁止鼠标物理离开特定的应用窗口矩阵），目前仍在基于纯语义或人类观察校验。 
