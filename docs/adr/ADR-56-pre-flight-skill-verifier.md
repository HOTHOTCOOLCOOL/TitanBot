# ADR-56: Pre-flight Skill Verifier (PSV)

**Status:** Proposed  
**Date:** 2026-04-17  
**Deciders:** Harness 5-阶辩证工作流 (Planner → Opus Critic → Gemini Pro → Gemini Low Validator → Sonnet Final)  
**Source Papers:** AutoHarness (arXiv 2603.03329, DeepMind), M* MSTAR (arXiv 2604.11811, CityU & Microsoft)

---

## 1. 背景与动机 (Context)

### 论文来源

本 ADR 源自对两篇前沿论文的系统性分析（见 `paper_analysis_report.md`）：

- **AutoHarness** (Google DeepMind, 2603.03329v1): 提出 LLM 自动编写动作拦截器 (Code-as-Harness)，使 Gemini-Flash 在游戏环境中以 100% 合法动作率击败 Gemini-Pro。核心理念：不依赖模型内部世界观，而是让模式的代码生成能力构建**外部可验证的约束程序**。
- **M\* MSTAR** (CityU & Microsoft, 2604.11811v1): 将记忆系统抽象为可进化的 Python 程序，证明不同任务需要不同的存储拓扑。引出了"Skill 级别的专属存储逻辑"构想（最终在辩证过程中仅保留其思想精华，实现路径被重构）。

### 现状痛点

Nanobot 现有的 Skill 执行路径（Phase 22B Dynamic Hooks）存在一个防御空白：当 LLM 生成的动作参数违反某个 Skill 的隐式约束时（如向危险路径写文件、向外部域名发送敏感数据、执行危险 SQL），当前系统只能：

1. 让 Skill `main.py` 内部抛出原生异常（无结构化拦截原因）
2. 或依赖 Phase 28B 沙盒的进程级隔离（粒度过粗，无法表达业务级约束）

**缺少的层次：** 基于 Skill 业务规则的、结构化的、低延迟的前置动作校验。

---

## 2. 决策 (Decision)

引入 **Pre-flight Skill Verifier (PSV)**：允许每个 Skill 携带一个可选的 `validator.py`，在 Skill 执行前通过 AST 安全扫描后以 `importlib` 同进程加载运行，以结构化异常拦截非法动作。

### 核心决策依据

#### 保留自 Draft V1 的设计

| 保留项 | 理由 |
|---|---|
| AutoHarness 启发的 Skill 级别前置防御理念 | Harness 哲学本身适用于 Nanobot 的 Skill 边界控制 |
| 在 `_run_pre_hooks` 之前插入独立验证阶段 | 分层干净，不污染现有 Phase 22B Hook 体系 |
| `validate(action, context) -> None` 标准化接口 | 可插拔性的前提，不可动摇 |
| 与 Phase 55 异常体系的对齐 | 新特性必须是现有体系的自然延伸 |

#### 采纳自 Opus 极端批判的修正

| Opus 批判 | 最终决定 |
|---|---|
| LLM 零样本生成 validator 不可靠 | **删除** SaveSkillTool 自动生成逻辑；validator 只由人工或 `onboard.py` 引入 |
| 静默 HookResult 造成黑箱效应 | 改为显式 `ToolValidationFailure` 异常，消息直接投递 LLM |
| Subprocess 造成 200-500ms 冷启动 | 改为 `importlib` 同进程加载 + ThreadPoolExecutor 超时保护 |
| Reload 覆盖人工调整的 validator | 落盘后绝不自动覆盖；只有 `onboard.py` 显式指定才能更新 |
| SQLite Local Memory (M*) 引入二进制态、锁机制等架构风险 | **Feature B（SQLite 本地化记忆 Schema）整体删除**，JSONL 底线守住 |

#### Trade-off 决策备忘

| 冲突点 | 决策 | 理由 |
|---|---|---|
| Validator crash → 拦截 vs 放行 | **放行 + warning** | 坏 validator 不能成为服务拦截器；安全性由 Phase 28B 沙盒托底 |
| ThreadPoolExecutor timeout 默认值 | **200ms** | 大于所有纯计算 validator 的合理上限；不影响主循环响应 |
| Validator 对 context 的读写权限 | **深拷贝传入，零副作用** | 强制前置验证无状态，杜绝 validator 成为隐藏的数据变异点 |

---

## 3. 实施规范 (Implementation Spec)

### 3.1 异常体系扩展

```python
# nanobot/utils/exceptions.py — 追加

class ToolValidationFailure(ToolExecutionError):
    """
    Raised by a Skill's validator.py before execution begins.
    The message is safe to surface directly to the LLM message queue.
    """
    def __init__(self, reason: str, skill_name: str):
        super().__init__(f"[{skill_name}] Pre-flight validation blocked: {reason}")
        self.skill_name = skill_name
        self.reason = reason
```

### 3.2 AST 安全扫描（严禁导入列表）

```python
# nanobot/agent/skills.py

_VALIDATOR_BLOCKED_IMPORTS = {
    "os", "subprocess", "socket", "requests", "urllib",
    "httpx", "shutil", "pathlib", "sys", "ctypes",
    "importlib", "builtins", "pickle", "shelve"
}
```

### 3.3 Validator 加载器

```python
def _load_validator(skill_dir: Path, skill_name: str):
    """
    Load validator.py via importlib after AST safety scan.
    Returns the module, or None if validator.py doesn't exist.
    Raises SkillLoadError if AST scan fails.
    """
    validator_path = skill_dir / "validator.py"
    if not validator_path.exists():
        return None

    source = validator_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) \
                    else ([node.module] if node.module else [])
            for name in names:
                root = name.split(".")[0]
                if root in _VALIDATOR_BLOCKED_IMPORTS:
                    raise SkillLoadError(
                        f"[{skill_name}] validator.py blocked: forbidden import '{root}'"
                    )

    spec = importlib.util.spec_from_file_location(
        f"nanobot.skill_validators.{skill_name}", validator_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

### 3.4 Validator 执行器

```python
def _run_validator(
    validator_mod,
    action: str,
    context: dict,
    skill_name: str,
    timeout_ms: int = 200,
) -> None:
    """
    Execute validator.validate() with a deep-copied context (zero side effects).
    - Raises ToolValidationFailure on rejection.
    - Raises ToolValidationFailure on timeout.
    - On validator crash: logs warning, allows through (fail-open).
    """
    import copy, concurrent.futures

    ctx_copy = copy.deepcopy(context)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(validator_mod.validate, action, ctx_copy)
        try:
            fut.result(timeout=timeout_ms / 1000)
            # validate() raises ToolValidationFailure to block; returning None = allow
        except ToolValidationFailure:
            raise
        except concurrent.futures.TimeoutError:
            raise ToolValidationFailure(
                f"validator timed out after {timeout_ms}ms", skill_name
            )
        except Exception as e:
            logger.warning(f"[{skill_name}] validator.py crashed: {e!r} — skipping safely")
```

### 3.5 execute_skill() 集成点

```python
async def execute_skill(skill_name: str, action: str, payload: dict, ...) -> SkillResult:
    skill = _get_skill(skill_name)

    # ── Pre-flight validation ─────────────────────────────
    if skill.validator_mod is not None and get_config().agents.validator.enabled:
        _run_validator(
            skill.validator_mod,
            action=action,
            context=payload,
            skill_name=skill_name,
            timeout_ms=get_config().agents.validator.timeout_ms,
        )
    # ──────────────────────────────────────────────────────

    await _run_pre_hooks(skill, payload)
    result = await _invoke_main(skill, action, payload)
    await _run_post_hooks(skill, result)
    return result
```

### 3.6 Config Schema 扩展

```python
# nanobot/config/schema.py

class ValidatorConfig(BaseModel):
    enabled: bool = True
    timeout_ms: int = Field(default=200, ge=50, le=5000)

class AgentsConfig(BaseModel):
    # ... 现有字段 ...
    validator: ValidatorConfig = Field(default_factory=ValidatorConfig)
```

---

## 4. Skill 目录约定

```
skills/
  <skill-name>/
    SKILL.md          ← 现有
    main.py           ← 现有
    config.json       ← 现有
    validator.py      ← 【可选，手动提供，框架不自动生成/覆盖】
    memory/
      executions.jsonl
```

### Validator 编写五戒

1. **纯计算函数**：不得有 I/O、网络、文件系统操作
2. **零副作用**：不得修改传入的 `context`（框架将传入深拷贝）
3. **明确拒绝原因**：`ToolValidationFailure` 的 message 将直接出现在 LLM 消息队列中，须为人类可读的业务描述
4. **不自动生成**：只由人工或 `onboard.py` 在知情情况下引入
5. **不被覆盖**：落盘后框架绝不自动删除或重写

### Validator 示例

```python
# skills/excel-actuator/validator.py
from nanobot.utils.exceptions import ToolValidationFailure

ALLOWED_SHEET_PATTERNS = {"Sales*", "FF*", "Summary"}

def validate(action: str, context: dict) -> None:
    if action == "write_cell" and context.get("sheet") == "protected_config":
        raise ToolValidationFailure(
            "'protected_config' sheet is read-only. Use 'Summary' or 'Sales*' sheets.",
            skill_name="excel-actuator"
        )
```

---

## 5. 受影响文件清单

| 文件 | 变更类型 |
|---|---|
| `nanobot/utils/exceptions.py` | MODIFY — 新增 `ToolValidationFailure` |
| `nanobot/agent/skills.py` | MODIFY — 新增 `_load_validator()` / `_run_validator()` / 集成到 `execute_skill()` |
| `nanobot/config/schema.py` | MODIFY — 新增 `ValidatorConfig` |
| `docs/adr/ADR-56-pre-flight-skill-verifier.md` | NEW — 本文件 |
| `progress_report.md` | MODIFY — 添加 Phase 56 条目 |
| `tests/test_phase56_validator.py` | NEW — 25+ 测试用例 |

---

## 6. 验证计划 (Verification Plan)

```bash
# 单元测试
python -m pytest tests/test_phase56_validator.py -v

# 回归测试（确保现有 Skill 不受影响）
python -m pytest tests/ -k "skill" -v

# 手动冒烟：在无 validator.py 的 Skill 上执行，确认行为不变
# 手动冒烟：在有 validator.py 的 Skill 上触发违规动作，确认 LLM 收到明确拒绝信息
```

---

## 7. 明确不在本 ADR 范围内的事项

- ❌ SQLite Task-Optimized Local Memory (已在辩证第三阶段删除，未来若有需求单独立 ADR)
- ❌ LLM 自动生成 validator（零样本不可靠，已在辩证第三阶段删除）
- ❌ Tree-Search Rollout 系统（违背单机单体哲学）
- ❌ `validator.py` 热重载逻辑（validator 是静态防线，不应随 `/reload` 动摇）
