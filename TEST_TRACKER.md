# Nanobot 功能测试追踪表 (Test Tracker)

> 每个新功能必须经过 ✅ **自动化测试通过** + ✅ **手动确认** 才算正式完成。
> 最后更新: 2026-03-25

---


## ⚠️ 已知问题

| 问题 | 影响 | 状态 |
|------|-----|------|
| `chromadb` 不兼容 Python 3.14 | `.venv` 无法运行 chromadb 相关测试 | 已绕过 (使用 `.venv311`) |
| `test_memory_daily.py` 有 2 个间歇性失败 | 不影响功能，环境相关 | 已知，暂不修复 |
| YOLO `test_live_yolo_detection` 需要真实 GPU | CI 环境跳过 | expected |
| `test_gemini.py` ImportError `google.genai` | 需 `--ignore=tests/test_gemini.py` 或安装 `google-genai` | 已知 |

---

## 📋 回归测试基线

**上次全量测试结果:** 1209 passed, 0 failed, 1 skipped（排除 gemini/skill 可选依赖）
**测试日期:** 2026-03-26 (Phase 30 回归修复后)
**Python 环境:** `.venv311` (Python 3.11)
**下一里程碑:** Phase 31 (Verification Layer)

> [!TIP]
> 每次新功能开发完成后，运行全量回归测试并更新此基线数字。
> 任何 **新增 failure** 都必须在合入前修复。

