# Browser-RPA Fusion: Act-Verify Loop + Operation Strategy + Enhanced Loop Detection

## Problem

From this log analysis, the agent enters an infinite loop when operating complex web pages because:

1. **No operation strategy guidance**: LLM picks [browser](file:///d:/Python/nanobot/nanobot/plugins/browser.py#268-286) for everything, never considers `rpa` + `screen_capture`
2. **No state-change verification**: After [click](file:///d:/Python/nanobot/nanobot/plugins/browser.py#483-500)/[fill](file:///d:/Python/nanobot/nanobot/plugins/browser.py#501-518), agent doesn't verify if the action succeeded
3. **Weak loop detection**: Existing L14 detects only **exact-match** signatures (3 identical calls). Real loops involve **similar but non-identical** calls (e.g., same action + different selectors)
4. **No action history**: The VLM has no summary of what it already tried, so it repeats the same approach

## Proposed Changes

---

### Component 1: Operation Strategy Guidance

Add strategy-level rules (not hardcoded workflows) that teach the LLM **when** to use which toolset.

> [!IMPORTANT]
> **前置依赖**：本组件引用的 `screen_capture` 和 `rpa` 工具当前尚未作为独立注册 Tool 存在（RPA 逻辑在 `rpa_executor.py` 内部辅助类中）。在实施本方案前，必须先确认这两个工具是否已注册到 `ToolRegistry`。如果尚未注册，则需要先实现 `screen_capture.py` 和 `rpa.py` 插件文件，否则 LLM 收到降级指令后会尝试调用不存在的工具，引发新的错误循环。

#### [MODIFY] [ARCHITECTURE.md](file:///d:/Python/nanobot/docs/rules/ARCHITECTURE.md)

Add **Section 6: UI Automation Strategy**:

```markdown
## 6. UI 自动化操作戒律 (UI Automation Strategy Rules)

* **工具选择策略 (Tool Selection Strategy)**:
  * **网页自动化 (Web)**: 简单表单或已知 DOM 结构的网页，使用 `browser` 工具（Playwright DOM API）。
  * **桌面应用 (Desktop App)**: ERP、Office、本地程序等桌面 UI，必须使用 `screen_capture(annotate_ui=True)` + `rpa(ui_name=...)` 组合。
  * **复杂网页渐进降级 (Complex SPA Progressive Fallback)**:
    1. 首选 `browser` DOM selector 操作。
    2. 当 selector 失败时，先使用 `browser(action='screenshot')` 让 VLM 分析页面结构，尝试替换 selector。
    3. 当 browser 工具返回的错误信息中包含 `[FALLBACK_RPA]` 标记时（系统按 URL 维度累计 selector 失败 ≥3 次后自动注入此标记），如果系统环境为 Headed 模式（可视窗口），则降级使用 `screen_capture(annotate_ui=True)` + `rpa(ui_name=...)` 进行物理坐标点击；**如果系统环境为 Headless 模式（如无图形界面的服务器端），则绝对禁止调用 RPA 防止截图黑屏，必须继续尝试 DOM 方案或如实向用户反馈环境受限。**
  * **注意**：headed/headless 模式由启动配置决定，如果 `screen_capture` 总是报错或截取到无意义黑屏，说明处于 Headless 模式，应当立刻放弃物理 RPA 降级。
* **操作-验证闭环 (Act-Verify Loop)**:
  * 对 browser 的 `click` 操作（可能改变页面状态/导航），默认自动截图验证（`verify=true`）。如果在已知稳定的 UI 上连续点击，可传 `verify=false` 跳过截图以提升速度。
  * 对 `fill`/`type`/`select` 等确定性表单操作，默认不截图（Playwright 无异常即视为成功）。如需验证可传 `verify=true`。
  * 禁止盲目重复相同的 selector。如果一个 selector 超时失败，必须尝试不同的定位策略。
* **操作历史感知 (Action History Awareness)**:
  * Agent loop 会在系统提示中注入最近的操作历史摘要（当历史中包含 browser/rpa 调用时）。模型必须参考历史，避免重复已失败的操作。
```

---

### Component 2: Enhanced Loop Detection + Action History (loop.py)

#### [MODIFY] [loop.py](file:///d:/Python/nanobot/nanobot/agent/loop.py)

**Change 0**: Expand the signature retention window for fuzzy detection

The existing L14 trims `_recent_call_sigs` to only `_DUPLICATE_THRESHOLD` (3) entries (line 544-545). Fuzzy detection requires a larger window. We must decouple the two windows:

```python
# Existing constant (unchanged)
_DUPLICATE_THRESHOLD = 3  # Break after N identical consecutive calls

# New constants: fuzzy loop detection (separate window)
_SIG_DELIMITER = "\x1e"  # ASCII Record Separator — won't appear in JSON values
_FUZZY_LOOP_WINDOW = 12  # Analyse the most recent N tool call iterations
_FUZZY_DOMINANCE_RATIO = 0.75  # A single tool-action pair exceeding this ratio = loop
```

Change the `_recent_call_sigs` trim logic from:

```python
# OLD (keeps only 3):
if len(_recent_call_sigs) > _DUPLICATE_THRESHOLD:
    del _recent_call_sigs[:-_DUPLICATE_THRESHOLD]
```

To:

```python
# NEW (keeps enough for both exact-match and fuzzy detection):
_SIG_RETENTION = max(_DUPLICATE_THRESHOLD, _FUZZY_LOOP_WINDOW)
if len(_recent_call_sigs) > _SIG_RETENTION:
    del _recent_call_sigs[:-_SIG_RETENTION]
```

**Change 1**: Add a fuzzy loop detection function

The existing L14 (lines 536-557) only catches **exact-match** signatures. Add a new check for **semantic loops** — detecting when the agent repeatedly calls the same tool type (e.g., `browser.click`) with different selectors but identical intent. This catches the pattern from the log where [browser(click, text="单程")](file:///d:/Python/nanobot/nanobot/plugins/browser.py#268-286) → [browser(fill, ...)](file:///d:/Python/nanobot/nanobot/plugins/browser.py#268-286) → [browser(click, text="2026-03-28")](file:///d:/Python/nanobot/nanobot/plugins/browser.py#268-286) repeats cyclically.

```python
def _detect_fuzzy_loop(recent_sigs: list[str]) -> bool:
    """Detect semantic loops via tool-action frequency dominance + cycle detection.
    
    Two complementary methods:
    1. Frequency dominance: if a single (tool, action) pair dominates ≥75% of the
       recent window AND every call uses the same arguments (no progress), it's a loop.
       Legitimate form-filling (same tool.action but different selectors/values each time)
       is excluded by checking argument uniqueness.
    2. Cyclic subsequence: if a (tool.action + normalized_args) sequence forms a
       repeating cycle of length 2-4, repeating ≥3 times. Both tool identity AND
       arguments must match to count as a cycle — this prevents false positives on
       normal form-filling patterns like click(field1)→fill(val1)→click(field2)→fill(val2).
    """
    if len(recent_sigs) < 4:
        return False
    
    from collections import Counter
    window = recent_sigs[-_FUZZY_LOOP_WINDOW:]
    
    # --- Method 1: Frequency dominance with argument stagnation check ---
    pairs = []       # (tool.action) for frequency counting
    pair_args = {}   # tool.action -> set of argument signatures (to detect stagnation)
    
    for sig in window:
        for sub_sig in sig.split(_SIG_DELIMITER):
            tool_part = sub_sig.split(":", 1)[0].strip()
            args_json = sub_sig.split(":", 1)[1] if ":" in sub_sig else "{}"
            try:
                import json as _json
                args = _json.loads(args_json)
                action = args.get("action", "")
            except Exception:
                action = ""
                args_json = "{}"
            
            pair_key = f"{tool_part}.{action}"
            pairs.append(pair_key)
            pair_args.setdefault(pair_key, set()).add(args_json)
    
    if pairs:
        counter = Counter(pairs)
        most_common_name, most_common_count = counter.most_common(1)[0]
        dominance = most_common_count / len(pairs)
        unique_args = len(pair_args.get(most_common_name, set()))
        
        # Only trigger if: high frequency AND low argument variety (= stuck, not progressing)
        # Example: browser.fill called 6 times with 6 different selectors → unique_args=6 → NOT a loop
        # Example: browser.click called 6 times with 2 alternating selectors → unique_args=2 → IS a loop
        if (dominance >= _FUZZY_DOMINANCE_RATIO
                and most_common_count >= 4
                and unique_args <= most_common_count * 0.4):
            return True
    
    # --- Method 2: Cyclic subsequence detection (with argument matching) ---
    # FIXED: Compare (tool.action, normalized_args) tuples, not just tool.action.
    # Without argument comparison, normal form-filling patterns like:
    #   click(field_A) → fill(val_A) → click(field_B) → fill(val_B) → click(field_C) → fill(val_C)
    # would be falsely detected as a cycle of length 2 repeated 3 times.
    call_tuples: list[tuple[str, str]] = []  # (tool.action, args_json)
    for sig in window:
        for sub_sig in sig.split(_SIG_DELIMITER):
            tool_part = sub_sig.split(":", 1)[0].strip()
            args_json = sub_sig.split(":", 1)[1] if ":" in sub_sig else "{}"
            try:
                import json as _json
                action = _json.loads(args_json).get("action", "")
            except Exception:
                action = ""
            pair_name = f"{tool_part}.{action}" if action else tool_part
            call_tuples.append((pair_name, args_json))
    
    for cycle_len in range(2, min(5, len(call_tuples) // 3 + 1)):
        needed = cycle_len * 3
        if len(call_tuples) < needed:
            continue
        tail = call_tuples[-needed:]
        candidate = tail[:cycle_len]
        is_cycle = True
        for rep in range(1, 3):
            if tail[rep * cycle_len:(rep + 1) * cycle_len] != candidate:
                is_cycle = False
                break
        if is_cycle:
            return True
    
    return False
```

**Change 2**: Add action history tracker and summary builder

```python
# New constant: max recent actions to track for history summary
_MAX_ACTION_HISTORY = 10

# Sentinel prefix for action history injection (used for cleanup and budget tracking)
_ACTION_HISTORY_SENTINEL = "\n\n--- 📋 Recent UI Action History ---\n"

def _build_action_history_summary(action_log: list[dict]) -> str:
    """Build a compact natural-language summary of recent tool actions and their outcomes.
    
    Note: 'outcome' field uses three states:
      - "ok": Playwright/RPA reported no exception (DOM-level success)
      - "error": Tool raised an exception or returned Error string  
      - "pending_verify": VLM screenshot was returned, awaiting model judgment
    The VLM will judge actual UI success in the next turn; this log is for
    preventing blind retries, not for definitive success/failure claims.
    """
    if not action_log:
        return ""
    lines = []
    for i, entry in enumerate(action_log[-_MAX_ACTION_HISTORY:], 1):
        outcome = entry.get("outcome", "ok")
        if outcome == "error":
            icon = "❌"
        elif outcome == "pending_verify":
            icon = "👁️"
        else:
            icon = "✓"
        tool = entry["tool"]
        action = entry.get("action", "")
        detail = entry.get("detail", "")[:80]
        lines.append(f"{i}. {icon} {tool}({action}) → {detail}")
    lines.append("\nDo NOT retry failed (❌) actions with identical parameters. Try a different approach.")
    lines.append("For pending (👁️) actions, check the screenshot to verify before proceeding.")
    return "\n".join(lines)
```

**Change 3**: Wire into the agent loop

In [_run_agent_loop()](file:///d:/Python/nanobot/nanobot/agent/loop.py#255-615):
- Maintain an `_action_log: list[dict]` alongside existing `_recent_call_sigs`
- After each tool execution, append to `_action_log`:
  ```python
  # After tool execution in asyncio.gather results processing:
  for tool_call, result in zip(response.tool_calls, results):
      # Existing result processing...
      
      # Action log tracking (for browser/rpa tools)
      if tool_call.name in ("browser", "rpa"):
          # FIXED: Detect "⚠️ ACTION FAILED" string to catch diagnostics screenshots as errors
          _is_err = isinstance(result, BaseException) or (isinstance(result, str) and (result.startswith("Error:") or "⚠️ ACTION FAILED:" in result))
          _is_verify = isinstance(result, str) and result.startswith("__IMAGE__:") and not _is_err
          _action_log.append({
              "tool": tool_call.name,
              "action": tool_call.arguments.get("action", ""),
              "outcome": "error" if _is_err else ("pending_verify" if _is_verify else "ok"),
              "detail": str(result)[:80] if _is_err else tool_call.arguments.get("selector", "")[:80],
          })
          # Cap action log size
          if len(_action_log) > _MAX_ACTION_HISTORY:
              del _action_log[:-_MAX_ACTION_HISTORY]
  ```
- Before each LLM call, inject action history into **system prompt** (not as a fake user message), **sharing `_INJECTION_BUDGET`** with `verification.enrich_context()`:
  ```python
  # FIXED: Action history shares the global _INJECTION_BUDGET (8000 chars) with
  # verification.enrich_context(), not an independent 1500-char sub-budget.
  # enrich_context() returns `injection_used` (chars already consumed).
  # We use 1500 as a max cap for action history, but also check against remaining budget.
  _ACTION_HISTORY_MAX = 1500  # Cap per injection, but must fit within global budget
  
  # Before the LLM call, inject action history into system prompt:
  if _action_log and any(e["tool"] in ("browser", "rpa") for e in _action_log):
      history_summary = _build_action_history_summary(_action_log)
      if history_summary and messages and messages[0].get("role") == "system":
          sys_content = messages[0]["content"]
          # Remove stale history from previous iteration (idempotent)
          sentinel_idx = sys_content.find(_ACTION_HISTORY_SENTINEL)
          if sentinel_idx != -1:
              sys_content = sys_content[:sentinel_idx]
          # Budget check: must fit within BOTH per-injection cap AND global remaining budget
          history_len = len(history_summary) + len(_ACTION_HISTORY_SENTINEL)
          # `injection_used` comes from verification.enrich_context() return value
          remaining_budget = _INJECTION_BUDGET - injection_used
          if history_len <= _ACTION_HISTORY_MAX and history_len <= remaining_budget:
              messages[0]["content"] = sys_content + _ACTION_HISTORY_SENTINEL + history_summary
              injection_used += history_len  # Track for downstream consumers
  ```
  > **Design note**: History is injected into the system prompt (not as a `"role": "user"` message) to avoid confusing the LLM about who sent it. The budget is **shared** with `verification.enrich_context()` (both draw from the same `_INJECTION_BUDGET = 8000`), complying with ARCHITECTURE.md 戒律 1.4 (全部上文注入严格限制在 8000 字符内). The sentinel prefix makes cleanup O(1).
  >
  > **Implementation note**: `injection_used` is the return value of `verification.enrich_context()` called in `_execute_with_llm()`. Since action history injection happens inside `_run_agent_loop()`, you need to pass `injection_used` into the loop (add it as a return value from `enrich_context()` or track it on the loop instance).

- **⚠️ ATOMIC CHANGE**: Change the L14 `_iter_sig` generation (around line 538) to use `_SIG_DELIMITER` constant. **This MUST be deployed simultaneously with `_detect_fuzzy_loop`** — if the delimiter is changed in one place but not the other, fuzzy detection will silently fail (parsing multi-tool signatures as single entries):
  ```python
  _iter_sig = _SIG_DELIMITER.join(
      f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
      for tc in response.tool_calls
  )
  ```

- Add the fuzzy loop detection check **after** the existing exact-match L14 check (line 557):
  ```python
  # After existing L14 duplicate check:
  if _detect_fuzzy_loop(_recent_call_sigs):
      logger.warning("Fuzzy loop detected: tool-action pattern repeating. Breaking loop.")
      final_content = (
          "⚠️ I appear to be stuck repeating similar actions without progress. "
          "Please check if the page loaded correctly, or try a different approach."
      )
      break
  ```

- **⚠️ CRITICAL**: Patch `_is_error_result()` to recognize diagnostic screenshots as errors. Without this fix, the circuit breaker (`consecutive_all_exceptions`) will never increment for failed browser actions that return `__IMAGE__` diagnostic screenshots, allowing infinite error retries:
  ```python
  # PATCH existing _is_error_result() (around line 472):
  def _is_error_result(r):
      if isinstance(r, BaseException):
          return True
      if isinstance(r, str):
          s = str(r).strip()
          if s.startswith("Error:"):
              return True
          # FIXED: Diagnostic screenshots embed error context in ANCHORS text.
          # Without this check, __IMAGE__ returns bypass the circuit breaker entirely.
          if "⚠️ ACTION FAILED:" in s:
              return True
      return False
  ```

---

### Component 3: Act-Verify Post-Action Screenshots (browser.py)

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

Add **opt-in** screenshot after click (defaulting to `verify=true`), with opt-in `verify=true` for fill/type/select. Click can opt-out with `verify=false` for known-stable multi-click sequences.

> **Design rationale**: `click` is the only action where the page state is unpredictable (may navigate, open modal, trigger JS, etc.). `fill`/`type`/`select` are deterministic — if Playwright doesn't throw, the value was set. However, even click verification is opt-out-able (`verify=false`) because consecutive clicks on known-stable UI (e.g., pagination) would otherwise accumulate ~3s latency per click.
>
> **Relationship with RPA verify**: The RPA tool (`rpa_executor.py`) already has its own `VLMFeedbackLoop` that does independent VLM verification with structured judgment and auto-retry. This browser Act-Verify is **deliberately simpler** — it returns the screenshot to the main LLM for judgment rather than making a separate VLM call. This avoids doubled latency in the critical Browser→LLM loop. If progressive fallback to RPA triggers, the RPA tool's own verify mechanism takes over.

**New instance variable for screenshot deduplication** (add to `__init__`):

```python
self._last_screenshot_ts: float = 0.0  # Timestamp of last screenshot (dedup guard)
_SCREENSHOT_MIN_INTERVAL = 2.0  # Minimum seconds between screenshots
```

**Sync navigate auto-screenshot with dedup timestamp** — add at end of `_action_navigate`'s auto-screenshot block (around line 475, after `return f"__IMAGE__:..."`):

```python
# FIXED: Update dedup timestamp so that a click immediately after navigate
# doesn't trigger a redundant post-action screenshot (both within 2s window).
import time as _time
self._last_screenshot_ts = _time.time()
logger.info(f"BrowserTool: auto-screenshot for VLM → {screenshot_filename}")
return f"__IMAGE__:{screenshot_path.resolve()} | ANCHORS:\n{anchor_text}"
```

> Without this sync, `_post_action_screenshot`'s dedup guard sees `_last_screenshot_ts == 0.0` after navigate, so a click immediately following navigate will produce a redundant screenshot.

**New helper method on BrowserTool:**

```python
async def _post_action_screenshot(self, page, action_name: str, selector: str,
                                   error_context: str | None = None) -> str | None:
    """Take a post-action screenshot and return __IMAGE__ payload for VLM verification.
    
    Args:
        page: Playwright page instance.
        action_name: Name of the action just performed (e.g., "click", "fill_FAILED").
        selector: The CSS selector used.
        error_context: If set, this is an error diagnostic screenshot. The error
                       message will be embedded in the ANCHORS text so that
                       downstream error detection (circuit breaker etc.) can still
                       see the failure context.
    
    Returns None if VLM is not configured, screenshot fails, or dedup interval not met.
    """
    try:
        import time as _time
        now = _time.time()
        
        # Dedup guard: skip if a screenshot was taken very recently (e.g., navigate just did one)
        if now - self._last_screenshot_ts < _SCREENSHOT_MIN_INTERVAL:
            return None
        
        # FIXED: Immediately update timestamp to prevent concurrent actions from bypassing dedup
        self._last_screenshot_ts = now
        
        from nanobot.config.loader import get_config
        vlm_cfg = get_config().agents.vlm
        if not (vlm_cfg.enabled and vlm_cfg.model):
            return None
        
        workspace = get_config().workspace_path
        tmp_dir = workspace / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        # Brief delay for UI to settle. Gracefully await any triggered page navigations.
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass
        await asyncio.sleep(0.5)
        
        filename = f"browser_verify_{int(now * 1000)}.png"
        filepath = tmp_dir / filename
        await page.screenshot(path=str(filepath), full_page=False)
        
        # Cleanup: keep only last 10 verify screenshots
        self._cleanup_verify_screenshots(tmp_dir)
        
        title = await page.title()
        url = page.url
        anchor_lines = [
            f"Page: {title}",
            f"URL: {url}",
            f"Action just performed: {action_name}(selector='{selector}')",
        ]
        
        if error_context:
            # Error diagnostic mode: preserve error info for circuit breaker detection
            anchor_lines.append(f"⚠️ ACTION FAILED: {error_context}")
            anchor_lines.append("The screenshot shows the current page state after the failure.")
            anchor_lines.append("Try a COMPLETELY DIFFERENT selector or approach.")
        else:
            anchor_lines.append("VERIFY: Did the action succeed? Did the page change as expected?")
            anchor_lines.append("If the action failed (element not found, page unchanged), try a DIFFERENT selector or approach.")
            anchor_lines.append("Do NOT retry the same selector that just failed.")
        
        anchor_text = "\n".join(anchor_lines)
        logger.info(f"BrowserTool: post-action verify screenshot → {filename}")
        return f"__IMAGE__:{filepath.resolve()} | ANCHORS:\n{anchor_text}"
    except Exception as e:
        logger.debug(f"BrowserTool: post-action screenshot skipped: {e}")
        return None

def _cleanup_verify_screenshots(self, tmp_dir: Path) -> None:
    """Keep only the most recent 10 verify screenshots.
    
    Also cleans up browser_nav_*.png files to prevent unbounded growth.
    """
    try:
        for pattern in ("browser_verify_*.png", "browser_nav_*.png"):
            captures = list(tmp_dir.glob(pattern))
            if len(captures) > 10:
                captures.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                for old_file in captures[10:]:
                    old_file.unlink(missing_ok=True)
    except Exception:
        pass
```

**Modify [_action_click](file:///d:/Python/nanobot/nanobot/plugins/browser.py#483-500)** — verify after click (opt-out with `verify=false`):

```python
async def _action_click(self, kwargs: dict) -> str:
    # ... existing click logic (selector extraction, :contains rewrite, page check) ...
    await page.click(selector, timeout=timeout)
    
    # Act-Verify: screenshot for VLM verification (click may change page state)
    # Default verify=true for click; LLM can pass verify=false for known-stable multi-clicks
    if kwargs.get("verify", True):
        verify_result = await self._post_action_screenshot(page, "click", selector)
        if verify_result:
            return verify_result
    
    return json.dumps({"action": "click", "selector": selector, "success": True})
```

**Modify [_action_fill](file:///d:/Python/nanobot/nanobot/plugins/browser.py#501-518), [_action_type](file:///d:/Python/nanobot/nanobot/plugins/browser.py#519-536), [_action_select](file:///d:/Python/nanobot/nanobot/plugins/browser.py#537-554)** — verify only on opt-in `verify=true`:

```python
async def _action_fill(self, kwargs: dict) -> str:
    # ... existing fill logic ...
    await page.fill(selector, value, timeout=timeout)
    
    # Act-Verify: only screenshot if explicitly requested (fill is deterministic)
    if kwargs.get("verify", False):
        verify_result = await self._post_action_screenshot(page, "fill", selector)
        if verify_result:
            return verify_result
    
    return json.dumps({"action": "fill", "selector": selector, "success": True})
```

Same opt-in `verify` pattern for `_action_type` and `_action_select`.

**Add `verify` to BrowserTool.parameters** (alongside existing params):

```python
"verify": {
    "type": "boolean",
    "description": "If true, take a post-action screenshot for VLM verification. "
                   "Defaults to true for click, false for fill/type/select. "
                   "Set verify=false on click to skip screenshot for known-stable multi-click sequences.",
}
```

**Handle click exception with diagnostic screenshot (preserving error info):**

In the `execute()` method's exception handler (around line 254-264), add a diagnostic screenshot when a mutating action fails with Timeout. The error message is preserved in the ANCHORS text so that the circuit breaker can still detect failures.

> **⚠️ CRITICAL DESIGN DECISION**: The diagnostic screenshot returns `"Error: ..."` prefix **before** the `__IMAGE__:` payload, ensuring `_is_error_result()` still recognizes it as an error for circuit breaker counting. `context.py`'s image parser must be verified to handle `Error:` prefix followed by `__IMAGE__:` protocol — if it only checks `result.startswith("__IMAGE__:")`, the image will be missed. The safest approach is to return the `Error:` string normally, and let the diagnostic screenshot be a **separate, appended line** so both parsers can find their expected prefix.

```python
except Exception as e:
    error_msg = str(e)
    if "Timeout" in error_msg and action in ["click", "fill", "type", "select", "wait"]:
        bad_selector = kwargs.get("selector", "unknown")
        hint = (
            f"Hint: The selector '{bad_selector}' was not found. "
            f"Since you cannot see the exact DOM structure, do not retry this identical selector. "
            f"Instead, try clicking visible label text using 'text=\"...\"', or use a broader/different selector."
        )
        error_msg += f"\n{hint}"
        # Diagnostic screenshot on failure: let VLM see current page state
        # FIXED: Return Error: prefix FIRST (for circuit breaker), then append __IMAGE__
        # on a new line (for context.py image parser). This ensures both subsystems
        # can find their expected prefix without interference.
        try:
            page = await self._get_page()
            if page:
                diag_result = await self._post_action_screenshot(
                    page, f"{action}_FAILED", bad_selector,
                    error_context=f"Error: Browser action '{action}' failed: {error_msg}"
                )
                if diag_result:
                    # Dual-prefix return: Error: for circuit breaker + __IMAGE__ for VLM
                    return f"Error: Browser action '{action}' failed: {error_msg}\n{diag_result}"
        except Exception:
            pass  # Best-effort diagnostic
    logger.error(f"BrowserTool action '{action}' failed: {error_msg}")
    return f"Error: Browser action '{action}' failed: {error_msg}"
```

> **Implementation note**: `context.py`'s `add_tool_result()` must be updated to scan for `__IMAGE__:` anywhere in the result string (not just at the start) so that the dual-prefix format works. Verify this before implementation.

---

### Component 3B: Progressive Fallback Counter (browser.py)

The ARCHITECTURE.md rule "累计 3 次 selector 失败时降级" requires a **code-level counter** rather than relying on LLM memory. Add a per-URL failure tracker to `BrowserTool`:

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

**Add to `__init__`:**

```python
self._selector_fail_counts: dict[str, int] = {}  # url -> cumulative selector failure count
_FALLBACK_THRESHOLD = 3  # After this many failures per URL, suggest RPA fallback
```

**Add fail counter logic to the exception handler** (after selector Timeout):

```python
# In the Timeout exception handler (see above), after building error_msg:
page = await self._get_page()
current_url = page.url if page else "unknown"
url_key = urlparse(current_url).netloc  # Track by domain, not full URL

self._selector_fail_counts[url_key] = self._selector_fail_counts.get(url_key, 0) + 1
fail_count = self._selector_fail_counts[url_key]

if fail_count >= _FALLBACK_THRESHOLD and not self._headless:
    error_msg += (
        f"\n[FALLBACK_RPA] This page has had {fail_count} selector failures. "
        f"DOM selectors may not work reliably on this page. "
        f"Consider using screen_capture(annotate_ui=True) + rpa(ui_name=...) instead."
    )
elif fail_count >= _FALLBACK_THRESHOLD and self._headless:
    error_msg += (
        f"\n⚠️ This page has had {fail_count} selector failures and the browser is in headless mode. "
        f"RPA fallback is NOT available. Try alternative DOM strategies or report to user."
    )
```

**Reset counter on ANY successful DOM mutating action** — extract a shared helper to avoid duplicating 3-5 lines of boilerplate in every action method:

```python
def _on_dom_action_success(self, page) -> None:
    """Reset selector failure counter and update dedup timestamp after a successful DOM action.
    
    Called from _action_click, _action_fill, _action_type, _action_select, _action_navigate
    after the core Playwright call succeeds (no exception).
    """
    if page:
        url_key = urlparse(page.url).netloc
        self._selector_fail_counts.pop(url_key, None)
```

Then in each action method, replace the inline reset with a single call:

```python
# After successful page.click() / page.fill() / page.goto() etc:
self._on_dom_action_success(page)
```

> **Design note**: Counter is per-domain (not per-full-URL) because SPA pages change URLs via client-side routing without actually changing DOM accessibility. The counter resets on any successful DOM action to avoid stale state and prevent false-positive RPA fallback hints over long SPA workflows.

---

### Component 4: Tests

#### [NEW] [test_phase33_browser_rpa_fusion.py](file:///d:/Python/nanobot/tests/test_phase33_browser_rpa_fusion.py)

Tests covering:

1. **Fuzzy loop detection — frequency dominance with stagnation**: Feed `_detect_fuzzy_loop` a window where `browser.click` appears in >75% of calls WITH identical args → returns `True`
2. **Fuzzy loop detection — high frequency but varied args (NO false positive)**: Feed `browser.fill` called 6 times with 6 different selectors → returns `False` (legitimate form filling)
3. **Fuzzy loop detection — cyclic subsequence (same args)**: Feed `[click(sel_A), fill(val_A), click(sel_A), fill(val_A), click(sel_A), fill(val_A)]` pattern with **identical arguments per cycle** → returns `True`
4. **Fuzzy loop detection — cyclic pattern but varied args (NO false positive)**: Feed `[click(sel_A), fill(val_A), click(sel_B), fill(val_B), click(sel_C), fill(val_C)]` — same tool.action cycle but **different args per cycle** → returns `False` (legitimate multi-field form filling)
5. **Fuzzy loop detection — normal varied calls**: Feed mixed tool calls (browser, web_search, shell, message) → returns `False`
6. **Fuzzy loop detection — window size validation**: Feed 12+ sigs, verify only last `_FUZZY_LOOP_WINDOW` are analyzed
7. **Action history summary — three-state outcomes**: Verify `_build_action_history_summary` correctly renders `✓` (ok), `❌` (error), `👁️` (pending_verify) icons
8. **Action history summary — empty log**: Returns empty string
9. **Action history summary — truncation**: Log with >10 entries only shows last 10
10. **Action history injection — goes into system prompt**: Verify history is injected into `messages[0]` (system role) not as a user message
11. **Action history injection — respects global budget**: Inject ~7500 chars of prior context via `enrich_context()`, then verify action history (500 chars) is NOT injected (would exceed `_INJECTION_BUDGET` 8000)
12. **Action history injection — sentinel cleanup**: Verify stale history is removed before injecting new
13. **Browser Act-Verify — click default verify=true screenshots**: Mock `_post_action_screenshot` → verify it's called after `_action_click`
14. **Browser Act-Verify — click with verify=false skips screenshot**: Call `_action_click(verify=false)` → verify `_post_action_screenshot` is NOT called
15. **Browser Act-Verify — fill default no screenshot**: Call `_action_fill` without `verify=true` → verify `_post_action_screenshot` is NOT called
16. **Browser Act-Verify — fill with verify=true screenshots**: Call `_action_fill(verify=true)` → verify screenshot IS taken
17. **Browser Act-Verify — VLM disabled fallback**: When VLM is not configured, `_post_action_screenshot` returns None → click returns JSON
18. **Browser Act-Verify — screenshot write failure graceful**: Mock `page.screenshot` to raise → verify click still returns JSON result
19. **Browser Act-Verify — dedup guard (click-click)**: Two clicks within 2s → only first triggers screenshot
20. **Browser Act-Verify — dedup guard (navigate-click)**: Navigate (auto-screenshot) then immediately click → click should skip screenshot (timestamp synced)
21. **Browser verify screenshot cleanup**: Create 15 `browser_verify_*.png` + 15 `browser_nav_*.png` files → call cleanup → verify only 10 of each remain
22. **Browser exception diagnostic — dual-prefix return**: Mock `page.click` to raise Timeout → verify return starts with `"Error:"` AND contains `__IMAGE__` on a subsequent line
23. **Circuit breaker — diagnostic screenshot counted as error**: Verify `_is_error_result()` returns `True` for a string containing `⚠️ ACTION FAILED:`
24. **Progressive fallback counter — increments on failure**: Trigger 3 Timeout failures on same domain → verify `[FALLBACK_RPA]` appears in error message
25. **Progressive fallback counter — resets via helper**: Call `_on_dom_action_success(page)` → verify counter is reset for that domain
26. **Progressive fallback counter — headless blocks RPA hint**: In headless mode, verify `[FALLBACK_RPA]` does NOT appear even after 3 failures
27. **Sig window retention**: Verify `_recent_call_sigs` retains `max(_DUPLICATE_THRESHOLD, _FUZZY_LOOP_WINDOW)` entries, not just 3
28. **Architecture rules presence**: Verify ARCHITECTURE.md contains the new Section 6

---

## Token Cost Considerations

> [!WARNING]
> **每次 click 默认截图会显著增加 token 消耗。** 一张 1920×1080 截图经 VLM 处理约消耗 1000-2000 tokens。一个典型航班搜索任务涉及 10-20 次 click，仅截图验证就可能消耗 10,000-40,000 tokens，使单次任务 token 开销翻 3-5 倍。
>
> **缓解措施**（可在后续迭代中实施）：
> 1. 在 `config.json` 中增加 `browser.verify_strategy` 配置项：`"always"` / `"on_change"` / `"never"`
> 2. `"on_change"` 模式：仅在 URL 变化或 DOMContentLoaded 事件触发后截图
> 3. 考虑降低截图分辨率（如 960×540）以减少 VLM token 消耗
>
> 当前方案完全依赖 LLM 自行传 `verify=false` 来跳过截图，但 LLM 不太可能自发这么做。建议在 V2 中引入配置级控制。

---

## Pre-Implementation Checklist

在开始编码前，必须确认以下前置条件：

- [ ] **`context.py` 兼容性验证**：确认 `add_tool_result()` 能处理包含 `__IMAGE__:` 协议的工具返回值（特别是 dual-prefix 格式 `"Error: ...\n__IMAGE__:..."`）。检查 image parser 是否只检查 `startswith("__IMAGE__:")` 还是使用 `"__IMAGE__:" in result`
- [ ] **`screen_capture` / `rpa` 工具注册**：确认这两个工具是否已存在于 `ToolRegistry`。如果不存在，先实现插件或从 ARCHITECTURE.md 规则中移除降级指令
- [ ] **`injection_used` 传递路径**：确认 `verification.enrich_context()` 的返回值如何传递到 `_run_agent_loop()` 内部（当前 `enrich_context()` 在 `_execute_with_llm()` 中调用，需要桥接到 loop 内部）

---

## Verification Plan

### Automated Tests

Run existing test suite to check for regressions:

```powershell
cd d:\Python\nanobot
python -m pytest tests/test_phase31_verification.py -v --tb=short 2>&1 | Select-Object -First 80
```

Run new tests:

```powershell
cd d:\Python\nanobot
python -m pytest tests/test_phase33_browser_rpa_fusion.py -v --tb=short 2>&1 | Select-Object -First 80
```

### Manual Verification

> [!IMPORTANT]
> The full end-to-end manual test (actually running the agent against Ctrip) would require a live environment. The automated tests cover the logic units; manual testing is recommended after deployment:
> 1. Send the agent a task like "去携程搜索航班" and verify it doesn't loop
> 2. Check logs for action history injection in system prompt (search for `📋 Recent UI Action History`)
> 3. Check logs for `post-action verify screenshot` entries
> 4. Verify the agent correctly uses progressive fallback (DOM → screenshot → `[FALLBACK_RPA]` → screen_capture+rpa)
> 5. Verify `browser_verify_*.png` AND `browser_nav_*.png` cleanup keeps at most 10 files each in `tmp/`
> 6. Verify that a 10-step form fill completes in reasonable time (no unnecessary VLM calls for fill/type/select)
> 7. Test `verify=false` on click: `browser(action='click', selector='...', verify=false)` should NOT produce a screenshot
> 8. Test screenshot deduplication: navigate (auto-screenshot) then immediately click → click should skip screenshot (within 2s interval)
> 9. Verify circuit breaker triggers after 3 consecutive diagnostic screenshots (not bypassed by `__IMAGE__` return format)
> 10. Verify `_is_error_result()` correctly identifies dual-prefix returns as errors
