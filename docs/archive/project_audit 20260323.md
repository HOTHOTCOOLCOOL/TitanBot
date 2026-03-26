# Nanobot 项目全面审计报告

> 截至 2026-03-23 | 基于全部 7 份文档 + 源码结构 + 93 个测试文件深度审查

---

## 📋 一、手动测试清单（完整版）

> **以下合并了 [progress_report.md](file:///d:/Python/nanobot/progress_report.md) 中的 A/B/C/D 四大类，增补了 Phase 26-28 缺失项。**

### A. 阶段功能 — 自动测试通过，缺手动验证

| # | Phase | 功能 | 自动测试 | 手动验证 |
|---|-------|------|---------|---------|
| A1 | 22A | SK1: AI-First Skill 描述重写 (11 个 SKILL.md) | ✅ 27 pass | [ ] 验证 LLM 实际触发匹配 |
| A2 | 22A | SK2: Skill 分类 + `build_skills_summary()` XML | ✅ | [ ] 验证 system prompt 中分类显示 |
| A3 | 22A | SK3: Skill 执行记忆 (`executions.jsonl`) | ✅ | [ ] 执行 skill → 检查 jsonl 写入 |
| A4 | 22B | SK4: per-skill `config.json` 配置 | ✅ 36 pass | [ ] 修改 config → 验证行为变化 |
| A5 | 22B | SK5: pre/post hooks 系统 | ✅ | [ ] 放 hooks.py → 验证触发 |
| A6 | 22B | SK7: Skill Registry 版本追踪 | ✅ | [ ] 查看 `skills_registry.json` 内容正确 |
| A7 | 22D | AE1: Event Bus 领域事件 + Dashboard WS 转发 | ✅ 35 pass | [ ] Dashboard WS 实时接收事件 |
| A8 | 22D | AE2: Session 追加模式保存优化 | ✅ | [ ] 多轮对话 → 检查 JSONL 追加 |
| A9 | 23A | R1: Dashboard POST 1MB body 限制 | ✅ 14 pass | [ ] curl 大 body → 验证 413 |
| A10 | 23A | R2: hooks.py 沙箱 (路径/大小/危险导入) | ✅ | [ ] 放恶意 hooks → 验证拒绝 |
| A11 | 23A | R4: SSRF DNS rebinding 防护 (Transport 层) | ✅ | [ ] `web_fetch http://127.0.0.1` → 验证阻断 |
| A12 | 23A | R5: Dashboard token 日志脱敏 | ✅ | [ ] 启动后查日志 token 已 mask |
| A13 | 23B | R3: Session 原子写入 | ✅ 15 pass | [ ] 对话中断电 → Session 不损坏 |
| A14 | 23B | R10: Key 提取 LRU 缓存 | ✅ | [ ] 重复查询 → 检查缓存命中 |
| A15 | 23C | R11: 图片 20MB 限制 | ✅ 7 pass | [ ] 发大图 → 验证跳过不崩溃 |
| A16 | 23C | R16: SHA256 视觉哈希去重 | ✅ | [ ] 重复截图 → 验证去重 |
| A17 | 24 | KG1-KG5: 知识图谱演进 (5 项) | ✅ 31 pass | [ ] 多轮对话 → 检查实体/三元组 |
| A18 | 25 | F1-F8: 回头看加固 (7项修复) | ✅ 979 pass | [ ] 长时间运行稳定性 |
| A19 | 28C | OpenClaw Memory Architecture (Vector DB→KG) | ✅ 3 pass | [ ] 多轮对话 → 检查 KG Semantic 检索 |
| **A20** | **26B** | **BrowserTool 11 actions (navigate/click/fill/screenshot 等)** | **✅ 54 pass** | **[ ] 真实浏览器 → 打开网页并截图** |
| **A21** | **26B** | **双层 SSRF 防护 (导航前 IP 检查 + route 拦截)** | **✅** | **[ ] 尝试导航到 `http://169.254.x.x` → 阻断** |
| **A22** | **26B** | **渐进信任域名 (首次确认后永久记住)** | **✅** | **[ ] 首次访问域名 → 确认提示 → 二次跳过** |
| **A23** | **26C** | **Session DPAPI/Fernet 加密持久化** | **✅ 28 pass** | **[ ] 登录网站 → 关闭→重启 → Session 恢复** |
| **A24** | **26C** | **TrustManager 独立化 + clear/remove** | **✅** | **[ ] `trusted_domains.json` 手动编辑确认** |
| **A25** | **27** | **SSRF TOCTOU 修复 (DNS pinning)** | **✅** | **[ ] 高并发 web_fetch → 无竞态** |
| **A26** | **27** | **AST Sandbox (替换 string-matching)** | **✅** | **[ ] 写 `__import__('os')` 的 hooks → 验证 AST 阻断** |
| **A27** | **27** | **Windows Atomic Write `safe_replace` 重试** | **✅** | **[ ] Windows Defender 场景下快速写入 → 无崩溃** |
| **A28** | **28A** | **ProviderFactory 抽象 (VLM 动态路由)** | **✅** | **[ ] 切换 VLM provider → 验证正确路由** |
| **A29** | **28A** | **Plugin Lifecycle (setup/teardown hooks)** | **✅** | **[ ] 手动 `/reload` → 确认 teardown→setup 序列** |
| **A30** | **28B** | **Python Sandbox (sys.addaudithook)** | **✅ 5 pass** | **[ ] 写恶意 Python 脚本 → 验证 audit hook 阻断** |
| **A31** | **28B** | **Shell Sandbox (stripped env)** | **✅** | **[ ] 检查 shell 进程环境变量 → 无敏感 key** |

### B. 核心功能 — 需生产环境验证

| # | 功能 | 描述 | 手动验证 |
|---|------|------|---------|
| B1 | Streaming 响应 | `/ws/stream` 流式 token 推送 | [ ] Dashboard 实时看到逐字输出 |
| B2 | VLM Feedback Loop | RPA 执行后 VLM 截图验证 | [ ] `verify=true` → VLM 比对结果 |
| B3 | Embedding 迁移 | bge-m3 1024-dim 自动迁移 | [ ] 旧 ChromaDB → 自动重建无报错 |
| B4 | Cron 跨日守护 | 重启后不补跑昨天的任务 | [ ] 次日重启 → 昨日任务标 skipped |
| B5 | Outlook 外部地址 | COM PropertyAccessor 发送外部邮件 | [ ] 发送到 @gmail.com → 成功 |
| B6 | 重复工具调用检测 | 连续相同 tool call → 自动终止 | [ ] 触发场景 → 验证中断 |
| B7 | 深度记忆整合 | 20B CLS 慢路径 → KG 自动 re-summary | [ ] 20+ 消息 → 整合触发 |

### C. 通道生产就绪状态

| # | 通道 | 代码存在 | 生产验证 |
|---|------|---------|---------|
| C1 | CLI | ✅ | [x] 日常使用 |
| C2 | MoChat (企业微信) | ✅ | [ ] 消息收发 + 附件 |
| C3 | Telegram | ✅ | [ ] 消息 + 语音 STT |
| C4 | Discord | ✅ | [ ] WebSocket 长连 + 消息 |
| C5 | Slack | ✅ | [ ] Socket Mode + Thread 回复 |
| C6 | Email (IMAP/SMTP) | ✅ | [ ] 收信 → 自动回复 |
| C7 | 飞书 (Feishu) | ✅ | [ ] 消息 + 图片下载 |
| C8 | 钉钉 (DingTalk) | ✅ | [ ] Stream Mode 消息 |
| C9 | WhatsApp | ✅ | [ ] Bridge WS + 消息收发 |
| C10 | QQ | ✅ | [ ] botpy SDK 消息 |

### D. 安全与文档维护

| # | 项目 | 描述 | 状态 |
|---|------|------|------|
| D1 | [SECURITY.md](file:///d:/Python/nanobot/SECURITY.md) 更新 | L248-254 的 5 个 "pending fix" 标注需更新为已修复 | [ ] |
| D2 | [TEST_TRACKER.md](file:///d:/Python/nanobot/TEST_TRACKER.md) 补全 | 添加 Phase 22A ~ Phase 28C 的测试记录 | [ ] |
| D3 | [TEST_TRACKER.md](file:///d:/Python/nanobot/TEST_TRACKER.md) 基线 | 回归基线从 924 更新为 **1097** | [ ] |
| D4 | [ARCHITECTURE_LESSONS.md](file:///d:/Python/nanobot/ARCHITECTURE_LESSONS.md) | L273 "Phase 22" 说明过时 | [ ] 低优先级 |
| D5 | [config.sample.json](file:///d:/Python/nanobot/config.sample.json) | **缺少** BrowserConfig / StreamingConfig / MemoryFeaturesConfig 等新增配置项 | [ ] |
| D6 | [TOOLS.md](file:///d:/Python/nanobot/TOOLS.md) | 缺少 BrowserTool (第 19 个工具)，当前写 18/18 需更新为 19 | [ ] |
| D7 | `pip-audit` 安全扫描 | 7 CVE / 6 包，已在 .venv311 升级修复；`npm audit` 跳过（WhatsApp 低优先级） | [x] ✅ |
| **D8** | **[PROJECT_STATUS.md](file:///d:/Python/nanobot/PROJECT_STATUS.md) 去重** | **L343-403 重复了 Phase 21D-21H 的内容 (与 L149-209 重复)** | **[ ]** |
| **D9** | **根目录临时文件清理** | **20+ 个 stale 文件 (err*.txt, test_*.txt, tmp_*.py 等) 应归档** | **[ ]** |
| **D10** | **[EVOLUTION.md](file:///d:/Python/nanobot/EVOLUTION.md) 更新** | **Phase 26B/26C/27/28A/28B/28C 已添加，但数据汇总区仍写 811 测试用例（实际 1097+）** | **[ ]** |

---

## 📝 二、计划做但未完成的事项

### 明确列入路线图但未开始

| 优先级 | 项目 | 来源 | 描述 |
|--------|------|------|------|
| **P1** | **Phase 22C: Multi-Channel Image Support** | [PROJECT_STATUS.md](file:///d:/Python/nanobot/PROJECT_STATUS.md) | 扩展图片下载到 MoChat, Slack, DingTalk |
| **P2** | **Phase 22C: Unified Speech-to-Text** | [PROJECT_STATUS.md](file:///d:/Python/nanobot/PROJECT_STATUS.md) | 统一语音输入管道（目前仅 Telegram） |
| **P2** | **Phase 22C: Image Generation Tool** | [PROJECT_STATUS.md](file:///d:/Python/nanobot/PROJECT_STATUS.md) | 集成 DALL-E / Stable Diffusion |
| **P3** | **Plugin Marketplace** | [progress_report.md](file:///d:/Python/nanobot/progress_report.md) | 可浏览的社区 Skill 仓库 |

### 文档中提到但尚未执行

| 项目 | 来源 | 状态 |
|------|------|------|
| `pip-audit` 依赖安全扫描 | [progress_report.md](file:///d:/Python/nanobot/progress_report.md) D7 | ✅ 已执行，7 CVE 已修复 |
| `npm audit` WhatsApp Bridge | [SECURITY.md](file:///d:/Python/nanobot/SECURITY.md) | ⏭️ 跳过（WhatsApp 低优先级，未来可能裁剪） |
| Rename "nanobot" → "titanbot" | 对话记录 | 评估后暂缓 |
| SQLite 迁移（Session 后端） | Phase 22D 评估 | 评估后延期 — JSONL 足够 |
| SSRS HTML→PDF 原生化 | Phase 2 备注 | 长期延期 |

---

## 🔍 三、已完成工作改进建议

### A. 潜在 Bug / 稳定性风险

| # | 严重度 | 文件 | 问题 | 建议 |
|---|--------|------|------|------|
| 1 | **P1** | [PROJECT_STATUS.md](file:///d:/Python/nanobot/PROJECT_STATUS.md) | L343-403 完全重复了 L149-209 的 Phase 21D-21H 内容，造成维护不一致 | 删除 L343-403 的重复内容 |
| 2 | **P1** | [EVOLUTION.md](file:///d:/Python/nanobot/EVOLUTION.md) L207, L385, L392-408 | 数据汇总写 "811 用例" 和 "948 passed"，实际已到 1097+ | 更新数据汇总区 |
| 3 | **P1** | [config.sample.json](file:///d:/Python/nanobot/config.sample.json) | 仅 59 行，缺少 Phase 21A `memoryFeatures`、Phase 21E `streaming`、Phase 26A `browser`、Phase 26C `trusted_domains` 等大量近期新增配置 | 补全所有新增 config 项 |
| 4 | **P2** | [TOOLS.md](file:///d:/Python/nanobot/TOOLS.md) | 写 18/18 工具全审计，但 Phase 26B 新增了 `BrowserTool`（plugins/browser.py），实际 19 个工具 | 补充 BrowserTool 审计条目 |
| 5 | **P2** | 根目录 | 存在 20+ 个临时/调试文件 ([err.txt](file:///d:/Python/nanobot/err.txt) ~ [err5.txt](file:///d:/Python/nanobot/err5.txt), `test_*.txt`, `tmp_*.py`, [clean_log.txt](file:///d:/Python/nanobot/clean_log.txt) 等) | 归档到 `archive/` 或删除 |
| 6 | **P2** | [sandbox_worker.py](file:///d:/Python/nanobot/nanobot/agent/sandbox_worker.py) | Phase 28B 沙箱仅 5 个测试，覆盖率偏低 | 增加边界测试用例 |
| 7 | **P3** | `skills/` 目录 | 项目根目录 `skills/` 仅 1 个 skill (`test-outlook-workflow`)，但 `nanobot/skills/` 有 12 个，结构可能造成混淆 | 统一 skill 存储路径说明 |
| 8 | **P3** | `.env` 文件 | Config Cleanup 阶段说 `config.json` 是唯一配置源，但根目录仍有 `.env` 文件 (1044 bytes) | 确认是否需删除 |

### B. 安全性审查

| # | 严重度 | 领域 | 发现 | 建议 |
|---|--------|------|------|------|
| 1 | ~~P1~~ | 依赖安全 | ~~从未执行 `pip-audit`~~ → ✅ 已执行，7 CVE 已在 .venv311 升级修复 | **已完成** |
| 2 | ~~P1~~ | Bridge 安全 | WhatsApp Bridge 用户极少，未来可能裁剪 | ⏭️ 跳过 |
| 3 | **P2** | Evaluate 白名单 | BrowserTool 仅允许 6 个 JS pattern，但未见自动化测试验证白名单绕过 | 增加 evaluate 白名单绕过测试 |
| 4 | **P2** | 加密退化 | Phase 26C 三级加密 (DPAPI→Fernet→Base64)，Base64 作为最终 fallback 不提供真正加密 | 文档明确标注 Base64-only 风险 |
| 5 | **P2** | `shell.py` Sandbox | Phase 28B 使用 stripped env + audit hook，但 `sys.addaudithook` 可被恶意代码在同进程内移除 | 已通过进程隔离缓解，但应文档说明限制 |
| 6 | **P3** | `config.sample.json` | 所有 provider apiKey 字段直接写 `"your_xxx_key_here"`，可能误用 | 考虑改为环境变量引用方式 |

### C. 架构 / 代码质量改进

| # | 领域 | 发现 | 建议 |
|---|------|------|------|
| 1 | **文档一致性** | 5 个文档各自维护进度信息，数据不同步（测试数、Phase 状态） | 考虑单一信息源 + 自动生成 |
| 2 | **Tools 计数** | `TOOLS.md` 写 18，`EVOLUTION.md` 写 18，实际 tools/ 有 18 + plugins/ 有 3 = 21 入口 | 统一定义何为 "工具" 并更新数字 |
| 3 | **Skills 目录结构** | 两个 skills 目录：`skills/`（根，仅 1 个）和 `nanobot/skills/`（12 个） | 文档说明用途区别 |
| 4 | **TEST_TRACKER 覆盖** | Phase 22A~28C 的测试都未记录到 TEST_TRACKER | 需要把 7 个 Phase 的测试补录 |
| 5 | **SECURITY.md items 6-10** | 显示为 ~~strikethrough~~ + ✅ 已修复，但 progress_report 标记为 "pending fix" | 统一标注 |

---

## 📊 四、项目状态快照

| 指标 | 数值 |
|------|------|
| 已完成大阶段 | 18+ Phase |
| 核心源文件 | 95+ |
| 测试文件 | 93 |
| 最新回归测试 baseline | **1097 passed** |
| 内置工具 (tools/) | 18 |
| 插件工具 (plugins/) | 3 (browser, browser_session, trust_manager) |
| 通道适配器 | 9 |
| 安全审计修复 | 32 项全部完成 |
| 待手动验证项 | **31 项 (A) + 7 项 (B) + 9 通道 (C) + 10 维护 (D) = 57 项** |
| 未完成计划项 | 4 个 (22C×3 + Plugin Marketplace) |

---

## ✅ 五、建议执行顺序

1. **立即：文档修复** — 删除 `PROJECT_STATUS.md` 重复内容、更新 `EVOLUTION.md` 数据、补全 `config.sample.json`
2. ~~**立即：安全扫描**~~ — ✅ `pip-audit` 完成（7 CVE 已修复），`npm audit` 跳过
3. **优先：根目录清理** — 归档/删除 20+ 临时文件，删除残留 `.env`
4. **优先：TEST_TRACKER 补全** — 添加 Phase 22A~28C 记录，更新回归基线到 1097
5. **手动测试按优先级** — 建议顺序：B 类 (核心功能) → A20-A31 (新增 Phase) → A1-A19 (旧 Phase) → C 类 (通道)
6. **后续开发** — 根据测试结果决定进入 Phase 22C 还是先修复发现的问题
