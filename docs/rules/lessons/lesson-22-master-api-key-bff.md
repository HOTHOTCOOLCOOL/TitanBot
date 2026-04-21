# Master API Key 绝对不出服务端 (Master API Key Must Never Leave the Server)

// Added: Phase 54 (参见 ADR-54)

当公司多个用户共用同一个上游 LLM 的 Master API Key（如 Azure OpenAI）时，**严禁**将该 Key 以任何形式（明文、混淆、加密）写入客户端安装包（如 Nanobot 的 `config.json` 或代码）。原因：客户端的任何加密最终都需要在本地内存中还原明文 Key 才能发出 HTTP 请求，攻击者可通过网络抓包（Fiddler）或内存 Dump 直接提取，与未加密无异。

**架构约束**：
- 必须引入 BFF（Backend-For-Frontend）代理网关，**部署于公司控制的服务端（而非用户机器）**。
- 客户端（Nanobot）仅持有一个低权限的"用户身份令牌 (dummy token)"，指向 BFF 网关发起请求。
- BFF 网关负责：① 鉴权 dummy token；② 限流（防止单用户爆刷）；③ 注入真实 Master Key；④ 将请求代理至 Azure 等上游服务。
- BFF 网关技术栈必须包含**服务端 LiteLLM**（而非手写 httpx 裸转），以解决 Azure/Anthropic 等非 OpenAI 标准协议的适配和流式超时异常处理。
- `bff/` 目录及包含真实 Key 的 `.env` 文件**永远不随 Nanobot 分发包下发给用户**。
