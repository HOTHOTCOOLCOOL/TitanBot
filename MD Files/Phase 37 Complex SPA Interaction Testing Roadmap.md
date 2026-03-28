# Phase 37: Complex SPA Interaction — Testing Roadmap

## Current Situation

Phase 36 fixed the **entry** problem (agent now uses URL params). But complex web tasks also need **interaction** with dynamic UI:

| Scenario | Why URL Params Won't Work |
|----------|--------------------------|
| 筛选条件（直飞/价格排序） | Filters must be clicked after results load |
| 日期选择器 | Custom datepicker widget, no URL param |
| 城市自动补全 | Type → wait for dropdown → select item |
| 登录弹窗/Cookie 同意 | Must dismiss before any interaction |
| 表单多步流程 | Wizard-style forms with state dependency |

## Bottleneck Analysis

### B1: [content](file:///d:/Python/nanobot/nanobot/plugins/browser.py#693-734) returns raw text, no selectors

When the agent calls [browser(action='content')](file:///d:/Python/nanobot/tests/test_phase33_browser_rpa_fusion.py#231-239), it gets **full page text** (up to 30K chars) but **zero information about interactive elements**. The LLM must guess CSS selectors from text alone — usually wrongly.

**Fix**: Add [browser(action='content', interactive=true)](file:///d:/Python/nanobot/tests/test_phase33_browser_rpa_fusion.py#231-239) mode that extracts **only interactive elements** with their selectors:
```json
{
  "buttons": [{"text": "搜索", "selector": "button.search-btn"}, ...],
  "inputs": [{"placeholder": "出发城市", "selector": "input#departCity"}, ...],
  "links": [{"text": "直飞", "selector": "a.filter-nonstop"}, ...],
  "selects": [{"label": "舱等", "selector": "select.cabin-class"}, ...]
}
```
This gives the LLM **actionable selectors** directly, no guessing needed.

### B2: VLM routing hijacks model choice

When the agent explicitly calls [screenshot](file:///d:/Python/nanobot/nanobot/plugins/browser.py#645-692), the next turn is routed to the **weaker VLM** (`doubao-mini`) for DOM decisions. But the VLM is bad at generating selectors — it was designed for visual recognition, not DOM reasoning.

**Fix**: Two-model cooperation pattern:
1. Main model decides **what** to do (strategy + selector generation from content data)
2. VLM only used for **visual verification** (did the click work?) and **coordinate extraction** (Level 3 mouse_click)

Implementation: Route to VLM only if the screenshot came from a `verify=true` action or an explicit [screenshot](file:///d:/Python/nanobot/nanobot/plugins/browser.py#645-692) call. After the VLM responds, immediately route back to main model.

> [!IMPORTANT]
> This is already partially implemented (`_VLM_RECENCY_WINDOW = 2`), but the VLM still makes DOM decisions when it shouldn't. Consider adding a flag to distinguish "verify screenshot" (VLM judges success/failure only) vs "exploration screenshot" (VLM should suggest actions).

### B3: No auto-retry with context on first selector failure

Currently: selector fails → error text returned → LLM guesses a new selector (often wrong again).

**Fix**: On **first** selector timeout, automatically inject the page's interactive elements into the error response. This gives the LLM real data to pick a correct selector instead of guessing blindly.

### B4: Level 2-3 never end-to-end tested

[mouse_click](file:///d:/Python/nanobot/nanobot/plugins/browser.py#943-989) and [evaluate](file:///d:/Python/nanobot/nanobot/plugins/browser.py#735-767) JS injection exist in code but have never been tested against a real SPA. We don't know if:
- VLM can accurately identify pixel coordinates from screenshots
- Synthetic [click()](file:///d:/Python/nanobot/nanobot/plugins/browser.py#540-566) / `dispatchEvent()` actually works on framework components (React/Vue)
- The coordinate system matches the headless viewport

## Proposed Testing Plan

### Phase A: Add `interactive` content extraction *(code change)*

Add a new `interactive=true` parameter to [_action_content](file:///d:/Python/nanobot/nanobot/plugins/browser.py#693-734) that returns structured interactive elements with their CSS selectors.

#### [MODIFY] [browser.py](file:///d:/Python/nanobot/nanobot/plugins/browser.py)

Add a JS snippet to extract interactive elements:
```javascript
[...document.querySelectorAll('a, button, input, select, textarea, [role="button"], [onclick]')]
  .map((el, i) => ({
    tag: el.tagName,
    text: (el.textContent || el.placeholder || el.ariaLabel || '').trim().slice(0, 50),
    type: el.type || '',
    selector: el.id ? `#${el.id}` : el.className ? `.${el.className.split(' ')[0]}` : `${el.tagName.toLowerCase()}:nth-of-type(${i+1})`,
  }))
  .filter(e => e.text || e.type)
  .slice(0, 50)
```

This bypasses the evaluate whitelist (internal use, like localStorage extraction).

### Phase B: Graduated live testing scenarios

Test 3 scenarios with increasing complexity:

#### Test 1: 携程航班结果页筛选 (Simple — click existing elements)
```
任务: "在携程搜索2026年4月1日上海飞巴黎经济舱，帮我筛选只看直飞航班"
```
- Step 1: URL param navigation (already works ✅)
- Step 2: Agent must click "直飞" filter button on results page
- **Tests**: Can the agent use [content(interactive=true)](file:///d:/Python/nanobot/nanobot/plugins/browser.py#693-734) to find the filter selector? Can it click it?

#### Test 2: 淘宝/京东搜索 (Medium — input + autocomplete)
```
任务: "在京东搜索 iPhone 16 Pro Max 256GB 的价格"
```
- Agent must fill search box → handle autocomplete suggestions → click search
- **Tests**: Form filling, handling overlays, extracting results

#### Test 3: 12306 火车票 (Hard — datepicker + city selector + CAPTCHA)
```
任务: "查一下4月5日北京到上海的高铁票"
```
- Custom datepicker, city autocomplete with pinyin/hanzi, possible CAPTCHA
- **Tests**: Level 2 JS injection for datepicker, Level 3 mouse_click for unselectable elements

### Phase C: VLM routing refinement *(code change)*

> [!WARNING]
> Defer this to after Phase B testing reveals whether VLM coordination is actually the bottleneck. The Phase 36 fix (navigate no longer auto-screenshots) may have already solved most VLM trap issues. If Phase B tests show the agent still gets trapped in VLM on explicit screenshots, then implement this fix.

## Execution Order

1. **Phase A** — Implement `interactive` content extraction (~30 min)
2. **Test 1** — Run Ctrip filter test manually and record logs
3. Fix selector issues revealed by Test 1
4. **Test 2** — Run JD search test
5. Fix issues revealed by Test 2
6. **Phase C** — VLM routing refinement (if needed based on Test 1-2 results)
7. **Test 3** — Run 12306 test (hardest scenario)

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Ctrip filter click | ❌ Infinite loop | ✅ Clicks filter in ≤3 attempts |
| JD search | ❌ Never tested | ✅ Returns product list |
| Selector failures per task | 5-10+ | ≤2 |
| VLM routing traps | Frequent | None (main model in control) |
| Total iterations per task | 10-20 | ≤8 |
