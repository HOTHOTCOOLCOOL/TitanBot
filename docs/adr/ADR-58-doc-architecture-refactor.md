# ADR-58: Documentation Architecture Refactoring (Docs-as-Context)

## 1. 状态 (Status)
**Accepted** — 经过 5 阶段 Harness 多模型辩证验证（Planner → Opus Critic → Gemini 重构 → Gemini 校验 → Claude 定稿）于 2026-04-17 通过。

---

## 2. 背景与痛点 (Context & Problem Statement)

随着 Nanobot 项目经历了多轮架构演进（从简单的单体设计到多模型协作、7层记忆、RAG 强化等），核心规则文档 `docs/rules/ARCHITECTURE.md` 呈现出以下**已确认**问题：

1. **文件内容物理重复 (Duplication Bug)**：`ARCHITECTURE.md` 第 91~260 行是第 1~90 行的完整二次粘贴，导致文件虚胖至 46k 字节。此为最高优先级缺陷，凌驾于所有其他重构动作之上。
2. **教训编号跳跃**：第 20 条之后直接跳至第 22 条，第 21 条缺失，内部自洽性受损。
3. **格式风格不统一**：§1–§6 章节使用无序列表 (`*`)，§7 章节使用有序列表，混用导致阅读体验割裂。
4. **缺乏版本时间戳**：每条教训未标注添加于哪个 Phase/时间，无法做过期判断。
5. **Tests 目录扁平化**：`docs/` 根目录下散落数十个 `phase_X_manual_test_guide.md`，噪声严重。
6. **长教训与启动载入冲突**：`ARCHITECTURE.md` 作为 `BOOTSTRAP_FILES` 之一，在每次会话启动时被完整加载进系统提示。随着含完整代码块的教训持续累积，有逼近 8000 字符注入预算上限（Rule 1.4 自我约束）的风险。

---

## 3. 关键约束（辩证确认）

> [!WARNING]
> `docs/rules/ARCHITECTURE.md` 的**文件路径不得修改**。
> 该路径在以下位置硬编码：`context.py (L24)`, `test_phase33_browser_rpa_fusion.py (L266)`, `CONTEXT_TIERING_TEMPLATE.md (L39, L62)`, `outlook.py (L149)`, `verification.py (L17)` 以及多篇 ADR。
> 任何路径变更将导致 CI 失败与 6+ 文件同步修改负担。

> [!IMPORTANT]
> 不得修改 `context.py` 的 `BOOTSTRAP_FILES` 机制。替代方案应利用现有基础设施（`read_file` 工具）实现按需加载，不引入新的路由基础设施。

---

## 4. 决策方案 (Accepted Solution)

### 4.1 核心创新：链式载入 (Hyperlinked Progressive Disclosure)
沿用 `ARCHITECTURE.md` 加入 `BOOTSTRAP_FILES` 的现有结构不变，但重写其 §7 的内容策略：

- **§1–§6（核心戒律）**：全量保留，因其是高频拦截指令，必须每次启动对 LLM 可见。
- **§7（教训沉淀）**：将含大量代码示例的长教训迁移到 `docs/rules/lessons/` 独立文件，在 §7 原位置替换为 **"一句触发摘要 + 绝对路径超链接"**。

```markdown
## 7. 实践沉淀与避坑教训 (Lessons Learned)
⚠️ 遇到以下场景前，必须先 read_file 查阅对应文档，以防导致生产崩溃：
- [多进程/子进程/Popen 相关开发] → [lesson-12-windows-orphan.md](file:///d:/Python/nanobot/docs/rules/lessons/lesson-12-windows-orphan.md)
- ...仍在 ARCHITECTURE.md 原地但已截短的低体积教训...
```

**优势**：Agent 看到摘要钩子（Trigger Hook）时，会利用内置的 `read_file` 工具主动加载完整内容。零新增架构代码，完美利用 Nanobot 现有能力。

### 4.2 实施分三阶段
| 阶段 | 改动内容 | 破坏性 | 优先级 |
|------|----------|--------|--------|
| **Phase A 手术修复** | 删除重复内容 (L91-260)、修复编号跳跃、统一列表格式、补 Phase 标签 | 零风险 | 立即执行 |
| **Phase B 目录归档** | 新建 `docs/tests/manual_guides/`，移入所有 `phase_X_..._guide.md` | 极低风险 | 随后执行 |
| **Phase C 链式载入重写** | 新建 `docs/rules/lessons/`，提取最长教训至独立文件，§7 改写为触发器列表 | 低风险 | 最后执行 |

### 4.3 明确排除事项 (Out of Scope)
- ❌ 不修改 `docs/rules/ARCHITECTURE.md` 文件路径
- ❌ 不修改 `context.py` 的 `BOOTSTRAP_FILES`
- ❌ 不修改 `test_phase33_browser_rpa_fusion.py` 的路径断言
- ❌ 不新增任何 RAG 路由/Meta-Router 基础设施
- ❌ 不新增 `core/`、`contracts/`、`research/` 等无管理者的过度拆分目录

---

## 5. 预期结果 (Consequences)

### Positive
- 消除文件重复 Bug，ARCHITECTURE.md 体积降至约 130 行真实内容。
- 系统提示词中 §7 教训区域从数千字压缩为轻量触发列表，显著节省 Bootstrap Token。
- `docs/` 根目录清爽化，所有测试指南归档。
- 未来教训可无损扩展至独立 lesson 文件，不再膨胀系统提示。

### Negative
- 短期需要人工核查哪些 lessons 体积足够大以值得提取（建议标准：含完整代码块且超过 20 行）。

---

## 6. 验证标准 (Verification)
- [ ] `ARCHITECTURE.md` 不再含内容重复（grep 检查无重复段落）
- [ ] `ARCHITECTURE.md` 教训编号连续（1-N 无跳跃）
- [ ] `context.py` L24 `BOOTSTRAP_FILES` 断言测试仍通过
- [ ] `docs/tests/manual_guides/` 包含所有迁移的测试指南
- [ ] `docs/rules/lessons/` 内的 lesson 文件均含有 `// Added: Phase XX` 标签

---

*Harness 参与模型：Claude 3.5 Sonnet (P1 Planner) → Claude Opus (P2 Critic) → Gemini Pro High (P3 V2 Architect) → Gemini Pro Low (P4 Validator) → Claude Sonnet (P5 Final)*
