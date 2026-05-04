# Codex Feedback

Status: rework
Job ID: phase_67_knowledge_map_tool

Failed Commands:
- `pytest tests/unit/test_knowledge_map_bug.py` (人工构造的极限边界测试)

Key Errors:
- `AssertionError: Failed! Length was 3018`

Severity A:
- **截断逻辑存在缺陷（越界违约）**：`_MAP_OUTPUT_CAP` 被设定为 3000。当前代码使用了 `result = result[:_MAP_OUTPUT_CAP] + "\n...[map truncated]"`，这导致最终字符串长度变成了 `3000 + len("\n...[map truncated]")` = 3018。这直接违反了 ADR-67 中“严控 <= 3000 chars”的架构契约。
- **单元测试存在漏洞（伪阳性绿灯）**：`test_output_cap_enforced` 单元测试试图通过塞入 200 个 node 来触发长度超限。但因为工具逻辑里有 `[:_TOP_N_HUBS]`（只取 15 个 hub），实际输出的字符串长度最多只有 1000~1500 字符，**根本没有触发**截断分支。这导致截断 bug 被掩盖，测试出现假绿。

Severity B:
- 无

Must Fix Files:
- `nanobot/agent/tools/knowledge_map.py`：修复截断逻辑，确保追加提示语后，**总长度**严格 `<= _MAP_OUTPUT_CAP`。
- `tests/unit/test_knowledge_map.py`：重写 `test_output_cap_enforced`，必须能够真正触发截断分支（例如使用包含极长字符串的实体名），并验证截断后的最终长度。

Boundary Reminder:
- 继续遵守原 handoff 的 Allowed Write Set / Forbidden Write Set

Return Instructions:
- 修复完成后写回 `codex_result.md` (如果不存在请创建)
