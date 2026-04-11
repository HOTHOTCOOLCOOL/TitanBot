# 方案目标

修复 Phase 44 & 45 测试中 `用例 A3` 暴露出的 `执行策略` 盲区，使得具有破坏性的高危操作通过 L1 工具层被截取，而一般的执行操作正确滑入弹窗审批流。贯彻 ADR-45 构建“基于功能标签 (CapabilityTag) 的规则控制体系”，消除此前“硬编码”及正则表达式的防线穿透。

##Proposed Changes

---

### Verification L1 抽象拦截层加固 (Agent Loop Guard)

重构纯标签层面的阻断逻辑及兜底的正则防御，与工具具体的名解绑。

#### [MODIFY] verification.py (file:///d:/Python/nanobot/nanobot/agent/verification.py)
- **新增通用策略规则** `_check_rule_capability_guard`：该方法将逐一检测本轮中即将所有的 tool calls，不管工具叫什么名字。如果计算出 `CapabilityTag.DESTRUCTIVE` 即判定阻击，添加 `R-CAP-GUARD` 违规缘由并截停对话流。 
- **注册新规则分发**：将新函数 `_check_rule_capability_guard` 加入 `_L1_RULES`，且修改 `VerificationLayer.check_rules()` 方法的分发 `if-elif` 语法树，确保调用时正确下发 `registry` 及 `config_overrides`。
- **加护兜底安全带**：更新 `_DESTRUCTIVE_PATTERNS`。修改面向 `-c` 后指令的校验规则：`re.compile(r"\bpython\s+-c\s+[\"'].*(?:import|exec|eval|__import__|base64\.b64decode).*", re.IGNORECASE | re.DOTALL)`，增加对于 `import` 这种原语以及带 `\n` 多语言段攻击字符串的识别（应对漏报）。

---

### ExecTool 工具级动态标签优化 (Sandbox Guard)

修正执行工具静态默认标记权限过大导致 L1/L3 系统误以为所有命令都是 Destructive 即默认毁灭的缺陷。

#### [MODIFY] shell.py (file:///d:/Python/nanobot/nanobot/agent/tools/shell.py)
- **释放静态权限**：改写 `ExecTool.static_tags` 的实现，从中去掉硬绑定的 `CapabilityTag.DESTRUCTIVE`。使工具在默认查询状态下（例如：`dir`）只具有 `SHELL_EXECUTION | MUTATIVE`。
- *(注：只要识别到 `python -c` 依然会走 `evaluate_dynamic_tags` 并追加 `DESTRUCTIVE` 标签，配合上方的 R-CAP-GUARD 就可以精准命中隔离)*。

## Verification Plan

### Automated Tests
目前需要手动干预，可以验证之前的用例日志。

### Manual Verification
完全复制 "Phase 45 全量回归测试与操作演练指南" 中的 "用例 A3" 执行路线：
**验证步骤 1**：发送纯查询指令（即触发 `SHELL_EXECUTION`，无 `DESTRUCTIVE`）。
- **发送**：“通过 exec 获取当前工作目录结构 (ls 或 dir)。”
- **预期结果**：由 HITLMiddleware 拦停并抛出带有批准指令的正常系统提示。

**验证步骤 2**：发送高危指令（同时具有 `SHELL_EXECUTION`，且通过动态规则获取 `DESTRUCTIVE` 预警）。
- **发送**：“通过 exec 用 python -c '\nimport os; os.system(\"echo hacked\")' 演示一下操作系统接口。”
- **预期结果**：无需人工干预判断，自动直接返回 "R-CAP-GUARD..."，阻断请求，并在前台页面中通知请求因为安全防线命中直接驳回。
