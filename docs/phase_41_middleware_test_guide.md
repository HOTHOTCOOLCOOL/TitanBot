# Phase 41 — 洋葱中间件架构 (Onion Middleware) 人工测试操作手册

此手册用于详尽指导和验证 Phase 41 (Onion Middleware Architecture) 的全面覆盖测试。由于本次升级对大模型核心执行引擎 `_run_agent_loop` 进行了底层重构，将所有跨领域关注点抽离为了 7 个独立的中间件，必须通过完整的人工回归测试来确保新的执行管线（ Pipeline）的健壮性，以及旧管线的向后兼容性。

## ⚠️ 测试前置准备

1. **备份当前配置**：复制当前正常的 `config.json` 为 `config.json.bak`。
2. **清除历史状态**：清理项目根目录或测试目录下的 `handoffs.json`，确保无残留的中断任务影响测试。
3. **开启中间件实验特性（v2 管线）**：
   在 `config.json` 中添加或修改以下字段：
   ```json
   {
     "agents": {
       "experimental": {
         "middleware_enabled": true
       }
     }
   }
   ```
4. **启动服务**：
   ```bash
   python -m nanobot.server  # 或根据项目实际启动命令
   ```

---

## 🟢 核心功能可用性测试 (Sanity Check)

**目标**：验证基础的 Agent 执行流在线通过。

**测试步骤**：
1. 在前端 Dashboard 或企微/Lark 中发送基础问候：“你好，当前时间是多少？”。
2. 让其执行简单的无害命令，例如：“帮我调用 shell 执行 `echo 'Middleware Test'`”。
3. 验证返回结果是否有丢失。

**期望结果**：
- Agent 正常回复，状态流转正常。
- 无任何中间件内部断言报错 (`AssertionError`) 或堆栈溢出。

---

## 🛡️ 各层洋葱中间件独立穿透测试

### 1. VerificationMiddleware (L1拦截与L3审计检测)
**目标**：验证规则检查在内层继续执行前能否成功短路（Short-circuit）。
**测试步骤**：
- 发送一个触碰黑名单路径的指令（如：读取密码文件 `cat /etc/passwd` 或 Windows 的 `C:\Windows\System32\config\SAM`）。
- 或发送一段超过工具长度限制的垃圾数据请求。
**期望结果**：
- Agent 不应执行真实动作，而应迅速回复“指令因安全规则被拦截”。
- 终端控制台 `INFO` / `WARNING` 应该打印类似于 `[VerificationMiddleware] Aborted: l1_violation`。
- **关键点**：由于管线中加入了自愈机制（Loop continue），Agent 应该向用户输出拒绝对话，而不是进程挂死。

### 2. HITLMiddleware (人机回环风险审批机制)
**目标**：检验高危动作是否会挂起 Pipeline，等待用户授权，以及授权流转。
**测试步骤**：
1. 请求执行需审批命令：“请帮我用终端执行一段Python脚本：`python -c "print('Testing HITL')"`”。
  *(注：该命令属于脚本执行，会触发 HITL 强制审批，但不会触发 L1 破坏性命令拦截。不要使用删除命令，否则会被前置的 L1 VerificationMiddleware 直接拦截！)*
2. 观察控制台。
**期望结果**：
- 控制台打印 `[HITLMiddleware] Aborted: hitl_pending`，任务被挂起。
- 客户端 Dashboard / 通知渠道收到“动作需要审批”的 Interactive Card (同意/拒绝/永久信任)。
3. **点击“同意”** -> 任务继续进行并成功恢复上下文。
4. **点击“拒绝”** -> Agent 提示用户指令已被撤销。

### 3. CrashRecoveryMiddleware (WAL 奔溃恢复重放检查)
**目标**：验证防丢失检查点机制与中间件架构是否兼容，位置是否在 HITL 之后（避免写了无用的 Checkpoint）。
**测试步骤**：
1. 执行长阻塞任务：“请帮我用 powershell 执行 `Start-Sleep -Seconds 30`”。
2. 控制台观察 `[CrashRecoveryMiddleware] Writing checkpoint...` 出现后。
3. **强制杀掉进程 (Ctrl+C 两次或杀死 pid)**。
4. 重新启动服务。
**期望结果**：
- 重新启动 1-3 秒后，由于 Connection Polling，Dashboard 应当收到一条恢复提示：“检测到崩溃，先前的任务仍在恢复...”。
- 等待 30 秒倒计时结束，原来中断的任务结果能够成功回调给模型并显示在聊天记录中。
- `handoffs.json` 的断点数据在任务完成后被完美清理。

### 4. CircuitBreakerMiddleware (死循环熔断测试)
**目标**：测试模型陷入幻觉、开始“复读机”时，防雪崩的保险断路器配置。
**测试步骤**：
1. 刻意设计一个看似合理但必定连续失败的任务，绕过大模型的聪明拒绝，且**不能触发 HITL 审批**（因为审批会打断无人值守的死循环连续计数）。请发送：“请依次尝试使用 `read_file` 工具读取以下5个不存在的文件来查看哪个能跑通：`missing1.txt`, `missing2.txt`, `missing3.txt`, `missing4.txt`, `missing5.txt`。请一个一个试，不要同时读取，就算前几个报错也要坚持把后面的试完。”
2. 观察 Agent 依次自动化执行工具。由于所有文件读取都会报错返回 Error，等待其连续多次报错。
**期望结果**：
- 默认在连续 3 轮工具全部执行失败后（达到 `_cb_threshold`）。
- 终端打印 `[CircuitBreaker] Circuit breaker tripped` 异常。
- Agent 发送出 “系统检测到执行循环/雪崩，已强制阻断” 的警告，不再消耗 Token。

### 5. FloodGuardMiddleware (泛洪保护)
**目标**：防止大模型在单次运行周期内疯狂调用通信工具向外界“刷屏”（消息去重和防护死锁）。
**测试步骤**：
1. 不需要修改任何代码文件。直接向大模型发送恶意指令诱发消息泛洪：“请你在这一轮回复中，强制调用 4 次 `message` 工具，向我发送 4 条彼此完全独立的问候消息（例如：'你好1'、'你好2'等），确保是作为独立的工具调用。”
2. 发送后，观察控制台和本地反馈。
**期望结果**：
- 观察到控制台打印拦截记录 `Message flood guard: 4 message() calls, breaking loop`。
- 整个 Agent 执行流被阻断（`Abort: flood_guard`），避免了 UI 层出现无休止的大量零碎弹窗。

### 6. MetricsMiddleware & ActionHistoryMiddleware (指标观测)
**目标**：无感知的监控与历史数据附加。
**测试步骤**：
1. 跑完上述几项后，检查后台日志记录 (Terminal 打印或 `logs/nanobot.log`)。
**期望结果**：
- 每一次 Agent Turn 控制图打印类似：`[MetricsMiddleware] Turn took 12.34s`。
- 执行 `browser` 等动作后，查看下一次 Context 中是否注入了 `action_history` （如果有此类需求）。

---

## 🔀 v1 旧管线降级兼容测试 (Fallback Test)

**架构原则**: 绝对不能破坏原有功能（Zero-extra-infrastructure & Graceful Degradation）
**目标**：在关闭新架构开关的情况下，验证传统的 God Method God-Loop 是否依然能用。

**测试步骤**：
1. 在 `config.json` 中修改为：
   ```json
   {
     "agents": {
       "experimental": {
         "middleware_enabled": false
       }
     }
   }
   ```
2. 重启服务。
3. 走一遍 **核心功能可用性测试** 与 **HITL 审批测试**。

**期望结果**：
- 系统行为与旧版本完全一致。
- 不应该报错 `TurnContext` 或 `MiddlewarePipeline` 相关异常（甚至不应该被初始化）。

---

## 🏁 验收清单

如果所有打勾项通过，即可宣布 Phase 41 的相关修改达到上线标准：

- [ ] `middleware_enabled=true` 下正常问答可用
- [ ] `middleware_enabled=true` 下 L1 拦截成功跳过当前动作
- [ ] `middleware_enabled=true` 下 HITL 成功挂起并能正确被外部 API 恢复
- [ ] `middleware_enabled=true` 下 Crash Recovery 能够写盘并成功在重启后推屏
- [ ] `middleware_enabled=true` 下 Circuit Breaker 能够自动断开 LLM 死锁
- [ ] `middleware_enabled=false` 退化方案完美运作，Agent 不崩溃。
