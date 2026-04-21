from __future__ import annotations
"""
import_users_to_litellm.py
==========================
Phase 60 平滑迁移脚本：将 bff/user_tokens.json（旧 BFF 用户表）
和 employees.xlsx（员工花名册）合并，批量导入至 LiteLLM 数据库。

核心特性：
  - 幂等 (Idempotent)：先查询是否已存在，存在则跳过，可安全重复运行
  - 零停机 (Zero-Downtime)：强制透传原始 Token 字符串，旧客户端无感知
  - 容错 (Fault-Tolerant)：单人创建失败不中断整体，错误记至 failed_users.txt
  - 部门分组 (Team-Based)：按部门分配至 LiteLLM Team，控制模型访问权限

使用方法：
  # 1. 确保 LiteLLM 容器已启动（或临时挂在 :8100 验证期端口）
  # 2. 设置环境变量（或直接修改下方常量）
  python scripts/import_users_to_litellm.py

  # 支持的环境变量覆盖：
  LITELLM_API=http://localhost:8099
  LITELLM_MASTER_KEY=sk-admin-xxxx

employees.xlsx 格式（可选，无此文件则仅从 user_tokens.json 导入）：
  列名: name(必须), department(建议), email(可选)
  name 列的值必须与 user_tokens.json 中的 username 对应，以便匹配部门信息
"""

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

# ──────────────────── 配置区 ────────────────────
LITELLM_API = os.environ.get("LITELLM_API", "http://localhost:8099")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")  # 必须设置，否则报 401

HEADERS = {
    "Authorization": f"Bearer {MASTER_KEY}",
    "Content-Type": "application/json",
}

# 部门 → 允许访问的模型列表（未匹配部门落入 "default"）
DEPT_MODEL_MAP: dict[str, list[str]] = {
    "管理层":   ["gpt-4o", "gpt-4o-mini"],
    "IT":       ["gpt-4o", "gpt-4o-mini"],
    "研发部":   ["gpt-4o", "gpt-4o-mini"],
    "业务部":   ["gpt-4o-mini"],
    "行政部":   ["gpt-4o-mini"],
    "default":  ["gpt-4o-mini"],
}

# 文件路径（相对于本脚本的父目录 bff/）
_BFF_DIR = Path(__file__).parent.parent  # = bff/
TOKENS_JSON = _BFF_DIR / "user_tokens.json"      # {token_string: username}
EXCEL_PATH  = Path(__file__).parent / "employees.xlsx"   # 员工花名册（可选）
FAILED_LOG  = Path(__file__).parent / "failed_users.txt"

# API 请求超时秒数
REQUEST_TIMEOUT = 10


# ──────────────────── 辅助函数 ────────────────────

def _check_master_key() -> None:
    """启动前校验 MASTER_KEY 已配置"""
    if not MASTER_KEY:
        raise SystemExit(
            "❌ LITELLM_MASTER_KEY 未设置！\n"
            "   请运行: export LITELLM_MASTER_KEY=sk-admin-xxx\n"
            "   或直接修改脚本顶部的 MASTER_KEY 常量"
        )


def _ensure_team(dept: str, team_cache: dict[str, str]) -> str:
    """
    幂等地创建或复用 LiteLLM Team，返回 team_id。
    使用内存缓存避免重复 API 调用。
    """
    if dept in team_cache:
        return team_cache[dept]

    # 查询现有 Team 列表
    try:
        r = requests.get(
            f"{LITELLM_API}/team/list",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        existing = {
            t["team_alias"]: t["team_id"]
            for t in r.json().get("teams", [])
        }
    except Exception as e:
        raise RuntimeError(f"无法获取 Team 列表: {e}") from e

    if dept in existing:
        team_cache[dept] = existing[dept]
        return existing[dept]

    # 创建新 Team
    models = DEPT_MODEL_MAP.get(dept, DEPT_MODEL_MAP["default"])
    resp = requests.post(
        f"{LITELLM_API}/team/new",
        headers=HEADERS,
        json={"team_alias": dept, "models": models},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    team_id: str = resp.json()["team_id"]
    team_cache[dept] = team_id
    print(f"  🏢 创建新 Team: {dept} ({', '.join(models)})")
    return team_id


def _key_exists(token: str) -> bool:
    """检查 Token 字符串是否已在 LiteLLM 中注册"""
    try:
        r = requests.get(
            f"{LITELLM_API}/key/info",
            headers=HEADERS,
            params={"key": token},
            timeout=REQUEST_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        # 网络异常时保守返回 False，下游创建步骤会再次处理错误
        return False


# ──────────────────── 主逻辑 ────────────────────

def main() -> None:
    _check_master_key()

    # 1. 加载旧 user_tokens.json: {token_str: username}
    old_tokens: dict[str, str] = {}
    if TOKENS_JSON.exists():
        with open(TOKENS_JSON, encoding="utf-8") as f:
            old_tokens = json.load(f)
        print(f"📂 已加载旧 Token 文件: {len(old_tokens)} 条记录 ({TOKENS_JSON})")
    else:
        print(f"⚠️  未找到 {TOKENS_JSON}，将仅从 employees.xlsx 导入")

    # 2. 加载员工花名册（可选）
    df: pd.DataFrame = pd.DataFrame()
    if EXCEL_PATH.exists():
        df = pd.read_excel(EXCEL_PATH)
        print(f"📊 已加载员工花名册: {len(df)} 行 ({EXCEL_PATH})")
    else:
        print(f"ℹ️  未找到 {EXCEL_PATH}，所有用户将归入 'default' 部门")

    # 3. 构建待导入记录列表
    # 以 username 为 key 去重，优先从旧 Token 文件建立映射
    name_to_dept: dict[str, str] = {}
    if not df.empty and "name" in df.columns:
        for _, row in df.iterrows():
            name = str(row["name"]).strip()
            dept = str(row.get("department", "default")).strip()
            name_to_dept[name] = dept

    records: list[dict] = []
    # 已有旧 Token 的用户（保留原始 Token 字符串）
    for token_str, username in old_tokens.items():
        records.append({
            "token": token_str,
            "name":  username,
            "dept":  name_to_dept.get(username, "default"),
        })

    # Excel 中存在但旧 JSON 中没有的新员工
    if not df.empty:
        existing_names = {v for v in old_tokens.values()}
        for _, row in df.iterrows():
            name = str(row["name"]).strip()
            if name not in existing_names:
                raw_token = str(row.get("token", "")).strip()
                if not raw_token:
                    print(f"  ⚠️  跳过新员工 {name}：Excel 中无 token 列，请手动在 Dashboard 中生成")
                    continue
                records.append({
                    "token": raw_token,
                    "name":  name,
                    "dept":  str(row.get("department", "default")).strip(),
                })

    print(f"\n🚀 待处理记录: {len(records)} 条\n{'─' * 50}")

    # 4. 执行导入（幂等 + 容错）
    team_cache: dict[str, str] = {}
    success_list: list[dict] = []
    failed_list:  list[dict] = []

    for rec in records:
        name  = rec["name"]
        token = rec["token"]
        dept  = rec["dept"]
        try:
            # 幂等检查
            if _key_exists(token):
                print(f"  ⏭  跳过（已存在）: {name} [{dept}]")
                continue

            team_id = _ensure_team(dept, team_cache)
            models  = DEPT_MODEL_MAP.get(dept, DEPT_MODEL_MAP["default"])

            resp = requests.post(
                f"{LITELLM_API}/key/generate",
                headers=HEADERS,
                json={
                    "key":       token,       # 🔑 强制透传旧 Token — 零停机核心保证
                    "key_alias": name,
                    "team_id":   team_id,
                    "models":    models,
                    "metadata":  {"dept": dept, "source": "import_script_phase60"},
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            print(f"  ✅ 导入成功: {name} [{dept}] → {', '.join(models)}")
            success_list.append(rec)
            time.sleep(0.1)  # 避免批量并发冲击 LiteLLM API

        except Exception as e:
            err_msg = str(e)
            print(f"  ❌ 失败: {name} [{dept}] — {err_msg}")
            failed_list.append({**rec, "error": err_msg})

    # 5. 汇总报告
    print(f"\n{'─' * 50}")
    print(f"🏁 导入完成: 成功 {len(success_list)} 人 | 失败 {len(failed_list)} 人")

    if failed_list:
        with open(FAILED_LOG, "w", encoding="utf-8") as f:
            f.write("name\tdept\ttoken\terror\n")
            for item in failed_list:
                f.write(f"{item['name']}\t{item['dept']}\t{item['token']}\t{item['error']}\n")
        print(f"\n  ⚠️  失败名单已记录至 {FAILED_LOG}")
        print("     请修正失败原因后重跑本脚本（幂等安全，已成功的用户将被自动跳过）")
    else:
        print("  🎉 全部成功，无失败记录！")


if __name__ == "__main__":
    main()
