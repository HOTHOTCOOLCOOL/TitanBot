# ADR-55: Architecture Maintenance — 技术债还款与代码健壮性加固

**状态**: ACCEPTED  
**日期**: 2026-04-17  
**来源**: Phase 54 Harness 5 阶辩证审查  
**作者**: TitanBot 架构委员会（5-phase harness; Sonnet Planner → Opus Critic → Gemini Pro Reconstructor → Gemini Low Validator → Sonnet Final）

---

## 背景与动机

在 Phase 38–53 的高速迭代中，项目在功能层面取得了显著成果（IFCC、KG-Wiki、M-RAG、GroupRAG、Excel RPA），但工程质量出现了明显的"腐化漂移"。可量化指标如下：

| 指标 | 扫描结果 |
|------|----------|
| Ruff 静态警告总数 | **1930 个**（运行 `ruff check nanobot`） |
| 裸 `print()` 调用 | **127+ 处**（全局搜索） |
| 泛型 `except Exception:` | **370+ 处**（大量 async 协程未守卫 CancelledError） |
| Unused imports (F401) | **多处**，含高危 side-effect import 被误删风险 |
| ADR-53 COM 死锁防御 | **空白**（`os.kill` 会伤及主体，激活时机无评估机制） |

这些技术债不再是"可以推迟"的选项，而是**系统在现有规模下继续高频迭代的重要阻力**。

---

## 核心架构决策

### 决策 1：代码域双轨制（最重要的新范式）

本次维护的最核心产出是首次**显式确立代码域边界**，并为两个域规定不同的 I/O 规范：

```
┌─────────────────────────────────────────┐
│         Host Agent 体系                  │
│  nanobot/agent/                          │
│  nanobot/providers/                      │
│  nanobot/session/                        │
│  nanobot/plugins/                        │
│  nanobot/utils/                          │
│                                          │
│  规则：                                  │
│  ✅ 所有输出必须通过 loguru logger        │
│  ❌ 禁止裸 print()                        │
│  ❌ 禁止 async 函数中吞噬 CancelledError  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         Tool Payload 体系                │
│  nanobot/skills/*/fetch_report.py        │
│  nanobot/scripts/*.py                    │
│  (未来: 任何被 ExecTool subprocess 调用) │
│                                          │
│  规则：                                  │
│  ✅ stdout = IPC API 契约，神圣不可侵犯  │
│  ✅ 诊断信息必须写入 sys.stderr           │
│  ❌ 禁止引入 loguru（会污染 stdout 流）  │
│  ❌ 禁止 stdout 添加时间戳/层级前缀      │
└─────────────────────────────────────────┘
```

**背景**：`fetch_report.py` 等 Skill 脚本被 `ExecTool` 以 subprocess 方式调用，其 `stdout` 是父 Agent 捕获并注入 LLM 上下文的原始数据。若将其迁移为 loguru 输出（含时间戳前缀），父进程的 JSON/CSV 解析器将彻底崩溃。Opus 批判阶段发现了这一严重误判，Gemini Pro 重构阶段将其提升为首要架构洞察。

---

### 决策 2：Async 协程 CancelledError 守卫红线

**问题**：`except Exception:` 在 async 函数中会静默吞噬 `asyncio.CancelledError`（Python 3.8 以前 `CancelledError` 继承自 `Exception`，Python 3.8+ 修复，但 `except Exception` 仍可捕获部分 cancellation 异常），导致长时间运行的协程无法优雅退出、资源泄露、Event Loop 无法关闭。

**强制改造模板**：

```python
# ❌ 危险（async 函数）
except Exception as e:
    logger.warning(f"Error: {e}")
    return None

# ✅ 安全
except Exception as e:
    if isinstance(e, asyncio.CancelledError):
        raise  # 协程控制流不可截断，必须向上传播
    logger.exception("Unexpected fault")
    raise ToolExecutionError(f"Operation failed: {e}") from e
```

**高危目标文件**（按优先级）：
1. `nanobot/plugins/browser_session.py`（12 处）
2. `nanobot/plugins/browser_use_worker.py`（4 处）
3. `nanobot/providers/litellm_provider.py`（4 处 streaming 回调）

---

### 决策 3：统一异常类库（`exceptions.py`）

新建 `nanobot/utils/exceptions.py`，集中定义项目的异常层次结构：

```python
class NanobotError(Exception):
    """所有 Nanobot 自定义异常的基类。"""

class ProviderExecutionError(NanobotError):
    """LLM Provider 执行失败（超时 / 解析错误）。"""

class ToolExecutionError(NanobotError):
    """Tool 执行失败（权限拒绝 / 沙箱阻断 / 运行异常）。"""

class SessionPersistenceError(NanobotError):
    """Session 持久化失败。"""
```

**理由**：当前 Provider 和 Session 层捕获 Exception 后仅 `pass` 或 `return None`，上层调度完全无法感知硬故障。引入结构化异常类后，`manager.py` 能根据异常类型触发精确的降级路径或 HITL 上报。

---

### 决策 4：COM 精准防御（放弃危险的 `os.kill`）

**原问题设计的危险性**：`os.kill(self_pid)` 会终止 Nanobot 主进程本身；即使是杀 Excel，也可能误伤用户已打开的其他工作簿（同进程多实例）。

**最终方案**：

```python
# 启动时记录精确 PID
excel = win32com.client.DispatchEx("Excel.Application")  # 独立进程隔离
hwnd = excel.Hwnd
_, excel_pid = win32process.GetWindowThreadProcessId(hwnd)

# 超时时精准回收
try:
    result = await asyncio.wait_for(
        asyncio.to_thread(self._run_excel_automation),
        timeout=120.0
    )
except asyncio.TimeoutError:
    subprocess.run(["taskkill", "/F", "/PID", str(excel_pid)])
    logger.warning(f"COM deadlock: force-killed Excel PID {excel_pid}")
    # 触发 HITL 上报
    raise ToolExecutionError("Excel COM automation timed out (120s)")
```

使用 `DispatchEx` 而非 `Dispatch`，确保每次启动的是**独立进程**（非附加到已有 Excel 实例），从而 PID 唯一且可精准回收。

---

### 决策 5：Ruff 修复策略（拒绝一刀切）

| Ruff 类别 | 处理方式 | 理由 |
|-----------|----------|------|
| I（Import 排序）| 自动 `--fix` | 无业务破坏性 |
| W291/W293（空格）| 自动 `--fix` | 无业务破坏性 |
| F401（Unused import）| **人工分组核查** | Side-effect import / re-export 有破坏风险 |
| E402（Import not at top）| **逐案判断** | Tool Payload 脚本有合理的条件 import |
| E501（行长度）| 永久 ignore | 不强制折行，维持阅读性 |

工具命令：
```bash
# 安全自动修复
ruff check nanobot --fix --select I,W291,W293,W292

# 人工核查清单
ruff check nanobot --select F401 --output-format grouped > f401_report.txt
```

---

### 决策 6：沙箱逃逸（明确接受 Trade-off，不投入）

> **「Nanobot 在 Windows 单机环境下的安全哲学：信任边界前移机制（Trust Manager）+ L1 执行黑名单防护」**

基于 Python 反射机制的高阶元编程逃逸（如 `__globals__` 链式调用）在纯 Python 层面无法完美防御。Docker seccomp / gVisor 等 OS 级防护因业务不涉及 Linux 部署而无限期搁置（已存档于 progress_report）。

**这是一个经过明确辩证后的技术折中决定，不反映为系统缺陷，而是成本优先级权衡。**

---

## 执行计划（按 Step 顺序强制执行）

### Step 0：测试基线（前置阻断门）
```bash
pytest --cov=nanobot --cov-report=term-missing
```
将结果存档至 `docs/baseline/` 目录。若覆盖率 < 60%，暂停后续所有步骤，优先补测试。

### Step 1：安全的 Ruff 自动修复
```bash
ruff check nanobot --fix --select I,W291,W293,W292
```
执行后立即运行完整测试套件确认无回归。

### Step 2：F401 Unused Imports 人工核查
```bash
ruff check nanobot --select F401 --output-format grouped > f401_report.txt
```
按模块分组审查，重点排查 `__init__.py` 和含 `register()` 调用的 loader 模块。

### Step 3：新建 `nanobot/utils/exceptions.py`
定义 `NanobotError` / `ProviderExecutionError` / `ToolExecutionError` / `SessionPersistenceError`。

### Step 4：Host 体系 print → logger 迁移
目标：`session/manager.py`, `providers/litellm_provider.py`, `plugin_loader.py`, `utils/metrics.py`。

迁移后检查：Tool Payload 体系的 print **一律保持不动**。

### Step 5：Async 协程 CancelledError 守卫改造
目标：`browser_session.py`, `browser_use_worker.py`, `litellm_provider.py`。

### Step 6：ADR-53 COM 精准防御重构
将 `ExcelActuatorTool` 从 `Dispatch` 改为 `DispatchEx`，引入 `asyncio.wait_for` 120s 超时断路器和精准 PID 回收。

### Step 7：pyproject.toml 强化基线
```toml
[tool.ruff.lint.per-file-ignores]
"nanobot/skills/*/fetch_report.py" = ["I001", "E402"]
"nanobot/scripts/*.py" = ["I001"]
```

---

## 验收标准

| 指标 | 目标 |
|------|------|
| Ruff 安全类别警告 | 从 ~1900 降至 < 50 |
| Host 体系裸 print 数量 | 从 127+ 降至 0 |
| Async 模块未守卫 CancelledError | 降至 0 |
| pytest 通过率 | ≥ Step 0 基线 |
| COM 120s 超时触发 HITL 上报 | Manual Test: PASS |

---

## 影响评估

- **向后兼容**：Tool Payload 体系完全不改，ExecTool 调用链无受影响风险。
- **新功能约束**：所有新建核心模块必须遵循 Host 体系规范（loguru，no bare print）。
- **文档更新**：`SECURITY.md` 加注 Trade-off 决策条目；`progress_report.md` 新增 Phase 55 记录。
