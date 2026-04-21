# ADR-64: 架构安全加固 — Phase 37-63 深度回顾综合决策

**状态**: 已定稿 (Accepted)  
**日期**: 2026-04-21  
**决策者**: Harness 5阶混合模型辩证工作流  
*(Claude Sonnet Planner → Claude Opus Critic → Gemini High V2 Planner → Gemini Low Validator → Claude Sonnet Final)*

---

## 背景与问题定性

对 Phase 37 (Manager-SubAgent 编排) 至 Phase 63 (回归测试加固) 的整体回顾，暴露出 Nanobot 在快速功能迭代过程中积累的**三类系统性风险**：

1. **边界渗透风险**：Shell Guard、PSV AST 校验、BFF 系统事件注入各自存在绕过漏洞
2. **状态漂移风险**：M-RAG 向量库无 GC 机制、上下文降级无感知通知
3. **工程债务风险**：Context 膨胀对模型过拟合、HITL 静态门控导致交互疲劳、Excel COM 遗留锁文件

经过 Harness 4 轮辩论，最终收敛为 **7 项架构决策**。

---

## 核心主张

> 从"防御堆砌"走向"边界契约"。不再试图用更多的黑名单和捕获器堵无穷攻击面，而是在执行区划、数据通道、状态一致性三个维度上建立有限但严格的边界契约。

---

## 架构决策

### 决策 1：Zone 执行区划隔离（取代文件后缀黑名单）

**问题**：原方案基于 `write_file` 后缀正则黑名单，被辩证识别为"无穷攻击面的反模式"（与 Phase 56 PSV 从黑名单切换白名单的同一教训）。任何黑名单都无法枚举 Windows 可执行文件的全集（`.pyw`, `.cmd`, `.vbs`, `.wsf`, `.jsx` 等），且 `exec` 工具的 stdin 完全旁路了路径检查。

**放弃**：基于文件后缀名的 `FileOpFence` 黑名单。

**采纳**：**Zone-based Execution Containment（区划执行隔离）**

| Zone | 路径 | 权限 |
|:---:|---|---|
| A | `nanobot/` 源码树 | 只读，严禁任何工具写入 |
| B | `workspace/memory/`, `.nanobot/ki_rules/` | 数据读写，禁止代码执行 |
| C | `workspace/sandbox/` | 唯一允许执行动态代码的区域 |

**实施**：修改 `run_command` / `exec` 工具的基础 Executor，强制将 `cwd` 锚定在 `workspace/sandbox/`。跨 Zone 的执行请求触发 HITL（Blast Radius 4）。

**Rationale**："写入"和"执行"路径的分离，是这个问题在设计层面唯一正确的解。

---

### 决策 2：IPC Payload 5MB 硬盖板 + 大文件代偿引流（含 1000 字前瞻预览）

**问题**：SubAgent 返回巨大 Payload 可能导致 Host OOM。字符数量截断过于粗暴，误杀合法 PDF/Excel 分析结果；嵌套深度检测对扁平大字符串完全无效。

**放弃**：字符数截断 + 嵌套深度计数。

**采纳**：

```python
MAX_PAYLOAD_IPC_BYTES = 5 * 1024 * 1024  # 5MB

if len(payload_bytes) > MAX_PAYLOAD_IPC_BYTES:
    preview = payload_str[:1000]  # 保留前1000字供模型感知
    tmp_path = workspace / "sandbox" / f"large_{content_hash[:8]}.txt"
    tmp_path.write_text(payload_str, encoding="utf-8")
    return (
        f"[Preview: {preview}...]\n"
        f"[Payload too large ({size_mb:.1f}MB). Full result saved to: {tmp_path}]"
    )
```

**Rationale**：前瞻预览保留基础上下文感知；完整数据通过文件引用可被后续工具读取，实现闭环而非信息丢弃。

---

### 决策 3：LLM 输出侧转义 `[System:]` + 孤儿工具消息升格修正

**问题**：两个独立漏洞：(a) LLM 可以在输出中伪造 `[System: ...]` 格式触发系统逻辑；(b) `context.py` 将孤儿 `role: tool` 降格为 `role: user [System Observation: ...]`，模糊了用户输入与系统事件的语义边界。

**放弃**：完全废弃 `[System: ...]` 协议（迁移成本超过安全收益）；`_trusted` 内联字段（序列化边界后失效，等于零防御）。

**采纳**：

**修复 A — 输出侧转义**（`loop.py`，接收 LLM response 后立即执行）：
```python
import re
# 转义 LLM 输出中的伪造系统标签，不破坏可读性
content = re.sub(r'\[System:', r'[\\System:', content or "")
```

**修复 B — 孤儿消息升格**（`context.py` 第 348 行附近）：
```python
# 原来：role: user (错误降格)
# 修改为：role: system (正确升格)
sanitized.append({
    "role": "system",
    "content": f"[Orphan tool telemetry: '{name}'] {content}"
})
```

**Rationale**：最小侵入式修复。`_trusted` 标志经过 JSON 序列化/反序列化后会被丢弃或可被伪造。信任必须体现在调用路径位置而非数据字段内容。

---

### 决策 4：M-RAG 惰性一致性校验（Lazy Consistency）

**问题**：向量库无 GC 机制，僵尸知识长期污染 RAG 检索。后台 GC 方案有并发竞态风险；Windows NTFS mtime tunneling 导致 mtime 判断不可信。

**放弃**：基于 mtime 的后台 GC Worker。

**采纳**：**检索时惰性验证**（`vector_store.py`，在 `search()` 返回结果前执行）：

```python
def _is_source_alive(self, result: dict) -> bool:
    """O(1) 磁盘探针，验证索引来源文件是否仍然存在。"""
    file_path = result.get("metadata", {}).get("file_path")
    if file_path and not Path(file_path).exists():
        self._flagged_for_gc.add(result.get("id"))
        return False
    return True

# search() 返回前过滤
output = [r for r in raw_results if self._is_source_alive(r)]
```

`_flagged_for_gc: set[str]` 内存集合由 nightly Cron (`clear_old_tasks` 同轮次) 批量 purge，解耦检索路径与磁盘写入路径。

**Rationale**：Gemini Low 确认这是 ADR-64 中最精妙的工程折中——O(1) 磁盘探针，无锁争用，完全规避 Windows mtime tunneling 和并发竞态，必须严格保留。

---

### 决策 5：Context 降级显性感知通知（安全区后置注入）

**问题**：Phase 57 的 Visual Silent Downgrade 和历史骨架化对 LLM 完全透明，导致模型在信息残缺下自信猜测。原通知追加在 `build_system_prompt()` 内部，自身可能被 IFCC 压缩（关于降级的通知本身被降级的递归问题）。

**放弃**：在 `build_system_prompt()` 内部追加降级通知。

**采纳**：**在 `build_messages()` 最后一步、Schema Sanitizer 之前注入独立 `role: system` 消息**（完全脱离 IFCC 管辖范围）：

```python
# context.py: build_messages() 末尾，schema sanitize 之前

degradation_notices = []
if dropped_images > 0:
    degradation_notices.append(
        f"⚠️ {dropped_images} image(s) removed due to token budget. "
        "Do NOT assume visual context. If the task requires images, ask user to re-provide."
    )
if skeletonized_count > 0:
    degradation_notices.append(
        f"⚠️ {skeletonized_count} history message(s) compressed to summaries. "
        "Older context details may be incomplete."
    )

if degradation_notices:
    messages.append({
        "role": "system",
        "content": "[Context Integrity Notice]\n" + "\n".join(degradation_notices)
    })

# 之后才进行 schema sanitize
sanitized = [...]
```

**Rationale**：独立 system 消息绕过 IFCC，且 Schema Sanitizer 不改写它。这是本 ADR 中实现成本最低、安全提升最高的修复之一（P0 优先级）。

---

### 决策 6：Excel COM 启动前 Pre-flight 脏锁清理

**问题**：`taskkill /PID` 强杀后立即扫描 `~$*.xlsx` 锁文件，存在 Windows 文件系统句柄异步释放窗口（数百毫秒），导致 `Access Denied`，随后需要 retry loop，引入额外复杂性。

**放弃**：强杀后同步扫描清理。

**采纳**：**下一次 ExcelActuator 初始化时的 Pre-flight 清理**：

```python
# excel_actuator.py 或 RPA 执行器的 __init__ / connect() 第一步

@staticmethod
def _preflight_clean_locks(target_dir: Path) -> int:
    """在进程启动前清理前任遗留的 Excel 锁文件。"""
    cleaned = 0
    for lock_file in target_dir.glob("~$*.xl*"):
        try:
            lock_file.unlink(missing_ok=True)
            cleaned += 1
            logger.info(f"[Pre-flight] Removed stale Excel lock: {lock_file.name}")
        except OSError:
            pass  # 仍被占用则跳过，下次再清理
    return cleaned
```

**Rationale**：在下一次实例化前清理，完美错开了强杀后的句柄异步释放窗口。这是 Windows GUI 自动化中处理残留锁文件的标准 Pre-flight 模式。

---

### 决策 7：Blast Radius 静态评分 + 严格 HITL 阻塞 + Cron 无头熔断

**问题**：Antigravity 全局规划门导致低风险任务被无差别拦截，交互疲劳严重。且"3秒自动同意"方案被辩证识别为极度危险——消灭了 HITL 中"Human"的存在。

**放弃**：所有形式的自动超时同意；完全删除 HITL（另一个极端）。

**采纳**：**Blast Radius 静态映射表 + 永不超时阻塞 + Cron 无头熔断**：

| Blast Radius | 操作类型示例 | HITL 策略 |
|:---:|---|---|
| 0 | 只读查询、报表分析 | 自动通过，无需确认 |
| 1 | workspace 内文件读写 | 仅写入审计日志 |
| 2 | 消息/邮件发送 | **强阻塞 HITL，永不超时** |
| 3 | 数据库写入 / Excel 修改 | **强阻塞 HITL，永不超时** |
| 4 | 代码执行 / 系统命令 | **强阻塞 HITL + 规划门** |

**Cron 无头模式补丁**（`hitl_store.py` / Cron Worker）：
```python
if hitl_required and is_headless_cron_env():
    # 无界面环境无法等待人类，直接失败并上报
    tracker.fail_task(task_id, error="HITL required but running in headless Cron mode.")
    notify_operator(f"Task {task_id} blocked: requires human approval.")
    return
```

**Rationale**：HITL 的本质是"人类真实参与决策"，任何 Blast Radius ≥ 2 的自动通过都违背了这一基本原则。Cron 无头熔断防止了任务在无人响应环境中永久挂起。

---

## 实施优先级

| 优先级 | 决策编号 | 影响文件 | 行变更量估计 |
|:---:|:---:|---|:---:|
| P0 🔴 | 决策 3 | `context.py`, `loop.py` | ~10 行 |
| P0 🔴 | 决策 5 | `context.py` | ~15 行 |
| P1 🟠 | 决策 6 | `excel_actuator.py` 或 RPA 执行器 | ~20 行 |
| P1 🟠 | 决策 4 | `vector_store.py` | ~25 行 |
| P2 🟡 | 决策 2 | `subagent.py` | ~20 行 |
| P2 🟡 | 决策 7 | `hitl_store.py`, Cron Worker | ~30 行 |
| P3 🟢 | 决策 1 | `sandbox.py`, `run_command` executor | ~40 行 |

---

## 刻意放弃 (Decided Not To Do)

- ❌ 基于文件后缀名的 `FileOpFence` 黑名单（无穷攻击面反模式）
- ❌ 基于 `_trusted` 内联字段的签名信任机制（序列化边界后失效）
- ❌ 完全废弃 `[System: ...]` 事件协议（迁移成本超过安全收益）
- ❌ 基于 mtime 的后台 GC Worker（Windows NTFS mtime tunneling + 并发竞态风险）
- ❌ 3 秒自动同意（消灭了 Human-in-the-Loop 的 "Human"）
- ❌ 10,000 字符硬截断 Payload（误杀合法大型返回，根因在总大小非字符长度）

---

## 新增经验法则 (ARCHITECTURE.md Rules #26-28)

> 见 `docs/rules/ARCHITECTURE.md` 末尾追加的经验法则 #26、#27、#28。

---

## 验证计划

| 测试类型 | 目标 | 验收标准 |
|---|---|---|
| 单元测试 | 决策 3 输出转义 | `[System:` 字符串无法通过 Loop 接收层未转义 |
| 集成测试 | 决策 4 惰性一致性 | 删除源文件后 `search()` 不再返回该孤立 chunk |
| 对抗测试 | 决策 1 区划隔离 | Zone A 路径的 `exec` 调用被拦截，返回 `Error:` |
| 功能测试 | 决策 6 Pre-flight | ExcelActuator 重新 connect() 后目录内 `~$*.xlsx` 消失 |
| 回归测试 | 全量 | Phase 63 绿色基线 pytest 不得新增红灯 |
