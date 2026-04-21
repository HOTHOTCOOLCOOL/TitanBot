# ADR-63: Execute Phase 回归测试强化策略

**状态**: 已采纳 (Accepted)
**日期**: 2026-04-19
**Harness 辩证轮次**: 5 阶辩证 (Sonnet Planner → Opus Critic → Gemini Pro High → Gemini Pro Low → Sonnet Final)
**关联 ADR**: ADR-62 (Azure 迁移复盘), ADR-55 (架构维护)
**受影响文件**:
- `.agent/workflows/execute_phase.md` (工作流文档)
- `docs/rules/ARCHITECTURE.md` (经验法则追加)

---

## 背景与问题陈述

`/execute_phase` 工作流在历经多个 Phase 的迭代后，暴露出一个系统性缺陷：**回归测试的执行依赖于人工操作和模型主观判断，缺乏任何结构化的防线**。ADR-62 的"测试体系三点自我反思"明确指出了该问题的严峻性：

1. **Ecosystem Blindness**：仅测"本地框架是否跑通"，忽视上游模型行为
2. **Adversarial Test 缺位**：缺乏系统在 API 异常/内容阻断时的恢复性验证
3. **框架测试脱离模型变数**：框架级验证应使用硬编码探针，而非通过 LLM Prompt 触发测试场景

此 ADR 记录 Harness 5 阶辩证对"如何强化 `execute_phase` 工作流的回归测试门控"这一命题的完整碰撞结论。

---

## 1. 迁移爆发的核心教训（根因分析）

| Opus 批判编号 | 批判等级 | 核心缺陷 | 根因 |
|---|---|---|---|
| C1 | 🔴 致命 | LLM 自生成的 Blast-to-Test 映射表是高置信幻觉 | LLM 无法对自身覆盖率盲区进行元认知 |
| C2 | 🔴 致命 | AST 扫描在大量延迟/动态 import 面前漏报率极高 | `loop.py` 等核心文件 60%+ 的依赖为函数体内动态加载 |
| C3 | 🟠 高危 | 缺少编码前绿色基线快照，pytest 红灯无法区分新旧债务 | 工作流未定义"开工前置条件" |
| C4 | 🟠 高危 | 让 LLM 自写"测试债务评估"是错误工具匹配 | LLM 会产出无意义套话或过度自信的遗漏 |
| C5 | 🟡 中危 | "≥3模块"门控阈值任意，激励扭曲 | 单文件单行改动即可摧毁 API 全链路（Phase 62 案例） |
| C9 | 🔴 致命 | 最高危的非确定性回归（模型行为驱动 Bug）完全不在守备范围 | 原工作流只防"代码破坏"，不防"语义降级" |

---

## 2. 架构决策

### 决策 1：废弃基于 LLM 的细粒度测试映射（全盘接受 C1 & C4）

**废弃**：在 `implementation_plan.md` 中要求 LLM 生成"文件 → 对应测试文件"映射表。

**原因**：LLM 无法可靠地跟踪动态依赖关系，此类映射表将以高置信度产出错误内容，制造虚假安全感——比没有映射更危险。

---

### 决策 2：废弃 `blast_radius.py` 静态扫描脚本（全盘接受 C2 & C8）

**废弃**：引入基于标准库 `ast` 的依赖反向索引脚本。

**原因**：Nanobot 代码库中大量使用函数体内延迟 import（`loop.py` 经审计超过 12 处），AST 顶层扫描漏报率不可接受。同时，该脚本本身会引入新的维护负担，违反"零额外基础设施"原则。

---

### 决策 3：引入"绿色基线快照"铁律（对应 C3）

这是本次辩证最高价值产出。

**新铁律**：编码开工前，**必须**在终端运行对应域的 `pytest` 靶向命令，确认测试基线为全绿。禁止在基线已红状态下开始编码。

**理由**：无基线则 pytest 的红/绿报告无任何诊断意义——无法区分"我炸的"与"本来就坏的"。该步骤操作成本极低（一行命令），但防御价值是决定性的。

---

### 决策 4：引入架构划区（Zone A/B/C）替代细粒度映射（折中 C1 & C6 & C7）

不要求 LLM 猜测具体文件依赖，而是强制 LLM 将改动归属至三大粗粒度架构域：

```
ZONE A（核心引擎层）
  波及: loop.py, context.py, session/manager.py, middleware/*.py, verification.py
  靶向命令: pytest tests/test_loop*.py tests/test_session*.py
            tests/test_middleware*.py tests/test_phase31*.py
            tests/adversarial/ -W ignore -v

ZONE B（工具与技能层）
  波及: tools/, channels/, skills/, cron/
  靶向命令: pytest tests/test_<具体工具>.py tests/test_channel*.py -W ignore -v

ZONE C（配置与基础设施层）
  波及: config/, docs/, scripts/
  靶向命令: 按受影响的具体模块精准执行，或无需测试
```

**折中理由**：粗粒度高置信胜过细粒度高幻觉。Zone 划区基于架构常识（非 LLM 推断），具有可重复性，且通过将 `tests/adversarial/` 默认纳入 ZONE A，直接回应了 C9 中"对抗性测试缺位"的批判。

---

### 决策 5：pytest 与 Codex 职责严格解耦（优化 C7 & C9）

两层物理串联，不可合并：

| 层次 | 工具 | 职责范围 | 触发条件 |
|---|---|---|---|
| L1 机器检查 | `pytest` | **确定性**：语法错误、接口断裂、Schema 合规、硬性契约失败 | 每次编码完成后，无条件执行 |
| L2 语义审查 | IDE Codex（跨模型） | **判断性**：角色越权、L1 正则绕过、协程泄漏、Schema null 合规破坏 | 仅在 L1 全绿后触发，且明确告知 Codex"语法已通" |

**关键指令**：告知 Codex：「语法层已通过 pytest，你的唯一任务是对照 ADR-62（Azure 安全契约）、ADR-61（L1/HITL 分层），挖掘：① 角色越权；② L1 正则被绕过的路径；③ 协程取消漏洞；④ Schema null 合规破坏。语法问题不在你的检查范围。」

---

### 决策 6：工作流文档净增 ≤ 20 行（对应 C6）

所有新增指令通过**替换原有模糊描述**而非追加实现，确保 `execute_phase.md` 从 57 行扩展至不超过 80 行，防止 LLM 在执行后期遗忘前期指令的"文档膨胀死亡螺旋"。

---

## 3. 明确不在本 ADR 范围内

- ❌ 引入 CI/CD 自动化测试管线（项目无此基础设施，违反零额外基础设施原则）
- ❌ 引入 coverage.py 覆盖率报告（需 CI 环境配合，超出当前迁移范畴）
- ❌ 自动生成 Adversarial 测试用例（非确定性测试生成违反 ARCHITECTURE.md 戒律）

---

## 4. 演化路线图

| 优先级 | 任务 | 受影响文件 |
|---|---|---|
| **P0**（本次落地）| `execute_phase.md` 四点注入（基线/Zone/职责解耦/Codex 指令精化） | `.agent/workflows/execute_phase.md` |
| **P0**（本次落地）| ARCHITECTURE.md 追加经验法则 #25（绿色基线铁律）| `docs/rules/ARCHITECTURE.md` |
| **P1**（下次 Phase）| 每次命中 ZONE A 的 Phase 完结后，确认 `tests/adversarial/` 下至少有一个对应的测试探针 | 对应 Phase 测试目录 |

---

## 参考

- `docs/adr/ADR-62-azure-openai-migration-retrospective-and-strategy.md` — 测试体系三点自反思
- `.agent/workflows/execute_phase.md` — 本次修改目标文档
- `tests/adversarial/` — 对抗性测试根目录（ZONE A 默认纳入）
- `tests/pytest_test_errors.log` — 既存债务存证（C3 批判的直接证据）
