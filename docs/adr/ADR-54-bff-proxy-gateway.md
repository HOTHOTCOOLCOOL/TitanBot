# ADR-54: Nanobot BFF 代理网关架构

**状态**: APPROVED
**日期**: 2026-04-16
**作者**: Harness 5阶辩证工作流 (Claude Sonnet → Claude Opus → Gemini High → Gemini Low → Claude Sonnet)
**相关议题**: 保护公司共用 Azure API Key 不随 Nanobot 分发包泄露

---

## 背景与问题陈述

Nanobot 未来将接入贵公司统一采购的 Azure OpenAI 服务，所有用户共用同一个 Master API Key。若将此 Key 直接写入 Nanobot 的 `config.json` 或以任何形式随安装包分发，用户可通过以下方式轻易提取：
- **本机文件读取**：直接 `cat config.json`
- **网络抓包**：Fiddler/Charles 等工具替换本机 SSL 证书后拦截明文请求
- **内存 Dump**：调试工具提取进程内存中已解密的 Key

客户端侧的任何加密手段（非对称加密、混淆等）均无法从根本上阻止以上攻击路径，因为任何加密方案最终都需要在客户端内存中还原明文 Key 才能发起 HTTP 请求。

## 决策

引入一个**后端代理网关 (BFF - Backend-For-Frontend)**，使得：
- **客户端 (Nanobot)** 只持有无害的"用户身份令牌 (dummy token)"，永远无法直接访问上游 LLM 服务商
- **BFF 网关** 持有 Master API Key，对请求进行鉴权后，代理转发至真实上游服务商

## 被评估的方案

| 方案 | 描述 | 结论 |
|:---|:---|:---:|
| A: 客户端侧加密 | 公钥加密 Key 后分发，用用户名/机器码作私钥 | ❌ 无法抵抗内存 Dump 和抓包攻击 |
| B: BFF 代理网关 | 客户端持 dummy token，服务端持真 Key | ✅ **采纳** |
| C: Azure STS 临时令牌 | 每次启动时服务端签发有效期极短的临时 token | 🔄 Phase 2 升级候选 |

## 技术细节

### 架构图

```
┌─────────────────────────────────────────────────┐
│              用户本地 (Client)                   │
│                                                 │
│  ┌──────────────┐         ┌──────────────────┐  │
│  │   Nanobot    │────────►│   config.json    │  │
│  │   客户端     │         │  api_key:        │  │
│  └──────┬───────┘         │  user_tok_abc    │  │
│         │                 └──────────────────┘  │
└─────────┼───────────────────────────────────────┘
          │ POST /v1/chat/completions
          │ Authorization: Bearer user_tok_abc
          ▼
┌─────────────────────────────────────────────────┐
│          公司云端/内网 (Server)                  │
│                                                 │
│  ┌────────────────────────────────────────────┐ │
│  │         BFF Gateway (FastAPI)              │ │
│  │                                            │ │
│  │  1. Auth: 验证 user_tok_abc 合法性          │ │
│  │  2. Rate Limit: 每用户 60 RPM              │ │
│  │  3. Model Map: gpt-4o → azure/my-deploy   │ │
│  │  4. LiteLLM: 注入 MASTER_KEY 转发          │ │
│  │  5. Audit Log: 记录 user/model/tokens      │ │
│  │                                            │ │
│  │  .env: BFF_AZURE_API_KEY=sk-real-key...   │ │
│  └──────────────────────┬─────────────────────┘ │
└─────────────────────────┼───────────────────────┘
                          │ POST + Bearer MASTER_KEY
                          ▼
              ┌────────────────────────┐
              │  Azure OpenAI /        │
              │  Anthropic / 任意上游   │
              └────────────────────────┘
```

### BFF 核心技术栈

- **框架**: FastAPI + Uvicorn（异步原生，与 Nanobot Python 生态一致）
- **代理引擎**: LiteLLM（服务端）
  - 解决协议碎片化问题（Azure 非 OpenAI 标准格式）
  - 原生支持流式响应（SSE）代理
  - 提供准确的 Token Usage 数据用于审计
- **鉴权（PoC）**: MockAuthenticator（user_tokens.json 查表）
- **限流**: 内存令牌桶（每 user_id 每分钟 60 次）

### 暴露的 Endpoints

| Endpoint | 方法 | 功能 |
|:---|:---:|:---|
| `/v1/chat/completions` | POST | 主代理入口（stream=true/false 均支持） |
| `/v1/models` | GET | 可用模型列表（LiteLLM 连通性检查必要） |
| `/health` | GET | 健康检查 |

### 关键设计约束

1. **环境变量前缀隔离**: 所有 BFF 配置使用 `BFF_` 前缀，防止与 Nanobot 本身的环境变量发生冲突
2. **错误格式 OpenAI 兼容**: Auth/Rate Limit 错误返回标准 OpenAI 错误 JSON 结构，防止客户端 LiteLLM 解析异常
3. **流式超时保护**: litellm 调用显式配置 `timeout=120`，防止上游假死导致连接泄露
4. **零侵入客户端**: Nanobot 核心代码无需任何修改，仅通过 `config.json` 的 `custom` provider 字段配置

## 决策过程详述（Harness 辩证历史摘录）

### V1 → V2 的关键架构演进

**最大的结构性变更：废弃手写 httpx 代理，改用服务端 LiteLLM**

V1 提案使用 httpx 手动转发 HTTP 请求。Opus 批判指出这有三个致命缺陷：
1. Azure 原生 API 不是 OpenAI 兼容格式（路径、Header、Authentication 均不同）
2. SSE 断流和错误处理没有可靠的异常捕获
3. 透传模式下无法获取 Token Usage 数据

V2 决策：服务端同样引入 LiteLLM 作为代理引擎。这实现了"双端对称"——客户端和服务端都通过 LiteLLM 处理 LLM 请求细节，形成架构上的镜像对称，极大降低了维护复杂度。

**本地 PoC 的安全边界约定**

Opus 指出"在用户本机部署 BFF 且 `.env` 存明文 Key"存在逻辑悖论：用户可以直接读取 `.env`。

**V2 折中决策**：Phase 0 (PoC) 的目的是**验证端到端架构可行性**，在逻辑上将本机划分为"客户端沙盒"和"服务端沙盒"。在真实 Phase 1 生产部署时，`bff/` 目录及 `.env` 将**仅存在于公司云服务器**，绝不纳入分发给用户的 Nanobot 包中。

## 生产演进路线图

| 阶段 | 主题 | 关键改动 |
|:---:|:---|:---|
| **Phase 0 (当前)** | 本地 PoC 验证 | FastAPI + LiteLLM + MockAuth + .env 明文 |
| **Phase 1** | 云端内网部署 | 部署至 Azure VM/Container；Nginx 反代 + TLS |
| **Phase 2** | 认证升级 | JWT RS256 验签；接入 Azure Entra ID (OIDC) |
| **Phase 3** | 精细管控 | Azure APIM 集成；用户配额；审计日志持久化 |

## 结果

- **Nanobot 客户端**的任何配置文件和日志中，Master API Key 将**完全不可见**
- 即使用户提取并分享自己的 dummy token，它也只在 BFF 有效期内、受限流保护下可用，且随时可被管理员在服务端吊销
- BFF 网关对客户端代码**零侵入**，Nanobot 无需任何核心代码修改

---

*本 ADR 由 Harness 5阶辩证工作流生成，经过 Claude Sonnet (Draft V1) → Claude Opus (极端批判) → Gemini High (反思重构 V2) → Gemini Low (正向校验) → Claude Sonnet (最终定稿) 多轮迭代审查。*
