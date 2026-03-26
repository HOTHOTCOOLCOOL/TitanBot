# Nanobot Developer Rules

> **绝对规则 (Absolute Rules)**
> 本文档由历史架构教训和生产故障总结提炼而来。所有开发必须严格遵循以下戒律，否则会导致系统崩溃或严重的回归。

## 1. 核心架构戒律 (Architecture Rules)

* **保持单循环 (The Simple Main Loop)**：绝对禁止引入复杂的 DAG（有向无环图）编排或多智能体框架。必须坚持“用户输入 → LLM → 工具调用 → 结果 → LLM”的最简循环。
* **按目录构建 Skill**：Skill 必须按文件夹组织（而不是单个文件），包含 `SKILL.md` (定义和指令)、`scripts/` (代码)、`references/` 和 `assets/`。必须采用渐进式加载（Progressive Disclosure）来节省 Token。
* **Skill Auto-Sublimation**：必须维持“观察 → 知识积累 → 验证模式 → 固化为 Skill”的自动进化流水线。
* **分层记忆 (Layered Memory)**：严禁将所有记忆塞入系统提示。必须遵守 7 层架构（L1 Config ~ L7 Graph），且全部上文注入严格限制在 8000 字符内。
* **验证与评估分离**：在需要评估的场景采用三层验证（L1 代码规则、L2 弱模型打分、L3 强模型校验）。切勿在常规操作中滥用“LLM 自我评估”。
* **抵制过度工程与滥用 Harness**：严禁构筑多个 Agent 相互对话的复杂 DAG 网络来掩盖模型本身的缺陷。在实现 Phase 31 的验证层时，必须坚持极简闭环架构（L0:前置认知注入 -> L1:刚性拦截 -> L2:小模型事前动作自省 -> L3:事后反思萃取）。并且每一个拦截器组件必须支持“随基础模型变强而可被剥离”。
* **始终清空 Session**：在解决或调试工具故障时，必须在重试前清空历史（使用 `/new`），否则 LLM 会被历史错误上下文污染，导致它由于产生了“我已经完成”的幻觉而直接跳过执行。

## 2. 工具与接口戒律 (Tool & API Rules)

* **错误信息前缀**：所有工具如果执行失败，返回的错误字符串必须严格以 `"Error: "` 开头。Agent Loop 非常依赖此标准前缀来进行重试或感知。
* **输出截断**：所有工具的返回必须硬限制在 50,000 字符以内，附带 `[TRUNCATED]` 标识。
* **防止死循环**：
  * 切勿将输出型/终端型交互工具放入 `_CONTINUE_TOOLS` 配置中（否则会导致 LLM 不断重复相同对话）。
  * Loop 层必须包含重复动作检测（比如 3 次签名完全相同的调用则强行中断）。不要指望 LLM 会自觉停下。
  * 禁止在 Shell 沙箱中对常规 productive 命令（如 `python -c`，`node -e`）执行过度拦截，避免 LLM 不断试错陷入死胡同。
* **并行状态一致性**：编写工具时，务必假定会被 `asyncio.gather` 并发调用。有状态类工具（比如 Browser）一定要实现资源的初始化锁（`asyncio.Lock`），并将“打开/创建资源”与“单纯读取资源”强制分离。

## 3. 健壮性与迁移戒律 (Robustness & Migration)

* **跨日 Cron Job Guard**：补跑失败/错过的任务时，必须严格检查隔日边界（通过判断 `next_run_at_ms` 是否属于昨日）。绝对禁止在重启时一并触发昨日过期的大规模历史任务。
* **第三方 API 防御**：
  * 在进行架构探针（如 ChromaDB 升级做 dimension 检测）时，不要盲目使用 `peek()`，改用更稳定的 `get()`。探针遇到核心维度异常必须记录 WARNING 或 ERROR（绝对不能抛到 DEBUG 里掩盖错误），并立即强制重建或迁移。
  * 涉及到第三方库返回复杂类型（如 Numpy 数组）时，做分支判断永远使用 `is not None` 和 `len() > 0`，绝对禁止直接利用 `if x` 判断其 truthiness，这会导致 Python 抛出 `ValueError`。
  * Outlook COM API 面向外部 SMTP 地址发信时，必须使用 `Recipients.Add` + `ResolveAll` + 指定 `PR_SMTP_ADDRESS` 属性（`0x39FE001E`），禁止直接赋值 `mail.To`。
* **配置文件读取与覆盖**：当你需要强制覆盖 VLM provider 等环境变量时，直接使用 `os.environ[key] = value`。禁止使用 `os.environ.setdefault`（它会默默失效并继续使用之前的配置）。
* **跨平台降级 (Cross-Platform Graceful Degradation)**：引入平台特有 API（如 Windows `uiautomation`，`win32com`）时，**禁止**在模块顶层抛出不可恢复的 `ImportError`，同时**禁止**通过全局字典无脑注销 Tool。必须在核心内部方法处拦截 `sys.platform` / `ImportError` 并返回标准化字符串如 `"Error: This tool/feature is not supported on your OS."` 或激活备选降级方案（如从 UIA 降回 OCR/YOLO）。
* **防御层移动策略**：在转移防御验证节点（如把 SSRF 判断从外部函数放入 Transport 类中）后，必须 `grep` 并修正旧单元测试中关于此功能的所有 mock 点，并执行端到端回放，以防止测试假阳性。

## 4. 安全防护戒律 (Security & Defense Rules)

* **严防 SSRF (Server-Side Request Forgery)**：对于在 Browser Tool 等浏览器自动化中的 SSRF 防御，拦截 URL 后禁止主动做域名解析的“隐式重写”。（隐式重写会导致 CDN 的 SNI / 证书名匹配失败）。必须“解析 IP 判断，若安全，则让浏览器基于原 URL 放行”。
* **跳过非 HTTP URIs 的拦截**：在浏览器路由劫持中，第一时间必须放行所有属于浏览器内核本身的 URL schema（如 `chrome-extension://`，`data:` 等），否则会导致应用层面的假性渲染失败。
* **安全黑名单拦截**：涉及到 Shell 命令和动态执行的黑名单不仅限于显式的 `rm -rf /`。攻击可以通过嵌入特定解释器（`python -c "os.system('rm -rf /')"`）实现逃逸。必须在对应的层级加固沙盒检测（AST Sandbox 或 Sys Audit hooks）。

## 5. 提示词与预处理戒律 (Prompting & Processing Rules)

* **明确语言**：系统提示必须明确使用 `简体中文` 并在指令中体现对应的用词范例，绝不能只要求“使用中文”。否则推理模型在多轮思考中极易退化成繁体。
* **消除不需要的推演过程 `<think>` / Chain-of-Thought**：
  * 并不是所有的 reasoning models 都会按照标准的 `<think>` 标签包装它思考的过程。
  * Key 抽取、路由意图抽取等严苛短文本场景，不能单纯依赖 `strip_think_tags()`。必须同时辅以强制字数限制（降至 100 char 以内）以及**基于内容的文本开场白识别防御**（过滤 “Based on", "Let me think" 等前缀），并强制 Fallback 截断为原始请求。
  * 在核心的 `_execute_with_llm()` 的 response path 中，处理 `strip_think_tags()` 必须 **先于** `_FAIL_INDICATORS`（如 "无法完成" 的断言检测）发生，避免思维链内容引发错误的终止退出。
