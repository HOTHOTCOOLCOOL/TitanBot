# Nanobot Developer Rules

> **绝对规则 (Absolute Rules)**
> 本文档由历史架构教训和生产故障总结提炼而来。所有开发必须严格遵循以下戒律，否则会导致系统崩溃或严重的回归。

## 1. 核心架构戒律 (Architecture Rules)

* **保持单循环 (The Simple Main Loop)**：绝对禁止引入复杂的 DAG（有向无环图）编排或多智能体框架。必须坚持“用户输入 → LLM → 工具调用 → 结果 → LLM”的最简循环。
* **按目录构建 Skill**：Skill 必须按文件夹组织（而不是单个文件），包含 `SKILL.md` (定义和指令)、`scripts/` (代码)、`references/` 和 `assets/`。必须采用渐进式加载（Progressive Disclosure）来节省 Token。
* **Skill Auto-Sublimation**：必须维持“观察 → 知识积累 → 验证模式 → 固化为 Skill”的自动进化流水线。
* **分层记忆 (Layered Memory)**：严禁将所有记忆塞入系统提示。必须遵守 7 层架构（L1 Config ~ L7 Graph），且全部上文注入严格限制在 8000 字符内。
* **验证与评估分离**：在需要评估的场景采用确定性验证（L1 代码规则拦截 + L3 事后反思萃取）。L2 弱模型自省已移除（误拒率不可接受）。切勿在常规操作中滥用“LLM 自我评估”。
* **抵制过度工程与滥用 Harness**：严禁构筑多个 Agent 相互对话的复杂 DAG 网络来掩盖模型本身的缺陷。在验证层架构中，必须坚持极简闭环架构（L0:前置认知注入 -> L1:刚性拦截 -> L3:事后反思萃取）。并且每一个拦截器组件必须支持“随基础模型变强而可被剥离”。
* **确定性优先 (Deterministic First)**：安全检查尽量用确定性规则（正则、白名单、路径匹配）实现，而非依赖 LLM 判断。L1 规则可测试、可审计、零延迟。如未来引入低延迟本地模型，可采用黑名单制+warn-only重新评估 LLM 审查。
* **始终清空 Session**：在解决或调试工具故障时，必须在重试前清空历史（使用 `/new`），否则 LLM 会被历史错误上下文污染，导致它由于产生了“我已经完成”的幻觉而直接跳过执行。

## 2. 工具与接口戒律 (Tool & API Rules)

* **错误信息前缀**：所有工具如果执行失败，返回的错误字符串必须严格以 `"Error: "` 开头。Agent Loop 非常依赖此标准前缀来进行重试或感知。
* **绝对禁止吞噬异常**：在 `try/except` 块中包装第三方库调用（如 Browser-Use, LiteLLM 等）时，**必须**使用 `logger.error(f"... {e}")` 打印异常堆栈再返回 Error 字符串。绝对禁止像 `except Exception as e: return f"Error: {e}"` 这样静默失败，这会导致 Agent 出现“0.0s 瞬间执行完毕但失败”的幻觉，使得开发者无日志可查。
* **第三方模型参数翻译**：集成外部框架（如 LangChain 的 ChatOpenAI）时，必须识别并清洗 Nanobot 内部的配置属性（如 LiteLLM 的 `volcengine/doubao-...` 前缀、将内部的 `api_base` 映射为外部框架的 `base_url`）。不要盲目把内部 Config 对象透传给第三方库。
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
* **子系统集成与生命周期同步 (Subsystem Integration & Lifecycle Sync)**：
  * 当开发独立的功能模块（如 `TaskKnowledgeStore` 负责存储记忆任务）时，必须严格确保它被编织进了主系统流程的核心生命周期（如及时触发 `VectorMemory` 进行语义索引）。绝对禁止出现数据已持久化但在检索层静默失效（Silent Failure）导致长期未能被大模型路由/感知的问题。添加新模块时，务必编写端到端的集成用例以验证全链条数据闭环。
* **配置文件读取与覆盖**：当你需要强制覆盖 VLM provider 等环境变量时，直接使用 `os.environ[key] = value`。禁止使用 `os.environ.setdefault`（它会默默失效并继续使用之前的配置）。
* **跨平台降级 (Cross-Platform Graceful Degradation)**：引入平台特有 API（如 Windows `uiautomation`，`win32com`）时，**禁止**在模块顶层抛出不可恢复的 `ImportError`，同时**禁止**通过全局字典无脑注销 Tool。必须在核心内部方法处拦截 `sys.platform` / `ImportError` 并返回标准化字符串如 `"Error: This tool/feature is not supported on your OS."` 或激活备选降级方案（如从 UIA 降回 OCR/YOLO）。
* **防御层移动策略**：在转移防御验证节点（如把 SSRF 判断从外部函数放入 Transport 类中）后，必须 `grep` 并修正旧单元测试中关于此功能的所有 mock 点，并执行端到端回放，以防止测试假阳性。

## 4. 安全防护戒律 (Security & Defense Rules)

* **严防 SSRF (Server-Side Request Forgery)**：对于在 Browser Tool 等浏览器自动化中的 SSRF 防御，拦截 URL 后禁止主动做域名解析的“隐式重写”。必须“解析 IP 判断，若安全，则让浏览器基于原 URL 放行”。
* **跳过非 HTTP URIs 的拦截**：在浏览器路由劫持中，第一时间必须放行所有属于浏览器内核本身的 URL schema（如 `chrome-extension://`，`data:` 等），否则会导致应用层面的假性渲染失败。
* **安全黑名单拦截**：涉及到 Shell 命令和动态执行的黑名单不仅限于显式的 `rm -rf /`。攻击可以通过嵌入特定解释器实现逃逸。必须在对应的层级加固沙盒检测。
* **智能审批静默 (Smart HITL)**：安全动作需要拦截，但禁止反人类的频繁骚扰。在增加涉及状态修改（如 `shell` 或 `outlook(send)`）的高危拦截机制时，**必须且只能**同频引入“永远允许”的粘性白名单匹配机制 (`ApprovalStore`)。让用户自主划定对环境及安全的可信边界，不打破代理执行的顺畅性。

## 5. 提示词与预处理戒律 (Prompting & Processing Rules)

* **明确语言**：系统提示必须明确使用 `简体中文` 并在指令中体现对应的用词范例，绝不能只要求“使用中文”。否则推理模型在多轮思考中极易退化成繁体。
* **消除不需要的推演过程 `<think>` / Chain-of-Thought**：
  * 并不是所有的 reasoning models 都会按照标准的 `<think>` 标签包装它思考的过程。
  * Key 抽取、路由意图抽取等严苛短文本场景，不能单纯依赖 `strip_think_tags()`。必须同时辅以强制字数限制（降至 100 char 以内）以及**基于内容的文本开场白识别防御**（过滤 “Based on", "Let me think" 等前缀），并强制 Fallback 截断为原始请求。
  * 在核心的 `_execute_with_llm()` 的 response path 中，处理 `strip_think_tags()` 必须 **先于** `_FAIL_INDICATORS`（如 "无法完成" 的断言检测）发生，避免思维链内容引发错误的终止退出。

## 6. UI 自动化操作戒律 (UI Automation Strategy Rules)

* **URL 参数化优先 (URL Parameterization First)**:
  * 对于支持 URL 查询参数的网站（旅行/搜索/电商类，如携程、Google Flights、Amazon），**优先使用 URL 直接导航到结果页**，而非模拟人类逐步填表。例如：`browser(action='navigate', url='https://flights.ctrip.com/online/list/oneway-BJS-PAR?depdate=2026-04-01')`。这完全跳过日期选择器等复杂 UI 组件的交互。
* **工具选择策略 (Browser-Use Fusion Strategy)**:
  * **网页智能交互 (Web DOM Interaction)**: 对于所有涉及到 DOM 元素的点击、读取、表单填充，**绝对优先使用 `browser_use_worker` 工具**。禁止大模型自行猜测和拼装脆弱的 CSS Selector 进行盲试。只需向 Worker 下达人类自然语言形态的 task。
  * **基础网页导航 (Base Navigation/Inspection)**: `browser` 工具退化用作顶级导航（`navigate`）、人工视觉验证（`screenshot`）、登录态注入（`login`），或执行极少数需要的高权限 JS 注入（`evaluate`）。
  * **桌面应用及复杂网页物理兜底 (Desktop & Canvas Fullback)**: 若面临 `browser_use_worker` 达到 `max_steps` 且报错目标元素不可交互（例如 Canvas 绘制的机票座位图、Flash、跨域 iframe、OS 级别文件弹窗），必须立刻降级使用 `screen_capture(annotate_ui=True)` + `rpa(ui_name=...)` 组合进行纯物理视觉点击。
* **操作-验证闭环 (Act-Verify Loop)**:
  * `browser_use_worker` 内部已自带多步验证状态机。通过强行控制 `max_steps=3`，防止出现“Agent套娃代理死锁”。
  * 遇到 Worker 抛出失败（或循环执行多次仍无法推进），将强制熔断，并回传 `HINT` 提示。大模型接收到提示后，必须停止死磕 DOM，转换思路使用物理兜底。
* **操作历史感知 (Action History Awareness)**:
  * Agent loop 会在系统提示中注入最近的 UI 行动历史 (`_action_log`)。模型必须参考历史避免重复验证已知死胡同的同一操作元件。

## 7. 实践沉淀与避坑教训 (Lessons Learned)

⚠️ **由于未加入严格的静态类型检查，每次新开会话/开发前，必须先复习此清单，避免犯低级错误！**

1. **交互式分支容易藏雷 (Edge Flows Testing)**：Agent 系统存在大量异步挂起的次级分支（`pending_approval`, `pending_save` 等）。如果重构了基础数据结构（比如调整了 `Session` 对象属性），不能只满足于“问候语”能正常输出，必须去把 HITL / 拦截界面亲自点一遍触发。Python 不会在运行前发现分支内部的 `AttributeError`（如把 `.messages` 误写成了 `.history`）！
2. **禁止在物理层为 UX 妥协 (Decouple UX from Storage)**：永远不要为了“让用户的对话框看起来别那么啰嗦”而去用 `pop()` 和 `del` 硬删核心会话数据记录。基础上下文数据应当是 **Append-only（仅追加）** 的。要想净化用户视野，必须在发送消息的 Render 层 / View 侧通过过滤进行，绝对不允许去修改和截断持久化数据的原始排列。
3. **限制非主业务崩溃的爆炸半径**：任何类似“清理一下不要的提示语”、“发个旁路通知”的代码，**绝对不允许**让主干 Loop 崩溃退出。这些锦上添花的功能如果不确定绝对安全，一律用 `try...except Exception as e:` 包裹，哪怕失效也顶多导致“提示语没删掉”，而不是进程直接崩溃抛出 500。
4. **命名规范与防御式编程**：动词做方法（`get_history()`），名词做属性（`messages`）。脑海中的宏观概念（“我要清理历史”）不要无意识地直接点成代码（`session.history`）。如果代码缺少 `mypy` 校验，要用极其直白不出挑的命名，或在写这种无上下文的成员访问时防御性地 `getattr(obj, 'prop')` 一下来保全进程。

### 🚨 深度避坑录：P40B-1 轻量断点续传 (Crash Recovery for Tools)

在实现工具执行的断点续传（进程崩溃后恢复并主动通知外部）的测试过程中（特别是模拟长阻塞和断网崩溃等极端场景），我们结结实实踩了以下大坑，**请所有系统级开发者牢记此教训**：

5. **Server Boot Race Conditions (服务器启动时的 WebSocket 广播竞态陷阱)**：
   应用重启后，想要通过 WebSocket 向前端主动推送恢复通知，**绝对不能在 T=0 的时刻盲目发信**！Uvicorn/WebSockets 的启动以及前端 Client 的自动重连存在 1~3 秒的物理延迟。此时直接发布 `OutboundMessage` 会因为没有或者尚未就绪 Subscribers（订阅者）导致幽灵丢包（信发了，没人接，就永远丢了）。
   **避坑指南**：避免死板固定硬编码 `asyncio.sleep(5)` 等待，必须实现**基于状态的连接检测（Connection Polling）机制**，如利用 polling 或回调确认确保至少有一个活跃的客户端心跳连接后，再执行关键的重连恢复通知。

6. **Fragile Single-Path Delivery (单向通知投递的致命脆弱性)**：
   仅仅依赖单边向事件总线投递 (`Bus -> Channel Subscriber -> WebSocket`) 去传递崩溃恢复通知对于 Critical Notification 来说是极度脆弱的。
   - 当配置中 `master_identities` 为空时，没转发目标。
   - 目标频道如果单纯是一个纯前端 Dashboard，可能根本不订阅特定的出向身份路由。
   - Client 正处于页面刷新 F5 或者网络切断后的重连真空中。
   **避坑指南**：必须采用 **Dual-Path (双保险混合推送)**。即在扔给消息总线通知常规客户端的同时，单独拿出一个独立的直推 `broadcast_ws_message()` 作为保底逻辑。并且在遇到身份空洞时，硬性注入类似 `dashboard:direct` 全局 Fallback ID 覆盖，做到无论如何都能兜底触发 UI。

7. **Phantom Bugs in Background Sandboxes (完美逻辑却抓不到断点的玄学事件：幽灵崩溃与沙箱陷阱)**：
   人工测试 Crash Recovery 往往需要 Mock 长时阻塞任务（例如使用 `ping -n 55` 或 `python -c "sleep(100)"`）。**千万不要想当然地认为目标命令在 Agent 底层 subprocess 调用中的表现，等同于在你控制台 CMD 中的表现！**
   这是因为：在沙箱隔离机制中，很多环境变量与 PATH 被剔除，甚至剥离了基础 TTY 与标准输入流。这就导致许多在你的 CMD 中能原生挂起阻塞 50 秒的命令，一旦进入沙箱就因缺少重定向对象或转义剥离瞬间报错并 **极速退出**（如 `python -c "sleep(100)"` 会因为外层 Shell 把内部双引号拿掉，抛出 `SyntaxError`）。
   造成的直观后果是：系统认为命令立刻“成功执行结束了” -> 然后顺便非常完美地清除了 Checkpoint WAL 断点文件 -> 当你干掉进程重新启动以后，根本没有断点引发恢复，并让你产生“逻辑完美但就是抓不出来的玄学 Bug”的错觉！
   **避坑指南**：当遇到恢复逻辑执行不到位的情况，首要原则是：**先去验证你的 Mock 阻塞是否真的在剥离环境的沙箱中成功挂起了！**建议使用能够免疫 IO 或权限特性的绝对命令，比如 `powershell -Command "Start-Sleep -Seconds 60"`，排除 Mock 进程光速自杀的干扰。

8. **异步环境中的并发状态覆写 (Race Conditions in Context Override)**：
   在需要为并发执行的子任务或子代理（Subagent）隔离其上下文（如屏蔽特定工具库）时，**绝对禁止通过修改全局的主实例属性 (如 `self.tools = restricted_tools`) 来实现**。Python 的 `asyncio` 环境下，多个子代理与主代理同时服务时必然产生严重的资源竞争，导致权限泄露或死锁。
   **避坑指南**：必须采用**显式的参数传递 (Explicit Argument Passing)**向下流动（如追加 `tool_registry_override` 贯穿整个 Middleware 层级与上下文栈），通过函数局部变量保持调用的线程安全与纯净性。即使是 `ContextVars` 在复杂异步回调栈中也可能出现隐式泄露，不如显式传参来得强健。

9. **Stateful Dependencies in Refactoring (重构时的状态副作用黑洞)**：
   在提取或解耦长期存在于“上帝方法”（God Methods）中的逻辑（如 VLM 模型路由算法）时，一定要极其小心其对实例内部缓存机制（如 `self._vlm_provider_cache` LRU Cache）的依赖。如果在重构为静态函数或外部类方法时，错误地对字典等可变状态进行修改方式不当，或者忽视了内部的副作用更新（如 `move_to_end`），会导致 LRU 淘汰机制悄无声息地全面瘫痪（引发内存泄漏或重连风暴）。
   **避坑指南**：对于包含此类隐式状态副作用的方法提取，首选将其声明为一个需要显式注入 Cache 引用的纯净委托（例如 Router 外部方法传入实例级的缓存字典按引用修改），并在接口代码中明确保留对架构决策（如 `DESIGN-5`）的传承注释，以此划定不可越轨的状态流转边界。

10. **XML 解析不可轻信 (Untrusted Regex Extraction in Fallbacks)**：
    在补救由于大模型能力退化（或本地微调模型缺陷）导致的结构化字段丢失 (如 `empty tool_calls`) 时，采用基于正则的 Fallback 提取（例如从 `content` 抽取 `<tool_use>`）会遭遇防不胜防的假阳性与 Prompt Injection 攻击测试。
    **避坑指南**：绝对禁止无条件相信提取出的 XML 标签。必须：① 绑定当次对话运行时白名单 (`valid_tool_names` intersection) 来严格过滤不存在的意图；② 坚守“只读策略 (Read-Only)”，提取归提取，绝不要试图为了美观去破坏性地 `replace` 掉 `content` 中的 XML 原文，否则会导致 Streaming 流式合并阶段不可预料的残废；③ 提取出的补救工具必须 100% 毫无特权地流经原有的 L1+HITL 标准安全中间件拦截网。

11. **Streaming API 行为隔离的重构盲区 (Streaming API Parsing Isolation Omission)**：
    很多 LLM 代理框架在使用提供商 (Provider) 级别封装时，非流式 (`chat`) 与流式 (`stream_chat`) 经常是两段**完全解耦、独立执行**的代码分岔逻辑。在做全局级别的能力干预（如引入 XML 工具兜底解析、Trace-ID 注入等）时，往往会因为只修改了大家最熟悉的 `_parse_response()` 统一收口，而彻底遗漏了 `stream_chat` 内部由开发者手动编写的 Delta 累计与 Chunk 组装阶段！这会导致同一套逻辑在普通对话中完美生效，但一切换到流式调用就“神奇失效并摆烂报错”。
    **避坑指南**：任何涉及 LLM Provider 数据进出的架构修改（Payload 解析补救、Metric 统计、安全过滤），必须**强制保持双线同构（Dual-Path Isomorphism）**检查。即：改了 `chat` / `_parse_response`，必须捏着鼻子去 `stream_chat` / `AsyncIterator` 结构内部的最后 `break`/`finish` 组装点，把同一套业务逻辑一字不差地复现进去。不要幻想底层的统一。

12. **Windows 进程树孤儿灾难 (Windows Process Tree Orphan Disaster)**：
    在实现类似 `Coordinator` 模式的跨进程真并发调度时，如果只保留 Python 的 `Popen` 对象而不加以系统级脱离挂载（如 `CREATE_NEW_PROCESS_GROUP`），当主 Agent 意外崩溃或被强杀 (Ctrl+C) 时，会直接导致派生的大量 Worker 进程变为孤儿留守在后台，引发可怕的端口占用和 API 请求泄漏（资源风暴）。
    **避坑指南**：在涉及长期进程分离（Daemon-like Subprocess）时：① 必须在 `Popen` 唤起时附带系统级的 `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` 控制解绑（限 Windows，Unix 下使用 `start_new_session=True`）；② 必须在架构入口硬编码 `atexit.register` 注册全局清理程序；③ 不能仅仅用 Python 层面的 `process.kill()`，必须彻底用 `taskkill /F /T /PID` (Windows) 或发送 `SIGTERM` 给整个进程组来强制切断子树。

13. **Cron 副作用检测禁止依赖 LLM 文本（LLM Text vs. Structured Trace for Side-Effect Detection）**：
    在 Cron 执行引擎中，为防止重复执行已完成的副作用操作（如重复发送邮件），禁止通过解析 LLM 响应的自由文本（如匹配 `"send_email"` / `"邮件已发送"` 等关键词）来判断副作用是否执行。LLM 措辞多变，假阳性（失败的工具调用被误判为成功）会导致邮件静默丢失，假阴性（LLM 换了措辞）则导致重复发送，且多语言场景下关键词列表不可扩展。
    **避坑指南**：副作用检测必须基于底层的**结构化工具执行遥测**（如 `TraceArchive.get_tool_calls(trace_id)`），从工具调用记录中确认特定工具（如 `outlook_send_email`）的执行状态（`status == "success"`）。同样原则适用于一切"是否已执行过 X 操作"的判断场景——永远"看它做了什么"，而不是"看它说了什么"。（参见 ADR-44）

14. **Cron 重试必须有硬性熔断阈值（Retry Loops Must Have Hard Caps）**：
    在定时任务（Cron）执行失败后，若盲目追加固定间隔重试（如 15-min retry），且不设置执行次数上限，会在依赖项（如 SSRS）长期不可用时造成日内无限循环，重复消耗 API Token 并产生多封重复邮件。条件判断 `retry_ms < next_cron_run_at_ms` 无法覆盖这一场景，因为重试时刻永远早于次日自然触发时刻。
    **避坑指南**：所有有副作用的 Cron Job 必须在 State 中维护 `retry_count`，并设置明确的 `MAX_RETRIES` 熔断阈值（建议 = 1）。超出后，状态直接锁定为 `error_fatal`（不可自动恢复终态），触发最高级告警要求人工介入，并停止一切后续自动重试。新周期成功后再重置计数器。（参见 ADR-44）

15. **沙箱网络审计钩子的盲目运用（Blind Network Auditing in Sandboxes）**：
    在对 Worker 进程（如 Coordinator Worker）应用防御式的 `sys.addaudithook` 拦截网络套接字（`socket.bind`/`socket.connect`）前，必须彻底厘清目标进程的业务职能。对于单纯执行一段不受信纯计算代码的容器（无 IPC，无三方依赖），严格断网是正确的；但对于需要依靠 HTTP 微服务框架（如 `aiohttp`）等待 IPC 任务派发，且内部包含 Agent 推理大回环（需直直连 LLM API）的调度进程，直接植入 `-I` 并拦截其内核层的 `socket.bind` 将立刻导致初始化死亡（Windows `ProactorEventLoop` 对自组环回的心跳依赖），同时也会让 Agent 因报错不可达变成聋瞎。
    **避坑指南**：切忌在架构高层落实「为了安全彻底切断子进程网络」这种不切实际的“一刀切”。真正的防线应该部署在**不受信子动作触发前隙**（如隔离的 `PythonSandbox` 或 `ShellSandbox`），而不是在承担基础设施职责的调度进程顶端自残。对于核心系统 Worker，安全策略必须止步于拦截恶意原生的 `os.system` / `os.exec` 等越权动作，明文豁免 Socket 以保留其生命血脉。（参见 ADR-45 Phase 45C 避坑反思）

16. **测试 Mock 必须与接口重构同步进化（Test Mock Interface Fidelity）**：
    在重构安全中间件接口（如从 `get_risk_tier()` → `CapabilityTag` / `static_tags` + `get_effective_tags(args, config_override=)` ）后，若测试中的 `FakeTool` / `FakeRegistry` 仅更新属性值而遗漏接口签名变化（如缺少 `static_tags` 属性、`get_effective_tags` 签名不接受 `config_override` 关键字参数），会导致产品代码通过但所有涉及新路径的测试全部 `AttributeError`/`TypeError` 崩溃，制造"绿色 CI 假象"。
    **避坑指南**：在做安全/验证层的 API 重构时，必须在同一 PR 里同步更新所有测试桩（Test Doubles），且对使用真实实例（如 `ExecTool()`）的 Mock 注册表优先于手搓的 FakeTool，以保证 `evaluate_dynamic_tags()` 等运行时动态行为能被测试链条端到端覆盖。（参见 ADR-45B Phase 45B）

17. **子进程模型上下文单例泄露（Subprocess Singleton Context Leak via JSON-RPC）**：
    在通过 JSON-RPC 将任务派发给长期运行的 Worker 子进程时，如果 Worker 环境在启动（如 `__init__`）时便初始化了 `AgentLoop` 或加载了默认的 `Provider`（如固定加载了 `defaults.model`），那么在支持“异构模型请求”（即主 Agent 要求 Worker 采用特定轻量模型处理任务）时，会导致 Worker 完全无视 HTTP 负载中指定的模型参数。此外，多任务的复用会导致 Worker 在上一个任务中污染的 `ContextVars` 泄露到下一次调用。
    **避坑指南**：对于基于长轮询/常驻子进程的 RPC 架构，其状态层（如 `AgentLoop` 及 `Provider`）必须保证与 RPC Action 的生命周期绝对对齐。在处理 HTTP Request 时，必须**动态基于 Payload 中的 Context (如 model, temperature, api keys) 重新实例化推理栈**，并保证在 Finally 中重置所有的上文隔离 `ContextVars` 污染，决不能贪图省事在进程启动时共享一个实例，否则状态必毁。（参见 Phase 38A 抽象统一教训）

18. **隐式 HITL 无头死锁与大文本上下文污染 (Headless HITL Deadlocks and Worker Context Bloat)**：
    在多模型并发协作 (Manager-SubAgent) 架构中，若直接将主框架包含高级安全栅栏的 `AgentLoop` 搬迁至脱离中控的主机或子进程里，此时任何工具在检测到 `CapabilityTag.IS_HIGH_RISK` 并悬挂等待审批反馈（HITL Prompt）时，都会因为 Worker 没有合法的通道句柄接收交互，从而导致该次 SubAgent 任务永久悬挂假死。其次，Worker 输出的全量调试文本如直接回传，将引发父 Agent 产生灾难级别的上下文膨胀。
    **避坑指南**：必须建立“多级防线代理隔离模式 (Proxy-Isolated Defense)”。① 对于权限继承，必须以硬性特征在底层拦截（如：在安全中间件检测 `chat_id.startswith("worker:")`，对所有 High-Risk 动作执行强行 Abort 而非 Suspend，并返回直白报错使 LLM 主动改变策略，而不是挂起等死）；② 对于上下文回传，必须内建 Outcome-Refining 降维流标管。在 `_announce_result` 返回父总线前，强制剥离无用的过程冗杂并通过轻量 LLM 层级蒸馏文本特征，只将 “Refined Synthesis” 送返核心。 (参见 Phase 38B 多模型协作重构教训)

19. **避免深层结构的大文本上下文污染 (Avoid Heavy Structure Context Bloat in LLMs)**：
    在执行诸如批量 JSON 解析、复杂日志扫描、二进制分析等“大体量、深结构”的数据整理任务时，绝对禁止采用无脑交由大模型循环读取判断 (`ReadListDir` -> `ReadFile` -> `LLM Context`) 的暴力手法。受限于上下文长度和多层推断注意力衰减（Attention Dilution），极易发生长文本截断、错位分析和大量无意义的试探性能量消耗。
    **避坑指南**：应坚守 **“确定性优先 (Deterministic First) + 本地逻辑探针引擎”** 的双引擎驱动战略。必须首先编写纯 Native 代码（如 Python 中的条件分支）完成对数据的初筛（如错误拦截 `Error:` 或边界状态过滤），仅在高度浓缩或剪枝提拉后的最终状态集合上，才动用 LLM 去做“主观归因推理与指令产出”。切记：不要用大模型的算力去干正则表达式和过滤器的活。(参见 Phase 46B 离线经验整编教训)

20. **配置合并中的脱敏字段劫持与乐观锁覆盖陷阱 (Masked Fields Hijacking and Optimistic Lock Overwrite in Config Merges)**：
    在构建全栈的配置编辑器时，为防止 API 泄露高危密钥（如 `API_KEY`），通过在后端将敏感字段替换为占位符（如 `__MASKED__`）是一种常见做法。但在将前端用户提交的修饰层配置写回时，如果采用粗暴的全量反序列化覆盖（如 `json.dump`）或在字典深层合并（Deep Merge）时忽略了对脱敏标记的过滤，就会导致真实的生产环境配置被前端的 `__MASKED__` 字符串无情覆盖损坏。同时，在跨端管理时，因缺失了“乐观锁”控制，很容易引发修改丢失（Lost Update）。
    **避坑指南**：① 必须在后端反序列化并开启深层补丁合并前，实施精准的**脱敏 Sentinel 探针过滤（Skip Masked Values in Deep Merge）**，对所有值等于脱敏面具特征（如 `__MASKED__`）的属性保持不覆盖，以保留磁盘原始真值；② **强校验乐观锁防篡改 (Optimistic Lock Hash Check)**。强制每次 GET 读取都附带文件的 `mtime` 或特征值，并在写入节点（Write API）行尾校验比对，一遇突变立即抛出 409 Conflict 警告并中断写入，严防并发和多 Tabs 开启造成的覆盖损坏。(参见 Phase 48 仪表盘安全配置编辑教训)
