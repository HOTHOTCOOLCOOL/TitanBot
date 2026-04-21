# Progress Report

## ✅ Completed / Recently Delivered Phases

- [x] **Phase 37-38**: Manager-SubAgent Orchestration & Execution Trace Archive completed.
- [x] **Phase 44-45**: Cron/SSRS reliability and Dynamic Sandbox capabilities (L1 shell, ExecutionPolicy) shipped and verified.
- [x] **Phase 46**: Fallback-Driven Query Expansion & Offline Experience Consolidator delivered.
- [x] **Phase 47**: Paper Analysis & Architecture Audit (ADR-47) finished.
- [x] **Phase 48**: Dashboard Config Editor (masking sensitive keys) shipped.
- [x] **Phase 49**: In-Flight Context Condensation (IFCC) shipped (ADR-49).
- [x] **Phase 50**: Knowledge Graph Wiki Export (KG-Wiki) shipped (ADR-50).
- [x] **Phase 51-52**: K-V Decoupled Indexing (M-RAG) & Group-Aware Parallel Reasoning (GroupRAG) shipped (ADR-51-52).
- [x] **Phase 53**: Excel OLAP Automation using ExcelActuatorTool shipped (ADR-53).
- [x] **Phase 54**: BFF Proxy Gateway (Securing API Keys) shipped (ADR-54).
- [x] **Phase 55**: Architecture Maintenance (技术债还款) shipped (ADR-55).
- [x] **Phase 57**: Context Intelligence Upgrade (Waterfall Budget, Visual Silent Downgrade) shipped and verified (ADR-57).
- [x] **Phase 58**: Documentation Architecture Refactoring (Docs-as-Context) shipped (ADR-58).
- [x] **Phase 61**: Command Control Tiering - Isolated HITL vs Destructive (ADR-61) shipped and verified.
- [x] **Phase 62 & 59**: Azure OpenAI Migration Security Hardening & Antigravity Planning Gate integrated.
  - ✅ Schema 全链路 Null 合规: 追踪 `add_message()` 到 `build_messages()`，保证带 tool_calls 时 content 强制为 null
  - ✅ Worker/Cron 防御降级: 增设 `AzureContentFilterException` 在 400 content_filter 报错时执行优雅解绑（Graceful Pause），不无限重试
  - ✅ 严格身份边界（伪装消融）: 删除旧版利用 user role 发送 `[System:...]` 的注入模型，改用虚拟助手与虚拟 Tool Call 安全回传系统事件。软化强硬 HITL 提示文本
  - ✅ Antigravity - Planning Gate V1: 实装 `write_artifact` 强制实施计划写板与 HITL 审查；实装 `update_task_progress` 进度透明化；实装 TaskTracker 最末 3 步状态直注 System Prompt
  - ✅ Antigravity - 防御规则池: 实装 `KI Rules` 战术规则短阵，实现匹配关键字时的微小上下文注入；新增测试断言保证单规则不越界 500 字符
  - ✅ 双轨制日志边界确立：Host Agent 体系强制 loguru，Tool Payload IPC stdout 豁免并 Ruff 保护
  - ✅ 全域 print() 审计清零：`rpa_executor.py` (15处), `screen_capture.py` (3处), `channels/weixin.py`, `config/loader.py`
  - ✅ Async CancelledError 守卫：`browser_use_worker.py`, `rpa_executor.py` async 路径加固
  - ✅ 统一异常类库：新建 `nanobot/utils/exceptions.py` (`NanobotError` / `ProviderExecutionError` / `ToolExecutionError` / `SessionPersistenceError`)
  - ✅ ExcelActuator COM 精准防御：`self._last_excel_pid` + `win32process.GetWindowThreadProcessId` + 精准 `taskkill /PID`
  - ✅ Ruff 自动修复：1624 个 import/whitespace 问题消除；per-file-ignores 保护 IPC 脚本
  - ✅ ARCHITECTURE.md 经验法则 #23 & #24 沉淀
- [x] **Phase 63**: `execute_phase` 工作流回归测试强化 (ADR-63) 完成。经 Harness 5 阶辩证，废弃 LLM 幻觉映射，引入绿色基线铁律 + Zone A/B/C 架构划区 + pytest(L1)/Codex(L2) 双层串联门控。`execute_phase.md` 精准更新，ARCHITECTURE.md 追加经验法则 #25。
- [x] **Phase 56**: Pre-flight Skill Verifier (PSV) (ADR-56) 极值打磨后交付。经过严酷的 20 轮“同进程安全限制”攻防战，放弃粗筛黑名单，确立“零能力”执行环境：极限收缩 Allowlist（7 个纯数据包）、封锁全体魔术方法与单下划线私有桥、切断内置动态反射与 format_map 解析后门，实现同进程环境下的 AST 安全隔离闭环。

## 📅 Next Steps / Backlog (后续计划)


- [ ] **Phase 60: Enterprise Gateway LiteLLM Migration** *(P1, ADR 已定稿，待进入编码实施阶段)*
  - 来源: Phase 54 BFF 自研网关运营反思 + Harness 5-阶辩证工作流 (ADR-60 定稿)
  - 核心决策 (经 Harness 5阶辩证审查敲定):
    - **迁移零停机**：`/key/generate` 强制透传旧 Token 字符串，200 人客户端无感知，`config.json` 零修改
    - **基础设施即代码**：`bff/docker-compose.yml` 三容器栈（LiteLLM + Postgres `15-alpine` + `pg-backup` sidecar）
    - **版本钉死**：`litellm:v1.40.23` 精确钉死，禁用 `latest`，防止 schema 破坏性升级
    - **每日自动备份**：`db-backup` sidecar 无人工干预，保留 7 天，数据安全兜底
    - **幂等迁移脚本**：`bff/scripts/import_users_to_litellm.py` 先查重再创建，容错记 `failed_users.txt`
    - **决策放弃项**：预算硬上限 Budget Cap（无需求）、阈值预警邮件（超过内网范围）、Nginx 反代（破坏极简原则）、动态模型列表（客户端"越权报错"体验可接受）
  - 详见 `docs/adr/ADR-60-enterprise-gateway-litellm-migration.md`
  - **状态**: ADR 已定稿，基础设施文件已生成，待进入 Docker 部署验收阶段



