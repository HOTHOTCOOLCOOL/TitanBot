# ADR-48: Dashboard 配置编辑器 (Config Editor)

**状态**: 已批准 (Approved)
**日期**: 2026-04-12
**辩证方法**: Harness 5段式辩证工作流（Planner → Extreme Critic → V2 Planner → Validating Critic → Final）

---

## 背景

`config.json` 随着系统功能扩展已变为复杂的多子模型 Pydantic 配置树。其中技术性设置（尤其是 `SandboxConfig.capability_overrides` 的位掩码整数）对非技术用户完全不透明，存在误配安全风险。需要在现有 Dashboard (FastAPI + Single-Page HTML) 框架内引入一个用户友好的配置编辑界面。

---

## 决策

### 保留的初代核心设计

| 设计 | 保留理由 |
|------|---------|
| 三端点 REST 架构（`GET/POST /api/config` + `GET /api/capabilities`） | 职责清晰，符合 RESTful 惯例 |
| 复用 `verify_token` + `check_rate_limit` 依赖注入 | 零额外鉴权机制，降低攻击面 |
| 从 `CapabilityTag` 枚举动态反射，而非手动维护描述 | **单一可信源**，防止标签增删后描述同步遗漏 |
| 三层导航信息架构（智能体 / 渠道 / 提供商 / 工具 / 实验性） | 分层降低用户认知负担 |
| 渠道卡片式 Toggle（`enabled` 字段控制整卡 dim 状态） | 直觉操作，"关了就不用填"防呆设计 |

### 采纳的批判与修复

| 批判 | 裁定决策 |
|------|---------|
| `save_config()` 接收 `Config` 对象而非 `dict`，Draft V1 伪代码直接传 dict 会 crash | 后端必须先 `Config.model_validate(merged_dict)` 生成强类型实例再传入 `save_config` |
| 脱敏 Passthrough 在并发场景下会静默覆盖数据（Race Condition） | 采用 `__MASKED__` 常量作为哨兵值；后端 Deep Merge 时跳过所有值为 `__MASKED__` 的键 |
| LocalStorage 草稿会永久驻留明文 API Key / Token | **彻底废弃** LocalStorage 草稿功能；关闭页面即丢弃 |
| 全量 POST 覆盖无乐观锁，导致并发「丢失更新」 | 引入 `version_hash`（基于 `config.json` 的 `mtime`）；`POST` 必须携带上次 GET 拿到的 hash，不匹配返回 **409 Conflict** |
| `capability_overrides` 实际是 `dict[str, int]`（per-tool 覆盖），Draft V1 Widget 展示成全局 Toggle | Widget 升级为 **工具下拉选择 + 2D Tag 开关** 结构 |
| JSON Schema 全自动表单渲染引擎复杂度被严重低估 | 降级为**双模式 UI**：核心字段白盒静态组件 + Raw JSON 编辑器（高级模式）|
| Diff 面板会同时展示新旧 Secret 明文 | **废弃** Diff 面板；改为单次原生确认对话框，敏感字段仅标注 `[已隐藏]` |
| 无容灾回退机制 | 每次 `save_config` 前自动备份旧文件为 `config.json.bak`（极简单体备份）|

### 明确拒绝的建议（附理由）

| 建议 | 拒绝理由 |
|------|---------|
| 完整 Pub/Sub 热更新基础设施（ConfigChangeEvent 订阅/广播） | 与 **zero-extra-infrastructure** 原则相悖；`get_config()` singleton 在每次 Agent 循环时重读，热更需求场景有限 |
| Git 式多版本配置历史 | 单体 `.bak` 已满足容灾需求；版本历史超出本次范围 |
| 管理员角色权限层级（Admin Password + 普通用户分级） | 现有 Bearer Token 鉴权已足够；额外层级只增加用户摩擦 |

---

## 技术实施路径

### A. `nanobot/config/loader.py`（MODIFY）

新增 `save_config_with_backup()` 函数：

```python
def save_config_with_backup(config: Config, config_path: Path | None = None) -> None:
    """原子写入 + 自动 .bak 备份。Dashboard API 专用，替代直接调用 save_config()。"""
    import shutil
    path = config_path or get_config_path()
    bak = path.with_suffix(".json.bak")
    if path.exists():
        shutil.copy2(path, bak)       # 备份旧文件
    save_config(config, config_path)  # 原子写入（复用 F4 tempfile+replace 机制）
    invalidate_config()               # 令 singleton 失效，下次 get_config() 重读磁盘
```

### B. `nanobot/dashboard/app.py`（MODIFY）

新增三个端点及两个辅助函数：

```python
_SENSITIVE_KEYS = {
    "api_key", "token", "secret", "password", "encrypt_key",
    "verification_token", "bridge_token", "claw_token", "app_secret",
    "client_secret", "imap_password", "smtp_password"
}
_MASK = "__MASKED__"

def _mask_sensitive_fields(d: dict) -> None:
    """递归原地将非空敏感字段替换为 __MASKED__。"""
    for k, v in d.items():
        if k in _SENSITIVE_KEYS and isinstance(v, str) and v:
            d[k] = _MASK
        elif isinstance(v, dict):
            _mask_sensitive_fields(v)

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典；跳过 override 中值为 __MASKED__ 的键（保留 base 原值）。"""
    result = dict(base)
    for k, v in override.items():
        if v == _MASK:
            continue
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
```

**`GET /api/config`**：加载配置 → 脱敏 → 附上 `version_hash`（`mtime`）返回。  
**`POST /api/config`**：校验 hash（409）→ Deep Merge → `model_validate` → `save_config_with_backup`。  
**`GET /api/capabilities`**：从 `CapabilityTag` 枚举动态反射 + `RISK_META` 合并，返回每个标签的名称、值、中文标签、风险等级、颜色、描述。

### C. `nanobot/dashboard/templates/index.html`（MODIFY）

- 导航栏新增 `⚙ 设置` 条目
- 新增设置面板 HTML 骨架，含四个选项卡：**智能体** / **提供商** / **渠道** / **沙盒权限**
- 底部固定"保存"按钮 + 「高级模式（Raw JSON）」切换链接

### D. `nanobot/dashboard/static/js/config.js`（NEW，约 600 行）

```
config.js
├── API 层
│   ├── fetchConfig()            → GET /api/config
│   ├── saveConfig(payload)      → POST /api/config（携带 version_hash）
│   └── fetchCapabilities()      → GET /api/capabilities
├── 渲染层（GUI 白盒模式）
│   ├── renderAgentsPanel()      → max_tokens / model / temperature 等
│   ├── renderProvidersPanel()   → API Key 密码框（默认 __MASKED__，可覆盖输入）
│   ├── renderChannelsPanel()    → 渠道卡片 + enabled Toggle
│   └── renderSandboxPanel()     → CapabilityTag 2D Widget
├── CapabilityTag Widget
│   ├── buildToolDropdown()      → 工具名下拉
│   ├── buildTagCheckboxes()     → 枚举 Tag 勾选框（DESTRUCTIVE 类需二次确认）
│   └── computeBitmask()         → 按位 OR 求和 → 写入 capability_overrides[tool]
├── Raw JSON 编辑器（高级模式）
│   ├── showRawEditor()          → 渲染脱敏 JSON 至 <textarea>
│   └── parseRawEditor()         → 解析输入，合并回 payload
└── 保存流程
    ├── collectFormValues()      → 收集 GUI 模式数据
    ├── showConfirmDialog()      → 单次原生确认框（无明文 Diff）
    └── submitConfig()           → POST 含 version_hash；成功后显示重启 Banner
```

### E. `nanobot/config/schema.py`（MODIFY，精简范围）

**不全量补齐**。仅对以下约 30 个核心暴露字段补充 `Field(description="...")`：

- `AgentDefaults`：`model`, `max_tokens`, `temperature`, `max_tool_iterations`, `memory_window`, `session_expiry_hours`, `language`
- `SandboxConfig`：`python_timeout_seconds`, `shell_timeout_seconds`, `tool_timeout_seconds`, `allow_network`, `restrict_workspace`, `capability_overrides`
- `VerificationConfig`：`l0_enabled`, `l1_enabled`, `l3_enabled`, `trace_archive_enabled`
- `BrowserConfig`：`headless`, `block_internal_ips`, `max_pages`
- `ProviderConfig`：`api_key`, `api_base`

---

## 明确超出范围（Not In Scope）

- 完整配置版本历史（Git 式多版本回退）
- 运行时组件热更新（需要 ConfigChangeEvent 发布订阅机制）
- 多管理员角色权限控制

---

## 验证计划

### 自动化测试（新增 `tests/test_dashboard_config.py`）

```python
test_mask_sensitive_fields()          # 验证递归脱敏：api_key → __MASKED__
test_deep_merge_skips_masked()        # 验证 __MASKED__ 被正确跳过，base 值保留
test_optimistic_lock_rejects_stale()  # 验证过期 hash → 409 Conflict
test_save_config_creates_backup()     # 验证 .bak 文件在写入前正确生成
test_post_config_pydantic_validation()# 验证非法值 (max_tokens: -1) → 422 内联错误
```

### 手动验证清单

- [ ] Settings 面板正常渲染，API Key 字段显示 `__MASKED__` 而非明文
- [ ] 不修改 API Key 直接保存，原 Key 不丢失（与 `.bak` 对比验证）
- [ ] 另一标签修改配置后，原标签提交 → 409 冲突提示
- [ ] 勾选 `DESTRUCTIVE` → 弹出二次确认对话框
- [ ] 保存成功后出现「需重启服务」全局 Banner  
- [ ] Raw JSON 模式中 api_key 显示 `__MASKED__`，保存后原值保留
- [ ] 损坏 JSON 提交 → 400 错误内联提示
- [ ] `~/.nanobot/config.json.bak` 在每次保存后刷新
