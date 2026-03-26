---
name: browser-automation
description: >
  Headless browser automation for web apps: navigate pages, fill forms, click elements,
  extract JS-rendered content, manage login sessions. Use when user needs to interact
  with web applications (ERP, SPA, dashboards), scrape JS-rendered pages, or automate
  web login flows. Triggers: "打开网页", "浏览器", "登录网站", "填写表单", "网页自动化",
  "open website", "browse to", "fill form", "login to", "web automation", "scrape page",
  "extract from website". Complements desktop RPA: browser = Web apps, rpa = Win32 apps.
  Requires playwright pip package.
category: infra_ops
version: "1.0.0"
hooks_post: log_execution
metadata: {"nanobot":{"emoji":"🌐","requires":{"pip":["playwright"]}}}
---

# Browser Automation (Playwright)

Headless Chromium browser for full web automation — JS rendering, form interaction, login sessions.

## When to Use

| Task | Tool |
|------|------|
| JS-rendered pages, SPA, dashboards | **browser** ✅ |
| Form filling on web apps | **browser** ✅ |
| Web login + session persistence | **browser** ✅ |
| Simple HTTP GET (static pages, APIs) | **web_fetch** (lighter) |
| Windows desktop apps (Win32/UIA) | **rpa** |
| Desktop screenshots + OCR | **screen_capture** + **rpa** |

## Tool: `browser`

### Actions

| Action | Required Params | Description |
|--------|----------------|-------------|
| `navigate` | `url` | Open URL in browser (SSRF-checked, trust-checked) |
| `click` | `selector` | Click element by CSS selector |
| `fill` | `selector`, `value` | Clear and fill a form field |
| `type` | `selector`, `text` | Type text into element (keystroke simulation) |
| `select` | `selector`, `value` | Select dropdown option by value |
| `screenshot` | — | Capture page screenshot, returns file path |
| `content` | `selector`? | Extract page text (full page or specific element) |
| `evaluate` | `expression` | Execute whitelisted JS (document.title, querySelector, etc.) |
| `wait` | `selector` or `wait_for` | Wait for element or 'networkidle' |
| `login` | `url` | Navigate with login intent (session save in future) |
| `close` | — | Close browser and free resources |

### Example Workflows

**Navigate and extract content:**
```
1. browser(action="navigate", url="https://example.com")
2. browser(action="content")
```

**Fill and submit a form:**
```
1. browser(action="navigate", url="https://app.example.com/form")
2. browser(action="fill", selector="#username", value="user@example.com")
3. browser(action="fill", selector="#password", value="secret123")
4. browser(action="click", selector="button[type=submit]")
5. browser(action="wait", wait_for="networkidle")
6. browser(action="screenshot")
```

**Extract data from JS-rendered table:**
```
1. browser(action="navigate", url="https://dashboard.example.com")
2. browser(action="wait", selector="table.data-table")
3. browser(action="content", selector="table.data-table")
```

### Security Notes

- All navigation URLs are checked against SSRF blocklist (no internal IPs)
- First visit to a new domain requires user trust confirmation
- Sub-requests within trusted pages are SSRF-checked but not trust-checked
- `evaluate` only allows whitelisted JS patterns (no arbitrary code execution)
- Cookie values are never exposed in LLM context

### Dependencies

Requires `playwright` pip package + Chromium browser:
```bash
pip install playwright
playwright install chromium
```
