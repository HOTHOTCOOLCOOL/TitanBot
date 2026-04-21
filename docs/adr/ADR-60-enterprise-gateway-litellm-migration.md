# ADR-60: Enterprise Gateway — LiteLLM Migration
# Phase 60 — 企业级网关升级：从轻量 BFF 迁移至 LiteLLM Proxy

**Status:** Proposed (ADR 已定稿，待进入编码实施阶段)
**Date:** 2026-04-18
**Deciders:** Harness 5-阶辩证工作流 (Sonnet Planner → Opus Critic → Gemini Pro High → Gemini Pro Low → Sonnet Final)
**Supersedes:** Phase 54 BFF Proxy Gateway (ADR-54) — 自研 FastAPI 网关

---

## 1. 背景与动机 (Context)

Phase 54 的自研 BFF 网关满足了最初的核心目的：隐藏 Azure Master API Key，防止其暴露给员工。但随着 Nanobot 向全公司推广（200+ 用户），以下新需求已无法在自研网关中轻量实现而不引入严重技术债：

| 新兴需求 | 自研 BFF 的困境 |
|:---|:---|
| 按用户/部门精确追踪 $ 花费 | 流式输出下精确计算 Token 极高成本 |
| 管理员实时 Dashboard | 需要自建前端 + 数据库 |
| 动态禁用/激活用户（免重启） | 目前依赖 JSON 文件 + 重启 |
| 用户分组与模型权限隔离 | RBAC 逻辑复杂 |
| Excel 批量导入用户 | 需要额外解析库 |
| IP 访问审计日志 | 需要额外持久化层 |

**核心洞察**：以上需求精准描绘了一个"企业级 LLM API 管理网关"——这正是 **LiteLLM Proxy Server** 的商业定位。与其把自研网关改成低配版的 LiteLLM，不如直接使用 LiteLLM 本身。本 ADR 记录了经 Harness 5-阶辩证工作流审查后的完整迁移决策。

---

## 2. 核心架构决策 (Decision)

### 2.1 保留的初代 V1 核心设计

| 决策 | 理由 |
|:---|:---|
| **客户端 `config.json` 零更改** | 200 人已分发，更改代价极高；LiteLLM 完全兼容 `/v1` OpenAI 协议 |
| **模型列表客户端写死（非动态）** | 改客户端逻辑违反极简原则；内网"越权报错"体验可接受 |
| **Dashboard 与 API 共用 :8099 端口** | 加 Nginx 层破坏"零额外基础设施"原则；以长随机 Master Key 替代端口隔离 |

### 2.2 采纳的关键批判与修正

| Opus 批判 | 采纳的解决方案 |
|:---|:---|
| **Token 格式断崖**：新旧 Token 不兼容，200 人同时失联 | 迁移脚本使用 `/key/generate` 强制透传旧 Token 字符串，实现真正的零停机 |
| **`latest` 镜像标签**：随时可能因版本升级而崩溃 | 精确钉死 `postgres:15-alpine` + `litellm:v1.40.23` |
| **Postgres 数据裸奔**：无备份 = 成本数据可随时丢失 | 引入 `pg-backup` sidecar 容器，每日自动 `pg_dump`，无需人工干预 |
| **脚本无幂等性**：重跑产生重复 Key | 先 `GET /key/info` 查重，已存在则跳过 |
| **Langfuse 毒药配置** | 从 `litellm_config.yaml` 彻底移除 `success_callback` |
| **备份目录权限** | 文档注明 `mkdir -p backups && chmod 777 backups` |

### 2.3 明确不在本 ADR 范围内的事项

- ❌ **预算硬上限 (Budget Hard Cap)**：用户无此需求；以 Azure Portal 真实账单作为最终权威；Dashboard 展示"估算值"已足够管理目的
- ❌ **阈值预警 (50%/80%/95%)**：需要引入发邮件/消息服务，超出极简内网分发的场景范围
- ❌ **Nginx 反向代理**：内网可信边界内不引入，维持零运维感知原则

---

## 3. 最终技术实施路径 (Implementation)

### 3.1 受影响文件清单

| 文件 | 变更类型 | 说明 |
|:---|:---|:---|
| `bff/docker-compose.yml` | **NEW** | LiteLLM + PostgreSQL + 备份 三容器基础设施 |
| `bff/litellm_config.yaml` | **NEW** | LiteLLM 模型映射与全局配置 |
| `bff/.env` | **MODIFY** | 追加 DB_PASSWORD 和 LITELLM_MASTER_KEY 字段 |
| `bff/scripts/import_users_to_litellm.py` | **NEW** | 平滑迁移脚本（幂等 + 容错 + 旧 Token 继承） |
| `docs/BFF_DEPLOYMENT_GUIDE_ZH.md` | **MODIFY** | 重写部署指南，覆盖 Docker + LiteLLM 管理面板 |
| `bff/bff_server.py` | **DEPRECATED** | 切换完成后删除；过渡期保留作双轨备份 |
| `bff/user_tokens.json` | **DEPRECATED** | 用户数据迁移至 Postgres 后废弃 |

### 3.2 零停机切换 SOP

```
Step 1 (验证期): LiteLLM 容器临时挂在 :8100，用测试账号验通路由和 Dashboard
Step 2 (导入期): 运行 import_users_to_litellm.py，原始 Token 字符串无损继承
Step 3 (切流期): 将 :8099 端口映射从旧 BFF 切换至 LiteLLM 容器，旧 BFF 下线
Step 4 (验收期): 抽查 3 个现有员工账号发起真实请求，Dashboard 确认有计费记录
```

> 自始至终，员工端 `config.json` 中的 `api_key` 和 `api_base` **无需任何修改**。

### 3.3 能力覆盖矩阵（最终版）

| 管理需求 | 覆盖状态 | 实现方案 |
|:---|:---|:---|
| 用户/模型使用量 + $ 统计 | ✅ 内置 | LiteLLM Postgres 精确追踪 |
| 管理员 Dashboard | ✅ 内置 | LiteLLM React UI (:8099/ui) |
| Excel 批量导入用户 | ✅ 定制 | `import_users_to_litellm.py` |
| 动态禁用/激活用户（免重启） | ✅ 内置 | Dashboard → Disable Key，秒级生效 |
| 模型组别隔离（VIP 用户用贵模型） | ✅ 内置 | LiteLLM Team + models 权限字段 |
| 按用户展示可用模型 | 🟡 客户端写死 | 越权请求返回 403，接受此 Trade-off |
| IP 访问记录 + 审计日志 | ✅ 内置 | LiteLLM 原生记录 request metadata |

---

## 4. 成本精度免责声明 (Cost Accuracy Disclaimer)

> ⚠️ **重要**：LiteLLM Dashboard 所显示的金额基于**公开模型零售价格表**进行估算，并非基于贵公司与微软签订的企业协议（EA）合同价格。实际财务核算请以 **Azure Portal → 成本管理 + 计费** 为最终权威依据。本 Dashboard 数据用于内部相对用量对比与归因，不作为财务账单使用。

---

## 5. 验证计划 (Acceptance Criteria)

- [ ] 三个容器 (`litellm-db`, `db-backup`, `litellm-proxy`) 全部 `healthy`
- [ ] 管理员以 `LITELLM_MASTER_KEY` 成功登录 `http://<内网IP>:8099/ui`
- [ ] 用**原有 Phase 54 的旧 Token** 发起请求，Azure 返回 200 + 有效回复
- [ ] Dashboard 在请求后即时显示该 Key 的 $ 花费更新
- [ ] `./backups/` 目录存在 `pg_dump` 备份文件
- [ ] `import_users_to_litellm.py` 二次运行后，所有输出为"⏭ 跳过 (已存在)"（幂等校验）
