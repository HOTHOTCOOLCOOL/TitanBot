# Browser-RPA 降级链路优化实施方案 (v2)

本方案汇总了以下全部来源的优化项，统一执行：
1. `progress_report.md` §94-117 预研反思 5 条 (Retro §1-§5)
2. 深度代码审查发现的 4 条遗漏问题 (§6-§9)
3. 双方达成共识的 3 项架构决策

---

## User Review Required

> [!IMPORTANT]
> **关于结构化降级信号（Structural Fallback Signal）的实现方式：**
> 我们通过统一的 `[FALLBACK_RPA]` 信号前缀向大模型宣告错误状态，让模型自然规划 `screen_capture → rpa` 的降级操作，而不是在 Worker 内部直接调度其他工具。这保持了工具之间的隔离性。

> [!IMPORTANT]
> **关于 CDP 动态端口分配的实现范围：**
> 实现动态闲置端口查找 + 通过类属性传递端口号给 Worker。暂不引入文件锁或 Env 文件机制（当前单 Agent 架构不需要）。

---

## 完整覆盖矩阵

| 来源 | ID | 条目 | 方案阶段 |
|------|-----|------|---------|
| Retro §1 | R1 | ensure_visible 破坏性重载 → 接受 visible 默认 | Phase 1 |
| Retro §2 | R2 | 坐标系漂移修复（RPA 截图源 + 窗口最大化锁定） | Phase 3 |
| Retro §3 | R3 | Agent 编排负担 → 结构化 fallback 信号 | Phase 2 |
| Retro §4 | R4 | asyncio.wait_for 资源泄漏 + finally 清理 | Phase 2 |
| Retro §5 | R5 | CDP 9222 端口动态分配 | Phase 4 |
| 遗漏 §6 | E6 | browser.py L544-621 死代码清理 | Phase 1 |
| 遗漏 §7 | E7 | `_headless = False` 硬编码移除 → 配置化 | Phase 1 |
| 遗漏 §8 | E8 | browser-use Worker Tab 追踪不同步 | Phase 2 |
| 遗漏 §9 | E9 | RPA headless 拦截条件修正 | Phase 3 |
| 文档整合 | D1 | progress_report.md retro 段落更新 | Phase 5 |

---

## Proposed Changes

---

### Phase 1: Browser Tool 代码清理与配置化 (P0) — 覆盖 R1, E6, E7

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

**1. 删除死代码 (E6)**
- 删除 L544-L621 的无法到达代码块（`_action_navigate` return 后面遗留的 click/fill/type/select 方法体）
- 这些代码在 L543 的 `return json.dumps(nav_data)` 之后，永远不会执行

**2. 移除测试硬编码并配置化 (E7 + R1)**
- 删除 `_load_config()` 中的 `self._headless = False  # HARD FORCED TO FALSE`
- 改为从 `bcfg.headless` 读取配置值，默认 `False`（正式接受"默认可见"作为最佳实践）
- 这使得 `ensure_visible` 成为一个合理的从 headless→visible 的 escape hatch，而不是一个永远走不到的死路径
- 简化 `ensure_visible` 的文档说明：仅在显式配置 `headless=True`（如后台批量爬虫场景）时有意义

---

### Phase 2: Browser-Use Worker 稳定性与结构化降级 (P1) — 覆盖 R3, R4, E8

#### [MODIFY] [browser_use_worker.py](file:///d:/Python/nanobot/nanobot/plugins/browser_use_worker.py)

**1. CDP 连接资源清理 (R4)**
- 在 `execute()` 中将 `Browser(cdp_url=...)` 的使用包裹在 `try...finally` 块中
- `finally` 中执行 `await browser.close()` 确保超时/异常后释放 CDP WebSocket 连接
- 防止僵尸页面和端口占用

**2. 结构化降级信号 (R3)**
- 统一所有错误返回的格式，使用 `[FALLBACK_RPA]` 前缀标记需要降级的错误
- Timeout 返回：`Error: [FALLBACK_RPA] Worker timed out after {timeout}s. Use screen_capture(annotate_ui=True) and then rpa tool.`
- 内部错误返回：`Error: [FALLBACK_RPA] DOM interaction failed: {error}. Use screen_capture(annotate_ui=True) and then rpa tool.`
- 这样 Agent Loop 在看到 `[FALLBACK_RPA]` 时可以自然规划降级，无需多步推理

**3. 通知 BrowserTool 同步页面列表 (E8)**
- Worker 执行结束后（无论成功或失败），调用 `BrowserTool._active_instance` 的一个新方法 `_sync_pages()` 来重新从 Browser Context 获取当前活动页面列表
- 在 `BrowserTool` 中新增 `_sync_pages()` 方法：遍历 `self._context.pages` 并更新 `self._pages`

**4. 读取 CDP 端口而非硬编码** (为 Phase 4 做准备)
- 从 `BrowserTool._active_instance` 读取实际使用的 CDP 端口，而不是硬编码 `9222`
- 如果 `_active_instance` 不存在，回退到 `9222`

---

### Phase 3: RPA 执行器边界防护与坐标对齐 (P2) — 覆盖 R2, E9

#### [MODIFY] [rpa_executor.py](file:///d:/Python/nanobot/nanobot/agent/tools/rpa_executor.py)

**1. Headless 拦截逻辑修正 (E9)**
- 将拦截条件从 `_headless AND _pages` 改为仅检查 `_headless`
- 当 BrowserTool 存在且 `_headless=True` 时，无论 `_pages` 是否为空都发出阻断警告
- 理由：headless 浏览器即使没有活动页面，物理 RPA 操作也可能因为窗口层叠问题导致误操作

**2. Monitor Context 防过期警告 (R2 部分)**
- 在 `_load_monitor_context()` 中读取文件时，检查 `monitor_context.json` 的修改时间
- 如果文件 mtime 距当前时间超过 60 秒，在返回的 context 中标记 `stale=True`
- 在 `_check_bounds()` 中，如果 context 标记了 stale，追加一条 Warning：`⚠️ Monitor context is >60s old. Run screen_capture again if the window has moved.`

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

**3. 窗口最大化锁定 (R2 完整修复)**
- 在 `_ensure_browser()` 中，当 `headless=False` 且平台为 Windows 时，在 `launch_kwargs["args"]` 中添加 `--start-maximized`
- 同时将 `new_context` 的 `viewport` 设为 `None`（让浏览器使用窗口实际大小），消除视口大小与窗口大小不一致导致的坐标漂移
- 这确保 Playwright 截图坐标与物理屏幕坐标最大程度对齐

---

### Phase 4: CDP 端口动态分配 (P2) — 覆盖 R5

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

**1. 动态端口分配**
- 新增 `_find_free_port()` 类方法：使用 `socket.bind((localhost, 0))` 获取 OS 分配的空闲端口
- 在 `_ensure_browser()` 中调用此方法替代硬编码的 `9222`
- 将实际使用的端口号存储在类属性 `_cdp_port` 中，供 `browser_use_worker` 读取

#### [MODIFY] [browser_use_worker.py](file:///d:/Python/nanobot/nanobot/plugins/browser_use_worker.py)

**2. Worker 端读取动态端口**
- 将 `Browser(cdp_url="http://localhost:9222")` 改为从 `BrowserTool._active_instance._cdp_port` 读取
- 兜底逻辑：如果读取失败，回退到 `9222`

---

### Phase 5: 文档更新 (P3) — 覆盖 D1

#### [MODIFY] [progress_report.md](file:///d:/Python/nanobot/progress_report.md)

**1. 更新 Retro 段落**
- 将 §94-117 的"预研与反思"段落标记为 ✅ 已完成
- 每条痛点下追加"解决方案"小节，记录实际采用的方案（而非原始规划）
- 补充遗漏的 §6-§9 条目
- 明确标注哪些原始方案被替换（如 §1 意图预测 → 默认 visible，§3 Worker 自调度 → 结构化信号）

---

## Verification Plan

### Automated Tests
1. `pytest tests/ -x -q` — 确保全部现有测试通过，无回归
2. 手动检查 `browser.py` 中删除死代码后的语法正确性

### Manual Verification
1. 启动 Nanobot，执行 `browser(action='navigate', url='...')` 确认浏览器以可见模式启动
2. 确认 CDP 端口不再硬编码为 9222（日志中应显示动态端口号）
3. 在 2048 场景下故意触发 `browser_use_worker` 超时，验证：
   - Worker 返回 `[FALLBACK_RPA]` 信号
   - Agent 自然调度 `screen_capture → rpa`
   - `browser.close()` 后资源正确释放（无僵尸进程）
4. 验证 `monitor_context.json` 过期警告在 60 秒后正确触发
