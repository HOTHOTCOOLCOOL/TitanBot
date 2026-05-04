# Review Packet

## Findings

1. **[High] 信任边界倒置**
   `draft_v1.md` 把 `SKILL.md -> LLM normalizer -> skill_ssl` 提升成 PSV 的前置边界，但当前命名源码里的真实拒绝执行边界仍然是代码级校验和通用 L1 规则，不是文档派生元数据。`SkillsLoader` 当前只是读取 `SKILL.md` 并把原文注入上下文，真正的 pre-execute 拦截来自 `validator.py` / pre-hooks；`VerificationLayer.check_rules()` 运行的是纯 Python 规则拦截。见 `nanobot/agent/skills.py:103-143`, `nanobot/agent/skills.py:800-840`, `nanobot/agent/verification.py:710-760`。如果不明确写死“SSL 只能收紧、不能授权、且永远不能覆盖 AST/validator 的 deny”，这个方案会把不可信文档和 LLM 产物错误地抬成安全边界。

2. **[High] `verification.py` 的运行时接线点没有定义**
   草案声称 `verification.py` 会把 planned tool calls 和 SSL Logical layer 对比，然后在 AST Sandbox 之前拦截。但 `VerificationLayer.check_rules()` 当前只接收 `tool_calls/messages/registry/config/workspace`，没有 skill identity、没有 KG handle、也没有从抽象动作（如 `READ local_file` / `CALL external_api`）映射到具体 tool args 的结构化规则接口。见 `nanobot/agent/verification.py:710-760`。在这个缺口补上之前，`L1: Validating against SSL boundary...` 很容易退化成日志或字符串匹配，而不是可靠的 fail-closed 拦截。

3. **[High] Prompt budget 叙述和现状不一致**
   草案写的是运行时只注入 Scheduling layer，且 `ContextBuilder` 预算是 1000 chars；但当前代码里 active skills 仍然直接注入完整 `SKILL.md`，预算是 `_SKILL_INJECTION_BUDGET = 8000`。现有 1000 chars 上限只对 KG `reasoning_template` 的 summary 生效，不对 skill 生效。见 `nanobot/agent/context.py:27-28`, `nanobot/agent/context.py:73-117`, `nanobot/agent/context.py:141-160`。如果不明确替换或短路原始 `SKILL.md` 注入路径，草案声称的 token 节省和注入面收缩都不成立，只会新增第二套表示。

4. **[Medium] Index-time lifecycle、失效策略、依赖优先级都没有落到现有 loader**
   草案反复使用“registration lifecycle intercept / index-time normalization / KG write”这套说法，但当前命名源码里 `SkillsLoader` 只有枚举/读取 `SKILL.md`、执行 pre-hooks/validator、以及基于 `SKILL.md` mtime 更新 `skills_registry.json` 的逻辑；看不到 KG 写入 hook，也看不到 baseline 里说的 “Memory Manager state tracking the registration pipeline of a new skill”。见 `nanobot/agent/skills.py:57-143`, `nanobot/agent/skills.py:1024-1106`。同时现有 skill 依赖解析还是 `depends_on` 配置链，不是 SSL 结构层。见 `nanobot/agent/skills.py:595-638`。草案没有说明旧依赖系统和新 SSL 依赖语义谁优先，后续会出现双源真相和陈旧图。

## Must Keep

- 保留“AST Sandbox / 代码级 validator 仍是最终 source of truth，SSL 只是 index-time supplement”这个前提，不要后移或弱化。
- 保留 `False Positive Success Paths` 这一节，尤其是 `Silent Bypass` 和 `Hallucinated Constraint` 两个反例；这部分是在对的地方攻击假阳性。
- 保留“normalizer prompt injection”和“normalizer parse fail-closed”这两个未验证项，不要在 `candidate.md` 里提前写成已解决。
- 保留“static docs layer vs dynamic AST layer”这个 trade-off 框架，但不要把它偷换成“已经多了一层可信安全边界”。

## Weak Claims / Unverified Claims

- `baseline.md` 给出的 `docs/adr/ADR-56-preflight-skill-verifier.md` 路径在仓库中不存在，Claim 2 的证据链当前是断的。
- `baseline.md` 的 Claim 3 引用 “Recent Phase 68/Job 20260503 ReasoningSkill KG Prompt Budget integration”，但没有给出明确 repo 文件路径；按 Critic 读取约束，这一条不能独立核实。
- `baseline.md` 中的 “Memory Manager state tracking the registration pipeline of a new skill” 没有在允许读取的命名源码里看到落点。
- `baseline.md` 里的 Observable Proof Signals (`L0: Normalizing...`, `skill_ssl` 写入, `L1: Validating against SSL boundary...`) 目前都是目标信号，不是从命名源码已存在逻辑中观察到的信号。
- `draft_v1.md` 的 “max 1000 chars” 目前只和 `reasoning_template` 相关，不能直接当成 `skill_ssl` Scheduling layer 的现成预算约束。

## False Positive Risks

- 系统日志显示已经生成并存储 `skill_ssl`，但 `ContextBuilder` 仍然注入完整 `SKILL.md`；外部看起来像“预算压缩成功”，实际 prompt 面没有缩小。
- 系统日志显示 `L1: Validating against SSL boundary...`，但底层仍是通用规则或 `str.contains()` 风格匹配；外部看起来像“边界校验成功”，实际没有结构化 capability enforcement。
- KG 中存在 `skill_ssl`，但 loader 只跟踪 `SKILL.md` mtime；`validator.py`、`hooks.py` 或 Python 实现变化后，旧图仍被继续使用，外部看起来像“索引已同步”，实际已经漂移。
- 现有 `depends_on` 配置链继续驱动依赖注入，而评审/文档误以为 SSL Structural layer 已经接管依赖框架；外部看起来像“SSL dependency framework 生效”，实际只是旧逻辑仍在工作。
- 如果 normalizer 解析出一个“更严格”的逻辑层，但 AST/validator 根本没有命中对应资源类别，团队会误以为系统已经得到更强安全边界，实质上只是多了一层不可验证的文档摘要。

## Acceptance Checklist

| A# | Claim | Evidence Method | Proof Signal | Expected Result | If Fail |
| --- | --- | --- | --- | --- | --- |
| A1 | `skill_ssl` 不会被提升成可授权的安全边界；它最多只能收紧，不能覆盖 AST/validator 的 deny。 | 构造一个 `SKILL.md` 声称“只读”的 skill，但其 `validator.py` 或代码路径明确拒绝某类操作；同时让 SSL graph 对该操作给出 allow。 | 运行时出现代码级 deny 证据，且日志/状态明确记录 deny 的优先级高于 SSL allow。 | deny 生效；执行被阻断；不会因为 SSL allow 而放行。 | 说明方案把不可信元数据抬成了授权源。 |
| A2 | `verification.py` 真的存在“tool call -> capability -> SSL Logical layer”的结构化匹配，而不是日志或字符串匹配。 | 用至少两类具体 tool call 做正反例测试，例如一个应命中 `READ local_file`，一个应命中 `CALL external_api`。 | 每次拦截或放行都能给出明确 capability id / path / matched boundary，而不是模糊文本。 | allow/deny 是确定性的、可追溯的、与具体工具参数绑定。 | `L1 SSL validation` 只是表象，不是机制。 |
| A3 | 引入 Scheduling layer 后，`ContextBuilder` 不再继续注入完整原始 `SKILL.md`，或者明确有单一优先级和预算口径。 | 对一个超长 `SKILL.md` 的 skill 构建 system prompt，检查最终注入内容。 | Prompt 中只出现预算内的 scheduling 表示，或有清晰可检验的单一路径；没有“raw SKILL.md + scheduling summary”双注入。 | token 节省和注入面收缩是真实的。 | 草案的 budget/security 收益不成立。 |
| A4 | `skill_ssl` 的失效/重建不只看 `SKILL.md` mtime，还覆盖代码、`validator.py`、`hooks.py` 或其他实际执行边界变化。 | 只修改 skill 的 Python 实现或 `validator.py` / `hooks.py`，不改 `SKILL.md`，再触发 reload/register。 | 旧 `skill_ssl` 被重建、标 stale、或直接阻断使用；不会静默沿用旧图。 | 不会出现“代码变了但图没变”的静默漂移。 | 新增一套长期陈旧且误导性的边界缓存。 |
| A5 | Normalizer 面对 malformed / adversarial `SKILL.md` 时会 fail-closed，而不是写出看似合法但不可信的 graph。 | 输入包含 prompt injection、schema 欺骗、超长冗余描述、故意冲突声明的 `SKILL.md`。 | 归一化失败时没有 `skill_ssl` allow 路径，且系统明确标记该 skill 未验证或不可用于边界判定。 | 不可信输入不会获得更宽权限，也不会产生“已验证”假象。 | 打开新的 prompt injection/安全剧场入口。 |
| A6 | 现有 `depends_on` 依赖系统与 SSL Structural layer 的优先级已被明确，不会形成双源真相。 | 构造一个 skill，让 `depends_on` 与 SSL Structural layer 给出冲突依赖。 | 日志/状态/Artifact 中有单一且稳定的优先级规则。 | 同一 skill 的依赖解析只有一个可信解释。 | 依赖框架迁移是不完整的，运行结果会随入口不同而变化。 |
| A7 | KG 确实支持 `skill_ssl` 作为可查询、可格式化、可被 `ContextBuilder`/PSV 消费的实体，而不是 generic summary 假装可用。 | 注册一个 skill 并执行一次 KG 写入与查询，再检查 ContextBuilder/verification 实际消费的数据形态。 | 能看到 `skill_ssl` 的层级化字段被保留并按用途消费，而不是退化成一段 `summary` 文本。 | `skill_ssl` 是真实数据接口，不是概念占位。 | Claim 3 仍然是未证实前提，后续设计无法落地。 |
