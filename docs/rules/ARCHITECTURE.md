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

⚠️ **由于未加入严格的静态类型检查，每次新开会话/开发前，必须先复习此清单，避免犯低级错误！遇到以下场景前，必须先调用 read_file 查阅对应触发器文档！**

* [多进程/子进程/Popen 死锁孤儿相关] → [lesson-12-windows-orphan.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-12-windows-orphan.md) *(Added: Phase 40B)*
* [沙箱网络拦截导致微服务假死卡壳] → [lesson-15-sandbox-network-audit.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-15-sandbox-network-audit.md) *(Added: Phase 45C)*
* [多模型协作并发死锁上下文膨胀] → [lesson-18-headless-hitl-deadlock.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-18-headless-hitl-deadlock.md) *(Added: Phase 38B)*
* [Master API Key 暴露与凭据盗取防御] → [lesson-22-master-api-key-bff.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-22-master-api-key-bff.md) *(Added: Phase 54)*
* [长断点恢复/断网 Mock 时立刻闪退玄学] → [lesson-07-phantom-sandbox-bugs.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-07-phantom-sandbox-bugs.md) *(Added: Phase 40B)*
* **交互式分支容易藏雷 (Edge Flows Testing)**：Agent 系统存在大量异步挂起的次级分支（`pending_approval`, `pending_save` 等）。如果重构了基础数据结构（比如调整了 `Session` 对象属性），不能只满足于“问候语”能正常输出，必须去把 HITL / 拦截界面亲自点一遍触发。Python 不会在运行前发现分支内部的 `AttributeError`（如把 `.messages` 误写成了 `.history`）！ *(Added: Before Phase 40)*
* **禁止在物理层为 UX 妥协 (Decouple UX from Storage)**：永远不要为了“让用户的对话框看起来别那么啰嗦”而去用 `pop()` 和 `del` 硬删核心会话数据记录。基础上下文数据应当是 **Append-only（仅追加）** 的。要想净化用户视野，必须在发送消息的 Render 层 / View 侧通过过滤进行，绝对不允许去修改和截断持久化数据的原始排列。 *(Added: Before Phase 40)*
* **限制非主业务崩溃的爆炸半径**：任何类似“清理一下不要的提示语”、“发个旁路通知”的代码，**绝对不允许**让主干 Loop 崩溃退出。这些锦上添花的功能如果不确定绝对安全，一律用 `try...except Exception as e:` 包裹，哪怕失效也顶多导致“提示语没删掉”，而不是进程直接崩溃抛出 500。 *(Added: Before Phase 40)*
* **命名规范与防御式编程**：动词做方法（`get_history()`），名词做属性（`messages`）。脑海中的宏观概念（“我要清理历史”）不要无意识地直接点成代码（`session.history`）。如果代码缺少 `mypy` 校验，要用极其直白不出挑的命名，或在写这种无上下文的成员访问时防御性地 `getattr(obj, 'prop')` 一下来保全进程。 *(Added: Before Phase 40)*
* **Server Boot Race Conditions**：重启后通过 WebSocket 推送恢复通知不能盲目。Uvicorn/WebSockets 启动有 1~3 秒物理延迟，需实现状态连接检测 (Connection Polling)。 *(Added: Phase 40B)*
* **Fragile Single-Path Delivery**：传递崩溃恢复通知对于 Critical Notification 极度脆弱，必须采用 Dual-Path (双保险混合推送)。 *(Added: Phase 40B)*
* **异步环境中的并发状态覆写**：绝对禁止通过修改全局的主实例属性隔离特定工具库。必须采用显式的参数传递 (Explicit Argument Passing) 或 ContextVars 向下流动。 *(Added: Phase 38A)*
* **Stateful Dependencies in Refactoring**：提取“上帝方法”时极度小心内部缓存（如 `move_to_end`）依赖，谨防静默重连风暴。 *(Added: Phase 42C)*
* **XML 解析不可轻信**：Fallback 提取 XML 必须：① 绑定运行时白名单；② 坚守 Read-Only 不破坏原文结构；③ 提取出的工具流必须毫无特权地流经拦截网。 *(Added: Phase 43)*
* **Streaming API 行为隔离盲区**：任何涉及 LLM Provider 数据进出的架构修改必须强制保持双线同构（Dual-Path Isomorphism）检查。 *(Added: Phase 40)*
* **Cron 副作用检测禁止依赖 LLM 文本**：永远"看它做了什么"，而不是"看它说了什么"，必须基于结构化的工具调用记录特征判断操作是否执行。 *(Added: Phase 44)*
* **Cron 重试必须有硬性熔断阈值**：不可盲目追加重试，有副作用的定时任务必须设置 `MAX_RETRIES` 熔断阈值（建议 = 1）。 *(Added: Phase 44)*
* **测试 Mock 必须与接口重构同步进化**：更新测试桩时遗漏了新参数或特征属性会导致产品代码通过而所有测试崩溃的假象。 *(Added: Phase 45B)*
* **子进程模型上下文单例泄露**：对于复用的长轮询 Worker 子进程架构，必须在每次 RPC 请求动态重置所有的上下文和单例 Provider 配置实例。 *(Added: Phase 38A)*
* **避免深层结构的大文本上下文污染**：大量文件系统解析与过滤应坚守“确定性优先 + 本地探针引擎”用代码初筛，别让大模型直接读无意义日志猜错位信息。 *(Added: Phase 46B)*
* **配置脱敏字段劫持与乐观锁覆盖陷阱**：在编辑器回写配置时，防范 `__MASKED__` 占位符把生产环境的真 Key 覆盖，必须基于哈希乐观锁防重叠保存。 *(Added: Phase 48)*
* **分域运行隔离与严格 I/O 契约分离**：时刻区分处于 Host 域（loguru/打印丰富）还是 Tool Payload 外部脚本域（契约标准打印）。禁止越界混用。 *(Added: Phase 55)*
* **基于 AST 词法树构建自动化戒律**：机器能扫描（AST/Lint）的代码质量死角，就永远不要依靠开发者的纪律或手工 Code Review。 *(Added: Phase 55)*
* **动态注入预算控制的闭环收口 (Context Budget Single-Point Allocation)**：动态 Context 组件（如 Action History）绝对不要自行使用复杂的累加器或“倒推减法”来扣除全局 Token 尝试兜底。应当由顶层统一初始化瀑布型预算流（`_WaterfallBudget`），按层级配置静态常量拦截（如层 1 给 KG，层 2 给经验），并将不可预期的“最终海绵”（如 RAG）置于最低层吸收全部余量，从而彻底解耦核心系统提示模块的预算计算。 *(Added: Phase 57)*
* **视觉隐式降级与内存重排 (Safe Visual Silence Downgrade)**：不要把海量历史多模态快照图片的清理任务放到大模型的二次请求截断中（会让大批量的 VLM Token 账单溢出）。应当在基建层（如 `_trim_history` 中），针对过期回合，将结构内的图像实体（Base64 nodes）直接抹除并平滑转变为携带断点摘要信息的 Text Node。 *(Added: Phase 57)*
* **动态能力鉴权与静态防规避解耦 (Decouple Dynamic Authorization from Static Tools)**：禁止依赖静态工具名称（如旧版将防护死绑在 `exec` 或静态标签）进行拦截。这会导致包含侧信道的工具（如 RPA 乱入组合键热键）执行的高危指令被遗漏（语义规避）。所有工具必须通过统一鉴权接口投射运行时合成的能力 Tag（如 `DESTRUCTIVE` 或 `SENSITIVE`），拦截层一视同仁只认 Tag 不认 Tool。且鉴权函数出错时绝不静默放行（必须抛异常或 fallback），防止静默权限提升。 *(Added: Phase 61)*
* **Schema 铁律：不要对缺失进行假设规整 (Do Not Type-Cast Absences)**：当应对类似于 OpenAI Schema 的外挂校验（如 Azure OpenAI）时，决不能帮大模型“擦屁股”把原本就该为空的占位符（如包含 `tool_calls` 时的空 `content`）粗暴转换为长度为 0 的空字符串 `""`。对网关及 API Validator 来说，`""` (Empty String) 是一种具有长度类型的业务形态，而 `null` (None) 才是真正的缺失 (Omitted)。底层构建消息时，必须严格保留模型的本意与协议的原真性。 *(Added: Phase 62)*
* **身份伪装与环境拦截红线 (No Identity Masquerading)**：向大模型强制注入所谓的 "System Notice / Notification" 时，绝对不要把它打扮成 `role="user"` 进行输入（模型视角里的强干预越权）。系统后台消息应当被看作是大模型之前未完成操作所唤起的隐匿后台回调事件。要用虚拟的 `tool_call` 请求及真实的 `tool` 结果组合进行投喂，只有这样才能通过企业的审计网关及大模型自身的语境免疫排异机制。 *(Added: Phase 62)*
* **回归测试必须先锁基线，再谈前进——绿色基线铁律 (Green Baseline Before Coding)**：在任何编码开工之前，必须运行对应架构域的 `pytest` 靶向命令，将当前测试状态记录为基线。禁止以"基线未知"状态开始修改代码，否则编码后的红灯无法区分"新引入的回归"与"已存在的债务"，结果毫无诊断价值。配套原则：使用架构划区（ZONE A/B/C）而非 LLM 幻觉映射表来确定靶向测试范围；pytest（L1 确定性防线）完全绿灯后，才能触发跨模型 Codex 语义审查（L2 判断性防线）。 *(Added: Phase 63, ADR-63)*
* **禁止黑名单防御执行路径——Zone 区划是唯一正解 (Zone-based Execution Containment)**：任何试图通过"枚举危险后缀/关键词黑名单"来防止危险代码执行的方案，都是对无穷攻击面的代偿。Windows 可执行文件格式集合（`.py`, `.pyw`, `.bat`, `.cmd`, `.vbs`, `.wsf`, `.jsx`, ...）是无法枚举完的。正确方案是在"执行"而非"写入"维度上建立区划隔离（Zone A 只读源码区、Zone B 数据区、Zone C 沙箱执行区），强制所有动态代码执行的 `cwd` 锚定在 Zone C 内。写什么不重要，在哪里执行才是边界。*(Added: Phase 64, ADR-64)*
* **任何经过序列化边界的"信任标志"等于零防御 (Trust by Call Path, Not Data Field)**：不要在消息 dict 或 JSON Payload 中加入 `_trusted: True` 之类的内联信任字段。这些字段经过 JSON 序列化/反序列化后会被丢弃，或者可以被攻击者在 Payload 中直接伪造。信任必须体现在**调用路径的位置**（由哪个模块、通过哪条代码路径注入），而非数据字段的内容值。需要区分系统事件与 LLM 输出时，应在接收 LLM content 的边界处做**输出侧转义**（如将 `[System:` 转义为 `[\System:`），而不是依赖内联字段。*(Added: Phase 64, ADR-64)*
* **Context 降级必须显性化——降级通知本身不得被降级 (Explicit Context Degradation Notice)**：任何对 LLM 上下文的截断（图片删除、历史骨架化、IFCC 压缩）都必须以独立的 `role: system` 消息明确告知 LLM，且该通知必须在所有压缩机制（IFCC、`build_system_prompt()`）执行完成后注入——即放在 `build_messages()` 的最后一步，Schema Sanitizer 之前。禁止将降级通知插入 `build_system_prompt()` 内部，否则通知本身会被 IFCC 压缩，形成"关于降级的通知也被降级"的递归悖论。*(Added: Phase 64, ADR-64)*
* **跨模型协作必须 Artifact 化，禁止让用户充当消息总线 (Artifact Handoff over Human Relay)**：在 AgentManager → Codex 这类多模型协作链路中，规划、执行、回执、返工必须沉淀为固定的结构化制品（如 `codex_handoff.md`、`codex_result.md`、`codex_feedback.md`）。如果依赖用户自由转述，需求边界会漂移，审计链会断裂，返工意见也无法回放。即便暂时做不到自动派工，也只能让用户转交原始 Artifact，绝不允许把用户降级成“人肉消息队列”。*(Added: Phase 65)*
* **运行时敏感任务必须显式写出行为契约与隐藏状态，不得拿“代码看起来合理”替代真实行为验证 (Behavior Contracts over Hidden Runtime State)**：凡涉及工具副作用、安全分级、审批链路、RPA、channel、headless/visible 模式、多显示器、缓存文件、临时状态等运行时因素的任务，必须在 `execute_phase` 的 `implementation_plan.md` 中显式列出 `Behavior Contract Matrix` 与 `Hermeticity / Hidden Runtime States Checklist`，并在验收阶段执行至少一个 `Behavior Smoke Check`。如果最终人工验收发现新的 bug，必须先把该 bug 升格为确定性 red test、behavior probe 或 adversarial test，再允许宣布 phase 完成。禁止把“人工知道怎么重试/重启/绕过”当作验收通过。*(Added: Phase 61 follow-up)*
* **严守硬截断契约与防御性测试 (Strict Hard-Cap & Defensive Testing)**：对于所有有全局长度限制的组件（如特定工具内部截断），追加的截断提示符必须算在硬上限额度内，否则会因后缀超出长度而破坏上层校验契约。此外，针对字符截断的单元测试决不能仅凭循环生成元素来凑长度（若业务逻辑又同时限制了元素个数，则永远无法触发截断），必须直接构造单体极长字符串（如 `A * 4000`）以在物理层面击穿阈值，谨防由测试结构导致的假阳性绿灯（False Positive）。*(Added: Phase 67, ADR-67)*
* **Orchestration Snapshot 只能是诊断快照，真实阶段必须从 Artifact 实时派生 (Artifacts Over Snapshot State)**：对于 `state.json` 这类 orchestration 快照，禁止把上一次运行写下来的 `derived_stage` 当成真相源。`status` / `advance` / reviewer 在做任何阶段决策前，都必须先扫描当前 Artifact 文件并重新派生阶段，再选择性刷新 snapshot；否则人工篡改、陈旧缓存或跨会话残留会把流程错误推进到下一个阶段。*(Added: Harness Orchestration Phase 1 MVP)*
* **L2 审查必须具备按 Artifact 限域的离线降级路径，禁止把验收门锁死在外部 Provider 上 (Artifact-Scoped Offline L2 Fallback)**：只要 Stage 3 把语义审查定义为必经门，就不能假设 Azure endpoint、第三方网络或远端 runtime 永远可用。审查器必须优先从 `codex_handoff.md` 的 `Allowed Write Set` 或 `codex_result.md` 的 `Changed Files` 反推出本次 diff scope；当远端 reviewer 全部失败或环境禁网时，必须降级到本地确定性检查继续给出 pass/fail，而不是让整个 `execute_phase` workflow 被外部依赖永久阻塞。*(Added: Phase 65 follow-up)*
* **外部咨询工具必须按“配置契约 + 运行时注册 + 失败路径测试”成组落地 (External Consultant Tools Ship as an Atomic Contract)**：像 Copilot Studio 这类外部咨询工具，不能只写一个 `Tool` 类就算完成。`schema.py` 中的配置契约、`config.sample.json` 中的默认示例、`tool_setup.py` 的内建注册，以及覆盖成功、超时、HTTP 失败的 mock 网络测试，必须一起交付；只缺其中任意一环，系统就会出现“代码存在但运行时不可用”或“失败路径不可诊断”的假完成。*(Added: job_20260426_copilot_tool)*
* **类型化上下文预算必须在结构化层完成，禁止先扁平化再反推类型 (Budget Typed Context Before Flattening)**：当某类知识片段拥有差异化预算契约（如 `reasoning_template` 必须硬截断到 1000 字符）时，必须在仍然保留 `type` 元数据的结构化实体层完成格式化与裁剪，再落到系统提示词字符串。禁止先把 Knowledge Graph 扁平化成纯文本，再尝试从字符串中猜测“哪一段需要特殊预算”；这会让即时检索、`pre_fetched_kg` 优化路径与后续缓存路径产生双重实现和静默漂移。配套要求：实体重建流程不得擦除人工维护的类型元数据，否则任何手工蒸馏的高价值模板都会在下一次 reindex 时被无声抹掉。*(Added: job_20260503_trs_reasoning_skill)*
* **P0 可观测契约必须绑定在工具派发前，工作区边界必须沿调用链显式传递并 fail-closed (Pre-Dispatch Proof over Post-Hoc Appearance)**：凡是依赖 `<think>`、`reasoning_content`、审批 token、Allowed Write Set 这类“执行前契约”的机制，必须直接检查 provider 原始响应，并放在真正的 tool dispatch 边界之前；绝不能等 `add_assistant_message()`、schema sanitization 或持久化落库之后，再靠历史消息“看起来像是有计划”来补判。与此同时，像 workspace 这样的安全边界上下文必须由 middleware 显式传入验证层，异常分支必须带诊断并 fail-closed；`except Exception: pass` 这类静默降级会把安全规则退化成纸面合同。*(Added: Phase 68 paper integration)*
* **成功 / 轨迹 / 知识账本必须只消费已执行调用，禁止把模型提案当成事实 (Executed-Only Bookkeeping)**：像 `LoopResult.tool_calls_with_args`、`pending_save["steps"]`、`session.last_tool_calls`、trace dump、`memory/tasks.json` 这类会影响后续记忆、回放、审计或提示词注入的步骤账本，必须只从真正经过 ToolExecutor 的调用派生，而不能直接复用 `response.tool_calls` 之类的 pre-dispatch proposal 列表。L1 block、HITL reject、middleware abort 等“未执行即终止”的路径本质上都只是提议，不得被写进成功步骤、trace 或知识沉淀；验收时必须检查持久化证据里 blocked proposal 不存在，而不是只看最终回复“像是成功”。执行与否的判据也必须绑定在真实执行路径上（例如 post-executor results），不能偷懒地绑定到某一个特定错误字符串。*(Added: Phase 68 write boundary contract)*
