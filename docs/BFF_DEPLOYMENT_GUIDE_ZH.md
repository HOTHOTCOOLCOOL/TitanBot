# Nanobot BFF 代理网关部署与配置操作手册

本文档是针对内部网络推广 Nanobot 时，如何正确把 BFF (Backend-For-Frontend) 服务器部署在公司内网，以及在内部分发客户端时如何进行安全配置的完整指南。

---

## 1. 架构概述为什么要部署它？

**核心目的**：保护公司花重金采购的 M365/Azure OpenAI **Master API Key（主万能密钥）** 永远不接触普通员工的电脑。
**设计原理**：
- 把真正的 `Azure API Key` 和真实端点锁在上锁的服务器房间里（即：网关服务器）。
- 员工手里的 Nanobot 安装包里，只有一个没有任何实质价值的“代币”（Dummy Token）。
- 网关验证代币合法并限流后，在内部注入真实主密钥向外面的微软发包。
一旦有员工离职或滥用配额，在服务器上秒删该人员的代币即可切断服务。

---

## 2. 服务端 (BFF Gateway) 部署流程

这一步通常由团队的 IT 管理员或者你自己在后台云服务器（需能同时打通内网和外网访问 Azure）上执行一遍即可。

### 2.1 环境准备与依赖安装
1. 将源码中的 `bff/` 整个目录上传/拷贝到专用的部署服务器上。
2. 确保系统安装了 Python 3.10+。
3. 打开服务器的终端，并进入该目录安装环境依赖：
   ```bash
   cd ./bff
   pip install fastapi uvicorn litellm python-dotenv loguru
   ```

### 2.2 核心配置文件 `.env`
BFF 服务端启动唯一认准的文件是 `.env`，**这个文件打死都不能混进发给普通员工的压缩包里**。
在 `bff` 文件夹下新建一个 `.env` 文件：

```ini
# 网关挂载的内网局域网IP与端口
BFF_HOST=0.0.0.0
BFF_PORT=8099

# 每分钟限流（限制单个用户的无意义刷屏消耗成本）
BFF_RATE_LIMIT_RPM=60

# 微软 Azure 真实密钥 (极高机密)
BFF_UPSTREAM_PROVIDER=azure
BFF_AZURE_API_KEY=你的真实的Azure_OpenAI_Key
# 注意：结尾千万不要带 /openai ！！
BFF_AZURE_API_BASE=https://xxx你公司的真实端点xxx.openai.azure.com  
BFF_AZURE_API_VERSION=2024-08-01-preview

# 名字转换表（如果你公司采购的名字很长，可以用这个转换）
# 左边：发给员工的名字  --> 右边：填入在 Azure 部署的真实名字
BFF_MODEL_MAP={"gpt-4o": "azure/gpt-4o", "gpt-4o-mini": "azure/gpt-4o-mini"}
```

### 2.3 分配员工“打卡牌” `user_tokens.json`
在 `bff/` 目录下找到这个文件，这是一个内测小名单，给每个人发一个独一无二的邀请码（也就是 Token）：
```json
{
  "supper_secret_token_for_zhangsan": "zhangsan",
  "supper_secret_token_for_lisi": "lisi"
}
```
*Tips: 有新人加入时，只需要修改这个 JSON 文件并**重启一下 BFF Server** 即可生效。*

### 2.4 正式长期运行
如果你在 Windows 服务器上：可以直接做成一个 `.bat` 自动开机启动脚本运行 `python bff_server.py`。
如果你在 Linux 服务器上：建议通过 `nohup` 或者 `pm2` 让它挂在后台不要因为终端关闭而退出：
```bash
nohup python bff_server.py > bff_gateway.log 2>&1 &
```
启动成功后，请记下这台服务器的内网 IP 地址（假设是 `192.168.10.50`）。

---

## 3. 分发给员工的客户端 (Nanobot) 配置

对于将要打包分享给那 200 号员工的 Nanobot 文件夹，你必须保证：
**它里面绝对没有任何 Azure API Key 残留。** 

你需要提前帮普通员工改好根目录下的 `config.json`：

```json
{
  "providers": {
    "custom": {
      "api_key": "supper_secret_token_for_zhangsan",  // 这里填给那位员工分配的Dummy Token
      "api_base": "http://192.168.10.50:8099/v1"      // 指向你的那一台内网网关服务器IP
    }
  },
  "agents": {
    "defaults": {
      "model": "gpt-4o"  // 这一行必须存在且和前面 .env 里的映射表对得上
    }
  }
}
```

员工拿到文件夹，双击运行，Nanobot 就会带着他专属的那个 `api_key` 发给内网 `192.168.10.50`。**而员工完全不知道真正值钱的那个密钥是多少，这就叫绝对隔离。**

---

## 4. 日常问题排查 (Troubleshooting)

如果你在内测群里收到员工截图报错，请对号入座，直接看服务器终端的报错：

- 🔴 **员工客户端一直提示 `401 Unauthorized`**
  - **病因**：这人填错了 Token，或者你的 `user_tokens.json` 没有他的账号。
  - **解药**：检查客户端的 `api_key` 和服务器挂载 json 是否一致，是否忘记重启服务端使新人员生效了？
- 🔴 **员工客户端一直提示 `429 Too Many Requests`**
  - **病因**：他在一分钟内点击了超过 60 次回车，涉嫌发包滥刷（Rate Limit 生效保护了你的钱包）。
  - **解药**：让他稍安勿躁等 1 分钟就能自己解封。
- 🔴 **员工客户端提示 `502 Bad Gateway` 且服务器日志爆红打印 `Resource not found`**
  - **病因**：员工 `config.json` 里填写的模型名字（如 `gpt-5.4-mini`），在 Azure 上不存在！
  - **解药**：修改你服务器端 `.env` 里的 `BFF_MODEL_MAP`，把他填进来的错误名字“强制映射”到你真实的 Azure 模型下，然后重启。
- 🔴 **员工客户端请求直接“拒绝连接 (ECONNREFUSED)”**
  - **病因**：网络物理不通。
  - **解药**：检查你服务器的系统防火墙是否放行了 TCP `8099` 端口，以及你的 `BFF_HOST` 是否填的是 `0.0.0.0` 而不是 `127.0.0.1` 导致只能本机访问。
