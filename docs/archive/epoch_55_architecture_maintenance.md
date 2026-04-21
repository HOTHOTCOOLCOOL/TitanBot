# Phase 55 ADR-55 — Architecture Lessons Learned

These two lessons were distilled from Phase 55 Architecture Maintenance and should be integrated into `docs/rules/ARCHITECTURE.md` as lessons 23 & 24.

---

## 23. 双域 I/O 铁律，不可混淆 (Dual-Domain I/O Guard)

Nanobot 存在两个平行的 I/O 体系，彼此的通道语义**不可互换，不可混用**：

- **Host Agent 体系**（`nanobot/agent/`, `nanobot/providers/`, `nanobot/session/`, `nanobot/plugins/` 等）：日志输出必须通过 `loguru.logger`；**严禁使用 `print()`**，print 会污染宿主进程的 stdout 并被 ExecTool 误解析为 JSON IPC 消息，导致灾难性的管道数据损坏。
- **Tool Payload 体系**（被 ExecTool / `subprocess` 调用的脚本，如 `sandbox_worker.py`, `skills/*/fetch_report.py`）：`stdout` 是圣洁的 **IPC 数据契约**；**严禁引入 `loguru` 或向 stdout 打印任何调试内容**，所有内部日志应送往 `stderr`。

判断一个文件所属体系的方法：检查它被调用的方式——若是 `import` 调用则属于 Host 体系；若是 `subprocess.Popen` / `run_command(...)` 调用则属于 Tool Payload 体系。

**Ruff 强化**：`pyproject.toml` 中已通过 `[tool.ruff.lint.per-file-ignores]` 为 Tool Payload 脚本注册 T201（print 豁免）。Host 体系没有豁免，CI 可自动捕获误用。（参见 ADR-55 Decision 1）

---

## 24. 异步取消守卫不可省略 (Async CancelledError Must Not Be Swallowed)

在异步函数（`async def`）中，如果使用 `except Exception as e:` 捕获宽泛异常，**必须**在第一行加 CancelledError 重新抛出守卫：

```python
except Exception as e:
    if isinstance(e, asyncio.CancelledError):
        raise
    # ... 其余处理
```

原因：`asyncio.CancelledError`（Python 3.8+）继承自 `BaseException`，但 Python 3.7 中继承自 Exception，因此宽泛的 `except Exception` 在多版本环境中可能静默吞噬它。被吞噬的 CancelledError 会使协程挂起直到 GC，期间持有的所有资源（文件句柄、锁、Browser Session）绝无释放可能，引发资源泄漏和 graceful shutdown 失败。

高危目标：Browser Session 工作器、RPA 执行器、所有长时间 IO 的 async execute() 方法。（参见 ADR-55 Decision 2）
