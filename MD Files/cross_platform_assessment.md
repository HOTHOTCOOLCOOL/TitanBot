# Nanobot 跨平台兼容性评估 (Windows → Windows + macOS)

## 结论摘要

| 指标 | 数值 |
|---|---|
| 总 Python 源文件 (nanobot/) | ~50+ |
| 需要修改的文件 | **7–9 个** |
| 需要完全重写的文件 | **1 个** ([outlook.py](file:///d:/Python/nanobot/nanobot/agent/tools/outlook.py)) |
| 需要平台适配的文件 | **5–6 个** |
| 完全不需要改动的文件 | **~85%** |
| **预估代码重构比例** | **~12–15%** |
| 测试需要重新覆盖 | **~15–20%** (新增 macOS 分支测试) |

> [!IMPORTANT]
> 核心结论：**完全有机会支持 Mac + Windows 双平台**。项目架构本身是跨平台的（Python + asyncio），Windows 依赖集中在少数几个 Tool 模块中，并非架构层面的耦合。

---

## 逐模块分析

### 🔴 Tier 1：100% Windows-Only，需要重大改造

#### [outlook.py](file:///d:/Python/nanobot/nanobot/agent/tools/outlook.py) (793 行)
- **依赖**: `win32com.client` (COM Automation), `pythoncom` (COM threading)
- **问题**: 通过 Windows COM API 直接操控 Outlook 桌面应用，**无 macOS 等价物**
- **影响**: 整个文件需要重新架构
- **方案选择**:
  - **方案 A**: macOS 上禁用此 Tool（`platform.system() != "Windows"` 时跳过注册）
  - **方案 B**: 替换为 Microsoft Graph API（REST API），Windows/macOS 通用，但需要 OAuth2 配置
  - **方案 C**: 保持 Windows COM 路径 + 新增 macOS `AppleScript` 路径（双实现）
- **推荐**: 方案 A（短期） + 方案 B（长期），因为 Graph API 统一且不依赖桌面应用

---

#### [ui_anchors.py](file:///d:/Python/nanobot/nanobot/agent/vision/ui_anchors.py) (363 行)
- **依赖**: `uiautomation` 库 (Python wrapper for Windows UIAutomation API)
- **问题**: Layer 1 感知完全依赖 Windows UIAutomation 树
- **影响**: macOS 上 Layer 1 不可用，需要替代方案
- **方案**:
  - macOS 使用 `pyobjc` + Accessibility API（NSAccessibility）
  - 或直接 fallback 到 Layer 2 (OCR) + Layer 3 (YOLO)，跳过 Layer 1
- **推荐**: 短期用 OCR/YOLO fallback，长期封装 `AccessibilityProvider` 接口

---

### 🟡 Tier 2：部分 Windows-Specific，需要平台条件分支

#### [rpa_executor.py](file:///d:/Python/nanobot/nanobot/agent/tools/rpa_executor.py) (460 行)
- **Windows 依赖**:
  - `ctypes.windll.shcore.SetProcessDpiAwareness` (DPI 感知，Line 15–20)
  - `pydirectinput` (Windows-only DirectInput 驱动)
- **macOS 兼容部分**: `pyautogui` 本身跨平台
- **改造量**: ~20 行 DPI 代码需要 `if platform.system() == "Windows"` 保护（**已部分存在**）
- **改造难度**: ⭐ 低

---

#### [sandbox.py](file:///d:/Python/nanobot/nanobot/agent/sandbox.py) (144 行)
- **Windows 依赖**: 硬编码环境变量白名单
  ```python
  essential_vars = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP"}  # Line 34
  essential_vars = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE"}  # Line 101
  ```
- **改造**: 根据 `platform.system()` 选择对应的 essential vars
  - macOS: `{"PATH", "HOME", "TMPDIR", "SHELL"}`
- **改造量**: ~10 行
- **改造难度**: ⭐ 低

---

#### [shell.py](file:///d:/Python/nanobot/nanobot/agent/tools/shell.py) (162 行)
- **Windows 依赖**:
  - Deny patterns 包含 Windows-specific 命令：`del /f`, `rmdir /s`, `powershell`, `pwsh`
  - Path detection: `re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)` (Windows 路径格式)
  - `..\\` 检测 (Windows 反斜杠)
- **改造**: 需要按平台添加 macOS deny patterns（`sudo rm -rf /`, `ditto`, etc.）
- **改造量**: ~15 行
- **改造难度**: ⭐ 低

---

#### [tool_setup.py](file:///d:/Python/nanobot/nanobot/agent/tool_setup.py) (171 行)
- **问题**: 无条件注册 [OutlookTool](file:///d:/Python/nanobot/nanobot/agent/tools/outlook.py#40-793) (Line 79)
- **改造**: 添加平台检测，macOS 上跳过 Outlook 注册
- **改造量**: ~5 行
- **改造难度**: ⭐ 低

---

### 🟢 Tier 3：已跨平台 / 需极少改动

| 模块 | 状态 | 备注 |
|---|---|---|
| [screen_capture.py](file:///d:/Python/nanobot/nanobot/agent/tools/screen_capture.py) | ✅ 跨平台 | 使用 `mss` 库，天然支持 Windows/macOS/Linux |
| [ocr_engine.py](file:///d:/Python/nanobot/nanobot/agent/vision/ocr_engine.py) | ✅ 跨平台 | PaddleOCR，纯 Python |
| [yolo_detector.py](file:///d:/Python/nanobot/nanobot/agent/vision/yolo_detector.py) | ✅ 跨平台 | ultralytics，纯 Python |
| [vlm_feedback.py](file:///d:/Python/nanobot/nanobot/agent/vision/vlm_feedback.py) | ✅ 跨平台 | 纯 LLM API 调用 |
| [context.py](file:///d:/Python/nanobot/nanobot/agent/context.py) | ✅ 已有平台检测 | Line 94: `platform.system()` |
| `loop.py` (Agent 核心) | ✅ 跨平台 | 纯 asyncio + LLM API |
| `memory/` (7 层记忆) | ✅ 跨平台 | JSON/SQLite/ChromaDB |
| `knowledge_graph.py` | ✅ 跨平台 | 纯 Python 数据结构 |
| `providers/` (LLM) | ✅ 跨平台 | LiteLLM，HTTP 调用 |
| `channels/` (通信) | ✅ 跨平台 | Telegram, Feishu, Slack, DingTalk, WeChat |
| `dashboard/` | ✅ 跨平台 | FastAPI + WebSocket |
| `bus/` (消息总线) | ✅ 跨平台 | 内存队列 |
| `cron/` | ✅ 跨平台 | croniter 库 |
| `skills/` (大部分) | ✅ 跨平台 | 纯 Python |
| `config/` | ✅ 跨平台 | Pydantic + JSON |

### 🔵 Tier 4：特殊模块 (Optional Features)

| 模块 | 状态 | 备注 |
|---|---|---|
| `skills/ssrs-report/` | ❌ Windows-Only | SSPI/NTLM 认证依赖 Windows 域环境，但这是 **optional skill**，不影响核心 |
| `chrome-win64/` 目录 | ❌ Windows-Only | 捆绑的 Chrome 二进制文件，macOS 需换为 `chrome-mac-arm64` 或系统 Chrome |
| [pyproject.toml](file:///d:/Python/nanobot/pyproject.toml) SSRS dep | ⚠️ 需条件化 | `requests-negotiate-sspi` 仅 Windows 可安装 |

---

## 改造工作量评估

### 代码变更量

| 分类 | 文件数 | 改动行数(估) | 难度 |
|---|---|---|---|
| Outlook Tool 重构 | 1 | 50–800 行 | 取决于方案选择 |
| RPA DPI 适配 | 1 | ~20 行 | ⭐ |
| Sandbox 环境变量 | 1 | ~15 行 | ⭐ |
| Shell 安全规则 | 1 | ~15 行 | ⭐ |
| UI Anchors 适配 | 1 | ~30 行 | ⭐⭐ |
| Tool Setup 条件注册 | 1 | ~10 行 | ⭐ |
| pyproject.toml deps | 1 | ~5 行 | ⭐ |
| **合计 (方案A: 禁用 Outlook)** | **7** | **~100 行** | **低** |
| **合计 (方案B: Graph API)** | **8** | **~500 行** | **中** |

### 测试影响

- **现有 1209+ 测试**: 大部分不需要改动（纯逻辑测试，mock 了 I/O）
- **需新增测试**: macOS 平台条件分支测试约 **30–50 个** test cases
- **需修改测试**: 涉及 Outlook/RPA mock 的测试需要添加 `platform.system()` 条件 skip
- **估计测试重构比例**: **~15–20%**

---

## 推荐路线图

### Phase 1: 最小化跨平台支持 (1–2 天工作量)
1. [sandbox.py](file:///d:/Python/nanobot/nanobot/agent/sandbox.py) — 按平台选择 essential env vars
2. [shell.py](file:///d:/Python/nanobot/nanobot/agent/tools/shell.py) — 添加 macOS deny patterns
3. [tool_setup.py](file:///d:/Python/nanobot/nanobot/agent/tool_setup.py) — 条件注册 Outlook/RPA
4. [rpa_executor.py](file:///d:/Python/nanobot/nanobot/agent/tools/rpa_executor.py) — DPI 代码保护已存在，确认 `pydirectinput` graceful fallback
5. [ui_anchors.py](file:///d:/Python/nanobot/nanobot/agent/vision/ui_anchors.py) — macOS 时 fallback 到 OCR+YOLO（跳过 UIAutomation）
6. [pyproject.toml](file:///d:/Python/nanobot/pyproject.toml) — SSRS dep 设为 Windows-only

### Phase 2: 完善 RPA 体验 (3–5 天)
1. macOS Accessibility API 集成（`pyobjc`）
2. `chrome-mac-arm64` 自动检测与下载

### Phase 3: 邮件功能统一 (5–7 天)
1. Microsoft Graph API 替代 Outlook COM
2. 统一邮件 Tool 接口

> [!TIP]
> Phase 1 完成后，Nanobot 的**核心能力**（对话、记忆、知识图谱、技能执行、Web 搜索、文件操作、仪表盘）在 macOS 上就能完整运行。RPA/Outlook 是增值功能，可以渐进式支持。
