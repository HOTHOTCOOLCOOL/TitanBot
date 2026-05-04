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
- [x] **Phase 61**: Command Control Tiering - Isolated HITL vs Destructive (ADR-61) shipped, regression-hardened, and manually accepted.
  - ✅ 2026-05-03 人工验收通过（`docs/tests/manual_guides/phase_61_manual_test_guide.md`）：场景 1 `rpa(action=click)` 点击屏幕中心直接放行；场景 2 `rpa(action=press, keys=['win'])` 正确进入 HITL 并在 `Reject` 后终止；场景 3 `exec("echo test | cmd")` 无审批路径，直接被 L1 安全层拦截。
  - ✅ RPA 执行层补强：修复 PyAutoGUI FailSafe 角落误伤普通点击的问题，非角落目标会先脱离急停角再继续执行，避免把执行层 emergency stop 误判成 Phase 61 权限回归。
  - ✅ 定向回归：`.venv311\\Scripts\\python.exe -m pytest tests/test_rpa_failsafe.py tests/test_rpa_find.py tests/adversarial/test_rpa_bounds.py -q` → **24 passed**
- [x] **Phase 62 & 59**: Azure OpenAI Migration Security Hardening & Antigravity Planning Gate integrated.
  - ✅ Schema 全链路 Null 合规: 追踪 `add_message()` 到 `build_messages()`，保证带 tool_calls 时 content 强制为 null
  - ✅ Worker/Cron 防御降级: 增设 `AzureContentFilterException` 在 400 content_filter 报错时执行优雅解绑（Graceful Pause），不无限重试
  - ✅ 严格身份边界（伪装消融）: 删除旧版利用 user role 发送 `[System:...]` 的注入模型，改用虚拟助手与虚拟 Tool Call 安全回传系统事件。软化强硬 HITL 提示文本
  - ✅ Antigravity - Planning Gate V1: 实装 `write_artifact` 强制实施计划写板与 HITL 审查；实装 `update_task_progress` 进度透明化；实装 TaskTracker 最末 3 步状态直注 System Prompt
  - ✅ Antigravity - 防御规则池: 实装 `KI Rules` 战术规则短阵，实现匹配关键字时的微小上下文注入；新增测试断言保证单规则不越界 500 字符
  - ✅ 2026-05-03 人工验收进展：**Phase 62 已通过**。其中后端 Cron 熔断探针 `tests/verify_phase62_content_filter_fuse.py` 跑通，确认 `Cron: job '...' reached fatal error state (Content Filter)`、`enabled=false`、`nextRunAtMs=null`、且无二次重试；Planning Gate 也已通过人工链路验证。
  - ✅ 2026-05-03 人工验收进展：**Phase 59 KI Rule 注入已通过**。日志已实锤出现 `L0: Injected KI rule excel-com.ki.json`，且模型行为与规则一致。
  - ⏳ 2026-05-03 当前剩余验收口：**Phase 59 TaskTracker 透明化** 已补齐 runtime wiring、探针脚本与回归测试；下一步仅需在 dashboard/live 会话里复测一次“你刚才进行到哪一步了？”并观察 `L0: Injected TaskTracker status for ...`。
  - ✅ 2026-05-03 retrospective 固化：已把本轮教训回写到 ADR-62 与 workflow 护栏，明确“回答像对不等于机制生效”，并把 `Runtime Artifact Parity Checklist`、`Proof Signals`、`False Positive Success Paths` 升级为设计 / 执行阶段的强制项。
  - ✅ 双轨制日志边界确立：Host Agent 体系强制 loguru，Tool Payload IPC stdout 豁免并 Ruff 保护
  - ✅ 全域 print() 审计清零：`rpa_executor.py` (15处), `screen_capture.py` (3处), `channels/weixin.py`, `config/loader.py`
  - ✅ Async CancelledError 守卫：`browser_use_worker.py`, `rpa_executor.py` async 路径加固
  - ✅ 统一异常类库：新建 `nanobot/utils/exceptions.py` (`NanobotError` / `ProviderExecutionError` / `ToolExecutionError` / `SessionPersistenceError`)
  - ✅ ExcelActuator COM 精准防御：`self._last_excel_pid` + `win32process.GetWindowThreadProcessId` + 精准 `taskkill /PID`
  - ✅ Ruff 自动修复：1624 个 import/whitespace 问题消除；per-file-ignores 保护 IPC 脚本
  - ✅ ARCHITECTURE.md 经验法则 #23 & #24 沉淀
- [x] **Phase 63**: `execute_phase` 工作流回归测试强化 (ADR-63) 完成。经 Harness 5 阶辩证，废弃 LLM 幻觉映射，引入绿色基线铁律 + Zone A/B/C 架构划区 + pytest(L1)/Codex(L2) 双层串联门控。`execute_phase.md` 精准更新，ARCHITECTURE.md 追加经验法则 #25。
- [x] **Phase 56**: Pre-flight Skill Verifier (PSV) (ADR-56) 极值打磨后交付。经过严酷的 20 轮“同进程安全限制”攻防战，放弃粗筛黑名单，确立“零能力”执行环境：极限收缩 Allowlist（7 个纯数据包）、封锁全体魔术方法与单下划线私有桥、切断内置动态反射与 format_map 解析后门，实现同进程环境下的 AST 安全隔离闭环。
- [x] **Phase 64**: Architectural Security Hardening (架构级防线与测试闭环清理) 经过多轮回炉终极交付，彻底打通 ExitKind 契约。
- [x] **ADR-66: Pre-Phase 37 Security & Resilience Hardening** *(经 Harness 5-阶辩证工作流落盘)* 交付6项核心修复:
  - ✅ **V1 (P0)**: `verification.py` — L1 路径防御引入 `os.path.realpath` 绝对路径解析，修复 `../` 路径穿越攻击与 Symlink/Junction Point 绕过；`write_file`/`edit_file` 改用 `startswith` 前缀匹配；`exec` 保持正则匹配（shell 命令不做路径解析，避免防线崩溃）
  - ✅ **V2 (P0)**: `rpa_executor.py` — `_check_bounds` 签名重构为 `tuple[bool, str|None]`，解耦 Stale 上下文警告（放行）与真正越界（硬阻断），彻底消除"60秒后所有 RPA 操作锁死"回归风险
  - ✅ **V3 (P0)**: 明确放弃对 `type` 操作的内容正则扫描（安全剧场——4种已知绕过方式），终极防御边界交由 Phase 64 物理沙箱 Zone Containment (ADR-64) 负责，此决策已写入 ADR 防止未来误返
  - ✅ **D1 (P1)**: `loop.py` — `_detect_fuzzy_loop` 引入 `json_repair.loads()` 替代 `json.loads()`，异常由 `debug`（生产环境静默）升级为 `logger.warning`（可见）
  - ✅ **D2 (P1)**: `loop.py` — `_normalize_tool_result` 改用 10/90 尾部偏重截断策略（保留 90% 尾部确保报错链存活）；移除 `json.loads()` 大文本解析（消除 OOM 风险与尺寸溢出漏洞）
  - ✅ **D3 (P1)**: `verification.py` — `_check_rule_ssrs_fatal` 改用三级无 `DOTALL` 正则降级匹配，杜绝"用户提问 DependencyFatal 时误触发规则"的跨消息误报
  - ✅ **对抗性测试套件**: 新增 4 个 `tests/adversarial/` 测试文件，覆盖路径穿越、RPA 越界解耦、截断安全、SSRS 误报全部攻击向量
  - ✅ **L2 Codex 审查加固** *(本次会话)*:
    - 拆分 `resolved_prefix`/`resolved_norm`，修复精确文件路径 deny pattern 被尾斜杠绕过 (A1)
    - `post_reflect` 的 `exit_kind` 从默认 `"success"` 改为必传参数，消除 fail-open API (B1)
    - basename 提取改用 `os.path.normpath` 统一处理混合分隔符 (B2)
    - 新增 3 个 L2 回归测试钉住路径拆分意图
  - 最终验收: **191 passed, 0 failed** (Zone A 全绿，经 3 轮 L2 Codex 审查通过)
  - 详见 `docs/adr/ADR-66-phase37-security-hardening.md`
- [x] **ADR-67: KnowledgeMapTool — KG 拓扑导航工具** *(经 Harness 5-阶辩证工作流落盘)*
  - 来源: CORPUS2SKILL 论文分析（arXiv 2604.14572v1）的工程价值提炼
  - 核心决策: 实现 `knowledge_map` 工具（非 Skill），基于 KG Degree Centrality 识别领域枢纽，mtime 懒缓存，Search-First 永远是 P0 路径
  - ✅ 新建 `nanobot/agent/tools/knowledge_map.py`
  - ✅ 注册至 `nanobot/agent/tool_setup.py`
  - ✅ `TOOLS.md` 审计条目 #20（20/20 Compliant）
  - ✅ `tests/unit/test_knowledge_map.py` — 4 个单元测试（A2/A3/A4/A5 验收项）
  - ✅ **Bugfix (Harness 误操作遗留)**: 修复截断后长度 = `_MAP_OUTPUT_CAP + len(suffix)` 的越界 Bug，重写极长实体名测试消灭“受限于 Hub 数量无法触发截断”的假阳性绿灯漏洞。
  - ✅ 2026-05-04 人工验收通过（`docs/tests/manual_guides/phase_67_manual_test_guide.md`）：Scenario 1 PASS；Scenario 2 PASS WITH NOTE（运行时以 `knowledge_map` + `memory` 并行 fan-out 体现 fallback 意图，而非严格串行链）；Regression Target 1 PASS（`exec("echo hello")`）；Regression Target 2 PASS（dashboard 对大 `tasks_tracking.json` 输出显示 `[OUTPUT TRUNCATED]`）。
  - 详见 `docs/adr/ADR-67-knowledge-map-tool.md`
- [x] **Job 20260426: Copilot Studio External Consultant Tool**: `consult_copilot_studio` 已完成配置契约、内建注册、Direct Line mock 回归和人工验收手册沉淀，具备进入真实租户联调的交付状态。
- [x] **Job 20260503: ReasoningSkill KG Prompt Budget**: `reasoning_template` 现已作为 Knowledge Graph 单一真源实体稳定持久化，`context.py` 在注入时对其施加严格 1000 字符预算截断，且 `rebuild_entity_index()` 不再抹掉人工维护的类型元数据。
- [x] **Job 20260503: Phase 68 Paper Integration Slice**: `loop.py` 的 pre-dispatch P0 可观测 gate 与 `verification.py` / `verification_mw.py` 的 workspace 写边界拦截已经落地，并在 `tests/test_phase68_paper_integration.py`、Zone A 回归集和限域 `auto_reviewer.py` 验收中于 2026-05-04 全部通过。

## 📅 Next Steps / Backlog (后续计划)

- [x] **Phase 65: Extreme Technical Debt Annihilation & L2 Automation** *(Completed as contract / regression slice on 2026-05-04)*
  - 核心交付: `execute_phase.md` 已升级为 Artifact-First 协同协议，新增 `codex_handoff.md` / `codex_result.md` / `codex_feedback.md` 三件套，默认“自动派工优先、人工转交 Artifact 兜底”，不再让用户充当消息总线。
  - 核心交付: `nanobot harness start/status/advance` 与 `nanobot/agent/harness/` lite-only orchestration 已落地，A1-A6 对应 CLI 回归通过，且 `auto_reviewer.py` 已支持按 Artifact 限域的本地 L2 fallback 以避免验收被外部 provider 长时间卡死。
  - 核心交付: 2026-05-04 新增 `tests/test_phase65_execute_phase_contract.py`，把 `execute_phase` 的 handoff/result/feedback 契约与代表性 Phase 65 job 回执一致性锁进回归；联同 `tests/test_harness_cli.py`、`tests/test_auto_reviewer.py` 执行 `.\\.venv311\\Scripts\\python.exe -m pytest tests/test_commands.py tests/test_cli_input.py tests/test_harness_cli.py tests/test_auto_reviewer.py tests/test_phase65_execute_phase_contract.py -W ignore -v` -> **24 passed**。
  - 结论: 当前 manual guide 的剩余价值已收敛到真实多会话 / HITL / provider / sandbox 环境验收；核心 contract 不再需要每次靠人工重复确认。
  - 拆分说明: 剩余的 runtime orchestration / auto-dispatch / approval-scoped automation 已从 Phase 65 中拆出，转入 Phase 68 独立推进。

- [ ] **Phase 68: Runtime Dispatch & Approval-Scoped Orchestration** *(New P0 successor to Phase 65)*
  - 核心目标: 实装 Codex 派工器、`codex_result.md` 完成信号检测器、以及 plan-scoped approval token，真正把 Phase 65 已落地的文档协议接入自动执行链。
  - 验收重点: 真实多会话 / HITL / provider / sandbox 环境下的自动派工、回执检测、返工闭环与防暴走拦截。
  - 非目标: 不重做 Phase 65 已经锁定的 Artifact-first contract、A1-A6 CLI 边界或已有 L2 fallback 回归。
  - 护栏机制: 设计 Human-In-The-Loop 人工干预防暴走拦截，避免长上下文下的模型自循环破坏。


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

- [ ] **Backlog: Cross-Platform Sensitive Path Normalization** *(P2, L2 Codex 审查残留 B2)*
  - 来源: ADR-66 L2 审查第二轮 B2 残留
  - 问题: `_SENSITIVE_PATHS_RESOLVED` 在 Windows 上将 `/etc/`、`/usr/bin/` 等 Linux 路径通过 `realpath()` 解析到当前盘根目录（如 `D:\etc\`），导致策略语义漂移和潜在误拦截
  - 建议方案: 按 `sys.platform` 分别构造敏感路径前缀集，或将 bare keyword（如 `system32`）与 absolute prefix 分开处理
  - 参考: `nanobot/agent/verification.py` L85-117 (`_resolve_sensitive_paths()`)
