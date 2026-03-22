# Nanobot 项目进度总览

> 截至 2026-03-22 （长期维护文档）

---

## 🏁 当前位置：Phase 25 ✅（全部完成）

已完成 **17+ 个大阶段**，从 10 文件聊天机器人发展到 95+ 文件、14 子包、18 工具、9 通道的企业级 AI Agent。

---

## ✅ 已完成阶段

| 阶段 | 核心内容 | 测试 |
|------|---------|------|
| Phase 7 | 轻量化重构 | ✅ |
| Phase 8 | 知识追踪 + 记忆系统 | ✅ |
| Phase 9 | 知识进化 (版本化/合并/KB命令) | ✅ |
| Phase 11 | 深度优化 (死代码/Token追踪/LLM重试) | ✅ |
| Phase 12 | Knowledge System Upgrade (AutoSkill/XSKILL) | ✅ |
| Phase 13-14 | 检索增强 + 工程清理 | ✅ |
| Phase 15 | Web Dashboard + Master Identity | ✅ |
| Phase 16-17 | Bug Fixes + Root Cleanup | ✅ |
| Phase 18A-D | 安全审计 (32 项全修复) | ✅ 529→599 |
| Phase 19/19+ | 性能优化 + Knowledge 拆分 | ✅ 602 |
| Phase 20A-H | AI Memory 7 层架构 | ✅ |
| Phase 21A-E | 审计修复 + Streaming + Embedding升级 | ✅ 793 |
| Phase 21F-H | 生产热修复 (3 轮) | ✅ |
| Phase 22A | Skill 触发 & 发现优化 (SK1-SK3) | ✅ 811 |
| Phase 22B | Skill 配置 & Hooks (SK4-SK7) | ✅ 847 |
| Phase 22D | Event-Driven Architecture + Session Save 优化 | ✅ 847 |
| Phase 23A | P0 安全加固 (Dashboard/SSRF/Hooks/Token) | ✅ 924+ |
| Config Cleanup | 移除 `.env` 冗余层，`config.json` 为唯一配置源 | ✅ |
| Phase 23B | P1 数据完整性 & 架构修复 (R3/R7/R8/R9/R10/R13) | ✅ 948 |
| Phase 23C | P2 架构优化 & 边缘加固 (R6/R11/R12/R14/R16) | ✅ 948 |
| Phase 24 | Knowledge Graph Evolution — MDER-DR (KG1-KG5) | ✅ 979 |
| **Phase 25** | **项目回头看 & 加固 (F1-F8)** | **✅ 979** |

---

## ⏳ 待做阶段

### Phase 26 — Playwright Browser Automation 🔜 (Next)

> **架构方案**：Skill + Tool Hybrid，按需加载。详见 `implementation_plan.md`。

| 子阶段 | 内容 | 预计工作量 | 状态 |
|--------|------|-----------|------|
| **26A** | Plugin Dependency Management — SK7 扩展 + `BrowserConfig` schema | 半天 | ❌ |
| **26B** | Playwright Skill + `BrowserTool` Plugin — 11 action + 双层 SSRF + 渐进信任 | 1-2天 | ❌ |
| **26C** | Session 加密持久化 + Trust Manager | 1天 | ❌ |

**关键设计决策**（已讨论确认）：
- ✅ Skill 层 (`skills/browser-automation/SKILL.md`) + Plugin Tool 层 (`plugins/browser.py`)
- ✅ 渐进信任域名模型 — 首次导航问一次，永久记住，子请求静默放行
- ✅ Session 持久化 — DPAPI 加密 + TTL + 域名隔离
- ✅ 双层 SSRF — 导航前 IP 检查 + `page.route("**/*")` 请求拦截
- ✅ 与桌面 RPA 互补 — `browser` 管 Web，`rpa` 管桌面应用

### Phase 22C — Multi-Modal & Channel Extension

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Multi-Channel Image Support | P1 | 扩展图片下载到 MoChat, Slack, DingTalk |
| Unified Speech-to-Text | P2 | 统一语音输入管道（目前仅 Telegram） |
| Image Generation Tool | P2 | 集成 DALL-E / Stable Diffusion |

### 长期 Backlog

| 项目 | 优先级 | 描述 |
|------|--------|------|
| Plugin Marketplace | P3 | 可浏览的社区 Skill 仓库（Phase 26 完成后推进） |

---

## 📋 文档过期问题

| 文档 | 问题 | 状态 |
|------|------|------|
| `SECURITY.md` L248-254 | 5 项标记 "pending fix" 但 Phase 21 已全部修复 | **需更新** |
| `ARCHITECTURE_LESSONS.md` L273 | "Phase 22" 说明已过时 | 低优先级 |
| `TEST_TRACKER.md` | 停在 Phase 21G，未覆盖 22A-25；回归基线过期 (924 vs 979) | **需更新** |
| `README.md` | 总体内容仍准确，无需改动 | ✅ |

---

## 🔍 手动验证追踪清单

> **规则**：每项验证通过后标 `[x]`，附日期。一人维护大项目，逐项记录确保无遗漏。

### A. 阶段功能 — 仅有自动测试，缺少生产手动验证

> Phase 22A 至 Phase 25 均有自动化测试通过，但 `TEST_TRACKER.md` 未记录手动确认。

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

### B. 核心功能 — 需要生产环境验证

| # | 功能 | 描述 | 手动验证 |
|---|------|------|---------|
| B1 | Streaming 响应 | F1: `/ws/stream` 流式 token 推送 | [ ] Dashboard 实时看到逐字输出 |
| B2 | VLM Feedback Loop | F3: RPA 执行后 VLM 截图验证 | [ ] `verify=true` → VLM 比对结果 |
| B3 | Embedding 迁移 | bge-m3 1024-dim 自动迁移 | [ ] 旧 ChromaDB → 自动重建无报错 |
| B4 | Cron 跨日守护 | L15: 重启后不补跑昨天的任务 | [ ] 次日重启 → 昨日任务标 skipped |
| B5 | Outlook 外部地址 | L14: COM PropertyAccessor 发送外部邮件 | [ ] 发送到 @gmail.com → 成功 |
| B6 | 重复工具调用检测 | L16: 连续相同 tool call → 自动终止 | [ ] 触发场景 → 验证中断 |
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
| D1 | `SECURITY.md` 更新 | L248-254 的 5 个 "pending fix" 标注需更新为已修复 | [ ] |
| D2 | `TEST_TRACKER.md` 补全 | 添加 Phase 22A ~ Phase 25 的测试记录 | [ ] |
| D3 | `TEST_TRACKER.md` 基线 | 回归基线从 924 更新为 979 | [ ] |
| D4 | `ARCHITECTURE_LESSONS.md` | L273 "Phase 22" 说明过时 | [ ] 低优先级 |
| D5 | `config.sample.json` | 确认包含所有新增配置项 (BrowserConfig 等) | [ ] Phase 26 后 |
| D6 | `TOOLS.md` | 确认 18 工具审计表仍准确 | [ ] |
| D7 | `pip-audit` 安全扫描 | 运行 `pip-audit` 检查依赖漏洞 | [ ] |

---

## 📝 每次 Phase 完成后必须更新的 5 个文档

1. ✅ `EVOLUTION.md` — 演进时间线 + Phase 条目
2. ✅ `LESSONS_LEARNED.md` — 本轮教训
3. ✅ `PROJECT_STATUS.md` — 详细进度跟踪
4. ✅ `progress_report.md` — 精简进度总览（本文档）
5. ✅ 测试全部通过

---

## 建议下一步

1. **Phase 26A** — Plugin Dependency Management（新会话执行）
2. **Phase 26B** — Playwright Skill + BrowserTool（新会话执行）
3. **Phase 26C** — Session 持久化 + Trust Manager（新会话执行）
4. **手动验证** — 逐项完成上列 A/B/C/D 清单
5. **文档更新** — 修复上表中标记 "需更新" 的项目

