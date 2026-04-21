# 隐式 HITL 无头死锁与大文本上下文污染 (Headless HITL Deadlocks and Worker Context Bloat)

// Added: Phase 38B (参见 Phase 38B 多模型协作重构教训)

在多模型并发协作 (Manager-SubAgent) 架构中，若直接将主框架包含高级安全栅栏的 `AgentLoop` 搬迁至脱离中控的主机或子进程里，此时任何工具在检测到 `CapabilityTag.IS_HIGH_RISK` 并悬挂等待审批反馈（HITL Prompt）时，都会因为 Worker 没有合法的通道句柄接收交互，从而导致该次 SubAgent 任务永久悬挂假死。其次，Worker 输出的全量调试文本如直接回传，将引发父 Agent 产生灾难级别的上下文膨胀。

**避坑指南**：必须建立“多级防线代理隔离模式 (Proxy-Isolated Defense)”。
1. 对于权限继承，必须以硬性特征在底层拦截（如：在安全中间件检测 `chat_id.startswith("worker:")`，对所有 High-Risk 动作执行强行 Abort 而非 Suspend，并返回直白报错使 LLM 主动改变策略，而不是挂起等死）；
2. 对于上下文回传，必须内建 Outcome-Refining 降维流标管。在 `_announce_result` 返回父总线前，强制剥离无用的过程冗杂并通过轻量 LLM 层级蒸馏文本特征，只将 “Refined Synthesis” 送返核心。
