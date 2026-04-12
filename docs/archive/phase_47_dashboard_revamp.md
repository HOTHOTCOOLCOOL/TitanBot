# Dashboard 配置编辑器改造方案 (最终定稿)

> **状态**: ✅ ADR-48 已批准，待进入编码阶段
> **ADR**: `docs/adr/ADR-48-dashboard-config-editor.md`
> **辩证过程**: Harness 5段式工作流（2026-04-12 完成）

---

## 背景 & 问题

随着系统能力扩展，`config.json` 已变为复杂的多子模型 Pydantic 配置树。技术性设置——尤
其是 `SandboxConfig.capability_overrides` 的位掩码整数（如 `DESTRUCTIVE: 128`）——对非技
术用户完全不透明。缺乏语境化风险说明的开放系统，对非技术用户而言是不安全的。

---

## 核心架构决策（经 Harness 辩证确认）

### 1. 安全写入管道（后端）

```
GET /api/config   → 返回脱敏配置（敏感字段 → __MASKED__）+ mtime version_hash
POST /api/config  → 乐观锁校验(409) → Deep Merge(跳过__MASKED__) → Pydantic校验 → .bak备份 → 原子写入
GET /api/capabilities → 从 CapabilityTag 枚举动态反射 + 风险元数据
```

### 2. 双模式 UI（前端）

| 模式 | 适用用户 | 实现方式 |
|------|---------|---------|
| **GUI 白盒模式** | 普通/非技术用户 | 四个选项卡（智能体/提供商/渠道/沙盒），手写静态组件 |
| **Raw JSON 编辑器** | 高级用户 | `<textarea>` 直接编辑脱敏 JSON，复用同一 Deep Merge 管道提交 |

### 3. CapabilityTag Widget（已纠正）

实际数据结构为 `dict[str, int]`（per-tool 覆盖），而非全局 Toggle。正确 UI：

```
┌ 沙盒权限覆写 ──────────────────────────────────────────┐
│ 工具: [exec ▼]                                        │
│                                                        │
│  ☑ DATA_READ         读取权限     风险: 🟢 低          │
│  ☐ SHELL_EXECUTION   Shell执行    风险: 🟡 中          │
│  ☐ DESTRUCTIVE       破坏性操作   风险: 🔴 高危! ⚠     │
│  ☐ UNTRUSTED_EXTERNAL 未知外部    风险: 🔴 高危! ⚠     │
│                                                        │
│  当前值: 1 (DATA_READ)                                 │
│  [重置为最低权限]                                       │
└────────────────────────────────────────────────────────┘
```

`DESTRUCTIVE`/`UNTRUSTED_EXTERNAL` 启用时弹出二次确认对话框。

---

## 关键安全决策

| 决策 | 说明 |
|------|------|
| `__MASKED__` 哨兵常量 | 敏感字段脱敏统一用此常量；后端 Deep Merge 时跳过该值，保留磁盘原值 |
| `version_hash` 乐观锁 | 基于 `mtime`，防止并发并发写入导致「丢失更新」|
| `config.json.bak` 自动备份 | 每次写入前备份，零额外基础设施的容灾机制 |
| **废弃** LocalStorage 草稿 | 防止明文 Token/Key 永久驻留浏览器本地 |
| **废弃** Diff 面板 | 防止新旧 Secret 同时上屏，改为单次确认对话框 |
| 热重载统一为"需重启"提示 | 不引入 ConfigChangeEvent 机制，避免过度工程化 |

---

## 受影响文件

| 文件 | 操作 |
|------|------|
| `nanobot/config/loader.py` | MODIFY — 新增 `save_config_with_backup()` |
| `nanobot/dashboard/app.py` | MODIFY — 新增 3 端点 + `_mask_sensitive_fields()` + `_deep_merge()` |
| `nanobot/dashboard/templates/index.html` | MODIFY — 导航扩展 + 设置面板骨架 |
| `nanobot/dashboard/static/js/config.js` | NEW — 约 600 行双模式 UI 逻辑 |
| `nanobot/config/schema.py` | MODIFY — 精简补全核心约 30 个字段的 `description` |
| `tests/test_dashboard_config.py` | NEW — 5 个自动化测试用例 |

---

## 验证计划

**自动化（`pytest tests/test_dashboard_config.py`）**:
- `test_mask_sensitive_fields` / `test_deep_merge_skips_masked`
- `test_optimistic_lock_rejects_stale` (409 验证)
- `test_save_config_creates_backup` (.bak 文件验证)
- `test_post_config_pydantic_validation` (422 内联错误验证)

**手动**:
1. API Key 字段显示 `__MASKED__`，不修改后保存原值不变
2. 另一标签先保存 → 原标签提交返回 409
3. 勾选 `DESTRUCTIVE` → 二次确认弹窗
4. 保存后出现「需重启」Banner
5. `config.json.bak` 每次保存后刷新

---

## 超出范围

- Git 式多版本配置历史
- 运行时组件热更新（ConfigChangeEvent Pub/Sub）
- 多管理员角色权限分级
