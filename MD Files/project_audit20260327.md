# Nanobot 项目审计报告

> **日期**: 2026-03-27  
> **范围**: L2 Verification Layer 退役后的全项目审计  
> **测试基线**: 1271 passed, 0 failed, 1 skipped (119s)

---

## 1. 🔴 漏洞 (Vulnerabilities)

### V-1: [ApprovalStore](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py#11-80) 无校验写入 — 外部可注入审批规则

**文件**: [hitl_store.py](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py#L36-L47)  
**严重度**: 🔴 高

[add_approval()](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py#36-49) 对 `match_context` 无验证。如果攻击者通过 prompt injection 让 LLM 触发 `Always Approve`，可以写入极宽泛的通配符规则（如 `tool=exec, action=*`），永久绕过 HITL 拦截。

```python
# 当前: 无任何校验
def add_approval(self, tool_name, action, match_context=None):
    rule = {"tool": tool_name, "action": action, "context": match_context or {}}
    self._rules.append(rule)  # 直接写入！
```

**建议**: 
- 限制 `match_context` 中的通配符范围（禁止裸 `*`）
- 对 [exec](file:///d:/Python/nanobot/nanobot/agent/tools/filesystem.py#196-217) 工具的 always-approve 规则增加显式二次确认
- 增加规则上限（如最多 50 条）防止存储膨胀

---

### V-2: Shell `deny_patterns` 使用 `lower()` 匹配可导致 Unicode 绕过

**文件**: [shell.py](file:///d:/Python/nanobot/nanobot/agent/tools/shell.py#L134)  
**严重度**: 🟡 中

```python
lower = cmd.lower()  # 仅做 ASCII lower
for pattern in self.deny_patterns:
    if re.search(pattern, lower):
```

攻击者可使用 Unicode 同形字（如全角字符 `ｒｍ` 代替 [rm](file:///d:/Python/nanobot/nanobot/agent/tools/web.py#72-76)）绕过黑名单。虽然实际利用难度较高（需要 LLM 产出此类字符），但在理论上构成漏洞。

**建议**: 增加 `unicodedata.normalize("NFKC", cmd)` 预处理步骤。

---

### V-3: `_SENSITIVE_PATHS` 子串匹配过于粗暴

**文件**: [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py#L73-L83)  
**严重度**: 🟡 中

当前使用简单子串匹配:
```python
path_lower = path_to_check.lower()
for sensitive in _SENSITIVE_PATHS:
    if sensitive in path_lower:
        violations.append(...)
```

这导致误报：路径如 `/home/user/projects/system32-backup/` 会被错误拦截。同时路径如 `C:\Windows\..\Users\..` 可能绕过。

**建议**: 使用 `Path.resolve()` 后再匹配，或改用 `pathlib.PurePath.is_relative_to()` 做路径层级匹配。

---

## 2. 🟡 不足 (Deficiencies)

### D-1: 文档严重过期 — 仍然引用已移除的 L2 层

| 文件 | 具体问题 |
|------|----------|
| [progress_report.md](file:///d:/Python/nanobot/progress_report.md#L69) | Phase 31 表格仍列出 L2 为"✅ 已完成"，Phase 32 仍提到"L2 自检穿透" |
| [ARCHITECTURE.md](file:///d:/Python/nanobot/docs/rules/ARCHITECTURE.md#L13) | 第 13 行仍写着"L0→L1→L2→L3"四层架构 |
| [SECURITY.md](file:///d:/Python/nanobot/SECURITY.md#L214) | 第 214 行仍提到"Weak Model Pre-execution Validation (Phase 30)" |
| [SECURITY.md](file:///d:/Python/nanobot/SECURITY.md#L275) | 最后更新日期仍为 "2026-03-21" |

---

### D-2: `ReadFileTool` 无文件大小限制

**文件**: [filesystem.py](file:///d:/Python/nanobot/nanobot/agent/tools/filesystem.py#L44-L57)

`WriteFileTool` 有 10MB 限制，但 `ReadFileTool` 没有任何限制。LLM 可读取 GB 级文件，导致内存耗尽或上下文爆炸。

**建议**: 增加 `_MAX_READ_BYTES = 5 * 1024 * 1024` 限制和截断标识。

---

### D-3: `ListDirTool` 无结果数量限制

**文件**: [filesystem.py](file:///d:/Python/nanobot/nanobot/agent/tools/filesystem.py#L196-L212)

`sorted(dir_path.iterdir())` 在包含上万文件的目录（如 `node_modules`）时返回巨量数据。

**建议**: 增加 `max_items=500` 限制和 `... and N more` 提示。

---

### D-4: L1 规则 R05（exec 长度限制）与 R09（网络外泄）存在重复

**文件**: [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py#L67-L70) + [shell.py](file:///d:/Python/nanobot/nanobot/agent/tools/shell.py#L35-L38)

`_DESTRUCTIVE_PATTERNS` 中已包含 `invoke-webrequest`、`invoke-restmethod`，`_EXFIL_PATTERNS` 再次包含相同模式。同时 `shell.py` 的 `deny_patterns` 第三次重复了这些检查。三层重复匹配存在维护负担。

**建议**: 统一到一个地方（优先 `shell.py` 的 `_guard_command`），L1 rules 只做补充。

---

### D-5: 缺少 R06 规则（Outlook 附件大小限制）

**文件**: [verification.py](file:///d:/Python/nanobot/nanobot/agent/verification.py#L231-L241)

`L2_VERIFICATION_RETHINK.md` 中提到 L1 扩展方向包含 "R06: `outlook send_email` 附件大小限制"，但实际未实现。规则编号从 R05 直接跳到 R07。

---

## 3. 🐛 Bug

### B-1: `handle_pending_approval` 中 `final_content` 可能为 `None`

**文件**: [state_handler.py](file:///d:/Python/nanobot/nanobot/agent/state_handler.py#L199-L210)

```python
final_content, tools_used, tc_args = await self.agent._run_agent_loop(...)
session.add_message("assistant", final_content)  # final_content 可能为 None!
```

`_run_agent_loop` 在循环耗尽且无 LLM 文本响应时返回 `None`。但 `handle_pending_approval` 未做 null 检查就直接传给 `add_message` 和 `OutboundMessage`。

**影响**: 用户在 HITL 审批后可能收到空消息。

---

### B-2: VLM provider 缓存 LRU 逻辑不标准

**文件**: [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py#L313-L315)

```python
if len(self._vlm_provider_cache) >= 4:
    oldest_key = next(iter(self._vlm_provider_cache))
    del self._vlm_provider_cache[oldest_key]
```

Python `dict` 的 `next(iter())` 返回的是**最先插入**的 key（FIFO），而非**最久未使用**的 key（LRU）。注释说是 LRU，但实际是 FIFO。`max_size=4` 且实际只有 1-2 个 VLM 模型的情况下影响很小，但语义上不准确。

---

### B-3: `_had_tool_errors` 在 `_execute_with_llm` 中检查错误的字段

**文件**: [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py#L996-L999)

```python
_had_tool_errors = any(
    isinstance(tc.get("args"), str) and tc["args"].startswith("Error:")
    for tc in tool_calls_with_args
)
```

`tool_calls_with_args` 中 `args` 是参数字典（dict），不是工具返回结果。这个检查永远为 `False`（因为 dict 不是 str），导致 `_is_analytical` 的逻辑分支**永远**走"分析模式跳过失败检测"的路径，可能在分析工具真正失败时仍然提示用户保存。

---

## 4. 🔒 安全性 (Security)

### S-1: `ApprovalStore._save()` 非原子写入

**文件**: [hitl_store.py](file:///d:/Python/nanobot/nanobot/agent/hitl_store.py#L28-L34)

```python
def _save(self):
    with open(self.filepath, 'w', encoding='utf-8') as f:
        json.dump(self._rules, f, ...)
```

直接覆盖写入。如果进程崩溃或断电，文件可能被截断，导致所有审批规则丢失。其他模块（`session/manager.py`、`reflection.py`、`knowledge_graph.py`）已经使用 `temp + os.replace` 原子写入模式。

**建议**: 采用与 `SessionManager._full_rewrite()` 相同的 `tempfile.mkstemp + safe_replace` 模式。

---

### S-2: Dashboard `/api/status` 无认证

**文件**: [app.py](file:///d:/Python/nanobot/nanobot/dashboard/app.py#L221-L224)

```python
@app.get("/api/status", dependencies=[Depends(check_rate_limit)])
# 注意：故意没有 Depends(verify_token)
```

虽然注释说是 "health check"，但这也暴露了 agent 是否在线的信息。如果部署在公网需注意信息泄露。

**评估**: 低风险，设计决策，建议加入可配置开关。

---

### S-3: `_SSRFSafeTransport` 中的 `socket.getaddrinfo` 是阻塞调用

**文件**: [web.py](file:///d:/Python/nanobot/nanobot/agent/tools/web.py#L43-L58)

`handle_async_request` 是 async 方法，但内部调用同步的 `socket.getaddrinfo`，可能阻塞事件循环（尤其是 DNS 响应慢时）。

**建议**: 改用 `asyncio.get_event_loop().getaddrinfo()` 或 `anyio` 的异步 DNS。

---

### S-4: Shell 环境变量白名单不包含 `USERPROFILE`/`HOME`

**文件**: [sandbox.py](file:///d:/Python/nanobot/nanobot/agent/sandbox.py#L34)

```python
essential_vars = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP"}
```

某些程序（如 `git`、`npm`）依赖 `USERPROFILE`/`HOME` 来定位配置文件。缺失会导致这些工具执行异常，但这也是安全设计（隔离）。

**评估**: 已知权衡。建议在 `SandboxConfig` 中增加 `extra_env_vars` 可选字段供用户配置。

---

## 5. 💡 可改进点 (Improvements)

### I-1: L3 `audit_antipatterns` 在每个 tool-call turn 都重复审计全部历史

**文件**: [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py#L508-L512)

`tool_calls_with_args` 是整个 loop 的累积列表，但 L3 audit 在每轮 tool-call 后都被调用。后续调用会重复审计已审计过的记录。

**建议**: 传入 delta（仅本轮新增的 tool calls），或在 audit 结束后标记已处理的索引。

---

### I-2: 增加 L1 规则 R10 — `write_file` 内容敏感信息检测

**当前状态**: 无对写入内容的敏感信息检测

**建议**: 新增规则检测 `write_file` 内容中是否包含 API key 模式（如 `sk-`, `ghp_`, `AKIA`），避免 LLM 将 API key 写入工作空间文件。

---

### I-3: 统一所有工具的 `get_risk_tier()` 实现

**当前状态**: 仅 `ExecTool` 实现了 `get_risk_tier → DESTRUCTIVE`。大多数工具使用默认的 `MUTATE_LOCAL`。

| 工具 | 当前 Tier | 建议 Tier |
|------|-----------|-----------|
| `read_file` | MUTATE_LOCAL | READ_ONLY |
| `list_dir` | MUTATE_LOCAL | READ_ONLY |
| `web_search` | MUTATE_LOCAL | READ_ONLY |
| `web_fetch` | MUTATE_LOCAL | READ_ONLY |
| `memory_search` | MUTATE_LOCAL | READ_ONLY |
| `outlook.read_email` | MUTATE_LOCAL | READ_ONLY |
| `outlook.send_email` | MUTATE_LOCAL | MUTATE_EXTERNAL |

**影响**: HITL 审批逻辑依赖 `RiskTier` 判断是否拦截。不精确的分级会导致不必要的审批弹窗（READ_ONLY 工具被当作 MUTATE_LOCAL）或漏放（send_email 未被当高危）。

---

### I-4: `_FAIL_INDICATORS` 应改为编译的 regex pattern

**文件**: [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py#L57-L61)

当前使用 `any(ind in content_lower for ind in _FAIL_INDICATORS)` 简单子串匹配。"not found" 在正常分析（如 "The file was not found in the Email"）中会误判为失败。

**建议**: 收紧为 sentence-level 匹配或使用更具区分度的完整短语。

---

### I-5: session JSONL 文件缺乏大小限制和清理机制

**文件**: [session/manager.py](file:///d:/Python/nanobot/nanobot/session/manager.py)

长时间运行的 session 会无限制增长 JSONL 文件大小。虽然 `_trim_history` 限制了上下文注入，但磁盘写入没有限制。

**建议**: 增加 session 文件大小上限（如 50MB），超过后自动触发 consolidation。

---

## 📄 需要更新的文档

| 文档 | 更新内容 |
|------|----------|
| `progress_report.md` | Phase 31/32 描述需移除 L2 相关内容，反映当前 L0→L1→L3 架构 |
| `ARCHITECTURE.md` | 第 13 行四层架构描述改为三层，第 14 行无脑防过载说明需更新 |
| `SECURITY.md` | 移除第 214 行"Weak Model Pre-execution"引用，更新日期至 2026-03-27 |
| `TEST_TRACKER.md` | 更新测试基线为 1271 passed |

---

## 📊 总结

| 类别 | 数量 | 严重项 |
|------|------|--------|
| 漏洞 | 3 | V-1 (HITL 绕过) |
| 不足 | 5 | D-1 (文档过期) |
| Bug | 3 | B-3 (_had_tool_errors 永远 False) |
| 安全 | 4 | S-1 (非原子写入) |
| 改进 | 5 | I-3 (RiskTier 未正确实现) |

**最高优先级修复**: B-3 (错误的字段检查导致false-success detection)、V-1 (ApprovalStore可注入通配符规则)、D-1 (文档过期)
