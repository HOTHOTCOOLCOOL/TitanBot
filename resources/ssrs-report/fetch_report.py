#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSRS Report Fetcher
--------------------
从内网 SSRS (SQL Server Reporting Services) 服务器获取报告内容。

认证优先级（三层 fallback，密码安全递减）：
  1. SSPI 当前用户透传  — 直接用 Windows 登录态，完全不需要密码配置 [最推荐]
  2. Windows Credential Manager — 系统加密存储，用 keyring 读取 [推荐]
  3. .env 明文             — SSRS_USER / SSRS_PASSWORD / SSRS_DOMAIN [不推荐]

初次配置（安全存储，代替 .env 明文）：
  python fetch_report.py --setup-credentials

依赖：requests, requests-ntlm, requests-negotiate-sspi, keyring, beautifulsoup4, fpdf2
"""

import csv
import io
import json
import os
import re
import sys
tempfile = __import__('tempfile')  # lazy import to avoid circular
from pathlib import Path
from typing import Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# CRITICAL: Force UTF-8 output immediately so Windows console (cp1252) never
# causes UnicodeEncodeError when the script is called by the agent.
# ---------------------------------------------------------------------------
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import requests
    from requests_ntlm import HttpNtlmAuth
except ImportError:
    print("ERROR: Missing dependencies. Please run: pip install requests requests-ntlm")
    sys.exit(1)

# Optional: SSPI passthrough (uses current Windows login session, no password needed)
try:
    from requests_negotiate_sspi import HttpNegotiateAuth
    HAS_SSPI = True
except ImportError:
    HAS_SSPI = False

# Optional: Windows Credential Manager secure storage
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

# Optional: HTML parsing
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Optional: PDF generation (fpdf2 package)
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

SSRS_KEYRING_SERVICE = "nanobot_ssrs"


# ---------------------------------------------------------------------------
# Authentication (3-tier secure fallback)
# ---------------------------------------------------------------------------

AUTH_METHOD_USED: str = "unknown"  # set during get_auth(), for logging


def get_auth():
    """
    Resolve authentication using the most secure available method.

    Priority:
      1. SSPI (current Windows user session)  — zero config, most secure
      2. Windows Credential Manager (keyring) — encrypted, one-time setup
      3. .env plaintext                       — fallback, least preferred

    Returns a requests auth object compatible with requests.get(auth=...).
    """
    global AUTH_METHOD_USED

    # --- Layer 1: SSPI passthrough (current Windows login, NO password needed) ---
    if HAS_SSPI:
        AUTH_METHOD_USED = "sspi"
        print("[SSRS Auth] Using SSPI (current Windows session)", file=sys.stderr)
        return HttpNegotiateAuth()

    # --- Layer 2: Windows Credential Manager (keyring, encrypted storage) ---
    if HAS_KEYRING:
        user = keyring.get_password(SSRS_KEYRING_SERVICE, "username")
        password = keyring.get_password(SSRS_KEYRING_SERVICE, "password")
        domain = keyring.get_password(SSRS_KEYRING_SERVICE, "domain") or ""
        if user and password:
            AUTH_METHOD_USED = "credential_manager"
            print("[SSRS Auth] Using Windows Credential Manager", file=sys.stderr)
            ntlm_user = f"{domain}\\{user}" if domain else user
            return HttpNtlmAuth(ntlm_user, password)

    # --- Layer 3: .env plaintext (least preferred, warn user) ---
    user = os.environ.get("SSRS_USER", "")
    password = os.environ.get("SSRS_PASSWORD", "")
    domain = os.environ.get("SSRS_DOMAIN", "")
    if user and password:
        AUTH_METHOD_USED = "env_plaintext"
        print(
            "[SSRS Auth] WARNING: Using plaintext credentials from .env. "
            "Run 'python fetch_report.py --setup-credentials' to store them securely.",
            file=sys.stderr
        )
        ntlm_user = f"{domain}\\{user}" if domain else user
        return HttpNtlmAuth(ntlm_user, password)

    # --- All layers failed ---
    raise EnvironmentError(
        "SSRS 认证未配置。请选择以下方式之一：\n"
        "  [推荐] 运行: python fetch_report.py --setup-credentials\n"
        "         → 安全存储到 Windows Credential Manager（加密，无需明文）\n"
        "  [备选] 在 .env 设置: SSRS_USER=xxx  SSRS_PASSWORD=xxx"
    )


def setup_credentials_interactive():
    """
    Interactive one-time setup: store SSRS credentials in Windows Credential Manager.
    Credentials are encrypted by Windows DPAPI and never stored in plaintext.
    """
    import getpass

    if not HAS_KEYRING:
        print("ERROR: keyring library not installed. Run: pip install keyring")
        sys.exit(1)

    print("=" * 55)
    print(" SSRS 凭据安全存储向导 (Windows Credential Manager)")
    print("=" * 55)
    print(" 凭据将加密存储在系统密钥库，不会写入任何文件。")
    print()

    user = input("Windows 用户名 (不含域名): ").strip()
    domain = input("域名 (可留空，例如 CORP): ").strip()
    password = getpass.getpass("Windows 密码 (输入时不显示): ")

    keyring.set_password(SSRS_KEYRING_SERVICE, "username", user)
    keyring.set_password(SSRS_KEYRING_SERVICE, "password", password)
    if domain:
        keyring.set_password(SSRS_KEYRING_SERVICE, "domain", domain)

    print()
    print("[OK] 凭据已安全存储到 Windows Credential Manager。")
    print("     可通过 控制面板 > 凭据管理器 > Windows 凭据 查看（服务名: nanobot_ssrs）")
    print("     .env 中的 SSRS_USER / SSRS_PASSWORD 条目现在可以删除。")


def load_registry() -> dict:
    """Load the reports registry JSON."""
    registry_path = Path(__file__).parent / "reports_registry.json"
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry not found: {registry_path}")
    with open(registry_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Report Resolution
# ---------------------------------------------------------------------------

def find_report(query: str, registry: dict) -> Optional[tuple[str, dict]]:
    """
    Find a report entry by name or alias.
    Returns (report_name, report_config) or None if not found.
    """
    query_lower = query.lower().strip()
    reports = registry.get("reports", {})

    for name, config in reports.items():
        # Exact name match
        if query_lower == name.lower():
            return name, config
        # Alias match
        for alias in config.get("aliases", []):
            if query_lower in alias.lower() or alias.lower() in query_lower:
                return name, config
    return None


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def build_report_url(base_url: str, extra_params: dict, fmt: str) -> str:
    """
    Append rs:Format and any extra params to the SSRS base URL.
    SSRS URLs already contain the report path as a query string value,
    so we append additional params carefully.
    """
    separator = "&" if "?" in base_url else "?"
    params = {**extra_params, "rs:Format": fmt}
    # SSRS uses colon in param names which urlencode handles correctly
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}{separator}{query_string}"


def fetch_as_csv(url: str, auth, timeout: int = 30) -> Optional[str]:
    """Download report as CSV and return as string."""
    csv_url = build_report_url(url, {}, "CSV")
    try:
        resp = requests.get(csv_url, auth=auth, timeout=timeout, verify=False)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/csv" in content_type or "text/plain" in content_type:
            return resp.text
        # Sometimes SSRS returns content without proper content-type
        if resp.text.strip().startswith('"') or "," in resp.text[:100]:
            return resp.text
        return None
    except requests.RequestException as e:
        print(f"[SSRS] CSV fetch failed: {e}", file=sys.stderr)
        return None


def fetch_as_html(url: str, auth, timeout: int = 30) -> Optional[str]:
    """Download report as HTML4.0 and parse to readable text."""
    html_url = build_report_url(url, {}, "HTML4.0")
    try:
        resp = requests.get(html_url, auth=auth, timeout=timeout, verify=False)
        resp.raise_for_status()

        if HAS_BS4:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove script/style
            for tag in soup(["script", "style", "head"]):
                tag.decompose()
            # Extract table data cleanly
            tables = soup.find_all("table")
            if tables:
                result = []
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        row_text = " | ".join(cell.get_text(strip=True) for cell in cells)
                        if row_text.strip():
                            result.append(row_text)
                return "\n".join(result)
            return soup.get_text(separator="\n", strip=True)
        else:
            # Fallback: strip HTML tags with regex
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
    except requests.RequestException as e:
        print(f"[SSRS] HTML fetch failed: {e}", file=sys.stderr)
        return None


def parse_csv_to_readable(csv_text: str) -> str:
    """Convert CSV content to a readable table format for LLM."""
    try:
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        if not rows:
            return csv_text

        # Calculate column widths
        col_widths = []
        for col_idx in range(len(rows[0])):
            max_w = max(len(str(row[col_idx])) if col_idx < len(row) else 0 for row in rows)
            col_widths.append(min(max_w, 40))  # cap at 40 chars

        lines = []
        for i, row in enumerate(rows):
            line = " | ".join(str(cell).ljust(col_widths[j]) if j < len(col_widths) else cell
                              for j, cell in enumerate(row))
            lines.append(line)
            if i == 0:
                lines.append("-" * len(line))  # header separator
        return "\n".join(lines)
    except Exception:
        return csv_text


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_pdf(report_name: str, content: str, output_path: Optional[str] = None) -> str:
    """
    Generate a PDF file from the report text content.
    Returns the path to the saved PDF file.

    Requires: pip install fpdf2
    """
    if not HAS_FPDF:
        raise ImportError(
            "fpdf2 not installed. Run: pip install fpdf2\n"
            "Then retry: python fetch_report.py <report> --pdf"
        )

    # Determine output path
    if not output_path:
        import tempfile
        tmp_dir = Path(tempfile.gettempdir())
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', report_name)
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_path = str(tmp_dir / f"{safe_name}_{date_str}.pdf")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font('Helvetica', 'B', 16)
    date_str = datetime.now().strftime('%Y-%m-%d')
    pdf.cell(0, 12, f"{report_name} - {date_str}", ln=True, align='C')
    pdf.ln(4)

    # Subtitle
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Generated by Nanobot SSRS Skill at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Divider
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Content (monospaced for table alignment)
    pdf.set_font('Courier', '', 8)
    for line in content.split('\n'):
        # Encode to latin-1 safely (fpdf default), replace unsupported chars
        safe_line = line.encode('latin-1', errors='replace').decode('latin-1')
        # Wrap very long lines
        if len(safe_line) > 120:
            safe_line = safe_line[:120] + '...'
        pdf.cell(0, 4, safe_line, ln=True)

    pdf.output(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def fetch_report(report_query: str, preferred_format: str = "auto") -> dict:
    """
    Main function: resolve report by name/alias, fetch content, return result dict.

    Args:
        report_query: Report name or alias (e.g., "购物村排名", "Top sales")
        preferred_format: "CSV", "HTML4.0", or "auto" (use registry preference)

    Returns:
        {
          "success": bool,
          "report_name": str,
          "format_used": str,
          "content": str,       # Readable text content for LLM
          "raw_url": str,
          "error": str | None
        }
    """
    registry = load_registry()
    found = find_report(report_query, registry)

    if not found:
        # List available reports for helpful error message
        available = list(registry.get("reports", {}).keys())
        return {
            "success": False,
            "report_name": report_query,
            "format_used": None,
            "content": None,
            "raw_url": None,
            "error": (
                f"未找到名为 '{report_query}' 的报告。\n"
                f"可用报告：{', '.join(available)}\n"
                "请检查 reports_registry.json 或添加新报告条目。"
            )
        }

    report_name, config = found
    base_url = config["url"]
    fmt = preferred_format if preferred_format != "auto" else config.get("preferred_format", "CSV")
    fallback_fmt = config.get("fallback_format", "HTML4.0")

    try:
        auth = get_auth()
    except EnvironmentError as e:
        return {
            "success": False,
            "report_name": report_name,
            "format_used": None,
            "content": None,
            "raw_url": base_url,
            "auth_method": None,
            "error": str(e)
        }

    content = None
    format_used = fmt

    # Try preferred format first
    print(f"[SSRS] Fetching '{report_name}' as {fmt}...", file=sys.stderr)
    if fmt == "CSV":
        raw = fetch_as_csv(base_url, auth)
        if raw:
            content = parse_csv_to_readable(raw)
    elif fmt.startswith("HTML"):
        content = fetch_as_html(base_url, auth)

    # Fallback format
    if not content and fallback_fmt != fmt:
        print(f"[SSRS] Falling back to {fallback_fmt}...", file=sys.stderr)
        format_used = fallback_fmt
        if fallback_fmt == "CSV":
            raw = fetch_as_csv(base_url, auth)
            if raw:
                content = parse_csv_to_readable(raw)
        elif fallback_fmt.startswith("HTML"):
            content = fetch_as_html(base_url, auth)

    if not content:
        return {
            "success": False,
            "report_name": report_name,
            "format_used": format_used,
            "content": None,
            "raw_url": base_url,
            "error": f"无法从 SSRS 获取报告内容（尝试了 {fmt} 和 {fallback_fmt} 格式）。请检查网络连接和认证配置。"
        }

    return {
        "success": True,
        "report_name": report_name,
        "format_used": format_used,
        "content": content,
        "raw_url": base_url,
        "auth_method": AUTH_METHOD_USED,
        "error": None
    }


# ---------------------------------------------------------------------------
# CLI Interface (for direct testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Fetch SSRS Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
认证配置（推荐顺序）：
  1. 自动SSPI  - 已安装 requests-negotiate-sspi 则直接用 Windows 登录态
  2. 安全存储  - python fetch_report.py --setup-credentials
  3. .env明文  - 设置 SSRS_USER + SSRS_PASSWORD（最后手段）
        """
    )
    parser.add_argument("report", nargs="?", default=None,
                        help="Report name or alias. Not required with --list or --setup-credentials.")
    parser.add_argument("--format", default="auto", choices=["auto", "CSV", "HTML4.0"],
                        help="Export format (default: auto, uses registry preference)")
    parser.add_argument("--list", action="store_true", help="List all available reports")
    parser.add_argument("--setup-credentials", action="store_true",
                        help="Securely store SSRS credentials in Windows Credential Manager")
    parser.add_argument("--pdf", action="store_true",
                        help="Generate a PDF file from the report content (requires fpdf2)")
    parser.add_argument("--pdf-output", default=None, metavar="PATH",
                        help="Custom output path for the PDF file (default: auto in temp dir)")
    args = parser.parse_args()

    if args.setup_credentials:
        setup_credentials_interactive()
        sys.exit(0)

    if args.list:
        reg = load_registry()
        print("\nAvailable Reports:")
        print("=" * 60)
        for name, cfg in reg.get("reports", {}).items():
            aliases = ", ".join(cfg.get("aliases", []))
            print(f"  {name}")
            print(f"    别名: {aliases}")
            print(f"    说明: {cfg.get('description', 'N/A')}")
            print(f"    格式: {cfg.get('preferred_format', 'CSV')}")
            print()
        sys.exit(0)

    result = fetch_report(args.report, preferred_format=args.format)

    if result["success"]:
        print(f"\n=== Report: {result['report_name']} (格式: {result['format_used']}) ===\n")
        print(result["content"])

        # --pdf: generate PDF and print the output path on a parseable line
        if args.pdf:
            try:
                pdf_path = generate_pdf(
                    result["report_name"],
                    result["content"],
                    output_path=args.pdf_output,
                )
                # Print on its own line so the agent can grep for it
                print(f"\nPDF_PATH:{pdf_path}")
            except ImportError as e:
                print(f"\n[PDF ERROR] {e}", file=sys.stderr)
                sys.exit(1)
    else:
        print(f"\n[ERROR] {result['error']}", file=sys.stderr)
        sys.exit(1)
