#!/usr/bin/env python3
"""
auto_reviewer.py

Automated L2 Codex review script.
Builds a diff, sends it to the configured provider, and prints the review.
"""

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure nanobot package is in module path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from nanobot.config.loader import load_config
from nanobot.providers.custom_provider import CustomProvider
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.openai_codex_provider import OpenAICodexProvider
from nanobot.providers.registry import PROVIDERS, find_by_name

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_REVIEW_MODELS = (
    "volcengine/doubao-seed-2-0-mini-260215",
    "gemini/gemini-2.5-flash",
)
MERGE_MARKER_RE = re.compile(
    r"(?m)^[ +](?:<<<<<<<(?: .*)?|=======|>>>>>>>?(?: .*)?)\s*$"
)
SECTION_HEADER_RE = re.compile(r"^#+\s+(.+?)\s*$")

PROMPT_TEMPLATE = """[System Background: Nanobot is running an automated Phase L2 review. Focus area: {context}]

Below is the code change you must review (Git Diff):
```diff
{diff_content}
```

Review using these rules:
1. Start with contract behavior, not implementation style. Verify the required behavior was truly restored.
2. Report problems by issue category, not by fragmented API-by-API notes.
3. For each category, list all known residual surfaces in one pass.
4. Severity rules:
   - A: core contract break, silent failure, or exploitable path. Must fix.
   - B: concrete architectural or reliability risk. Must assess.
   - C: theoretical concern. Record only.
5. Verify tests simulate realistic production failure paths instead of synthetic shortcuts.
6. If you detect repeated same-class regressions, state that the root cause is still open.

Allowed conclusions:
1. Review passed. The architecture gap is closed and wrap-up may begin.
2. Review failed. Include the categorized residual issue list with severity.
"""


def _load_repo_env() -> Path | None:
    """Load repo-local .env so review tooling matches normal project runtime."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
        return env_path
    return None


def _apply_env_overrides(config) -> None:
    """Apply NANOBOT_* overrides relevant to provider selection."""
    model_override = os.getenv("NANOBOT_AGENTS__DEFAULTS__MODEL")
    if model_override:
        config.agents.defaults.model = model_override

    for spec in PROVIDERS:
        provider_cfg = getattr(config.providers, spec.name, None)
        if provider_cfg is None:
            continue

        env_prefix = f"NANOBOT_PROVIDERS__{spec.name.upper()}__"
        api_key = os.getenv(env_prefix + "API_KEY")
        api_base = os.getenv(env_prefix + "API_BASE")

        if api_key is not None:
            provider_cfg.api_key = api_key
        if api_base is not None:
            provider_cfg.api_base = api_base


def _make_provider(config):
    """Reuse the main CLI's provider selection contract."""
    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    provider_cfg = config.get_provider(model)

    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        provider = OpenAICodexProvider(default_model=model)
        return provider, model, provider_name, None

    if provider_name == "custom":
        api_base = config.get_api_base(model) or "http://localhost:8000/v1"
        provider = CustomProvider(
            api_key=provider_cfg.api_key if provider_cfg else "no-key",
            api_base=api_base,
            default_model=model,
        )
        return provider, model, provider_name, api_base

    spec = find_by_name(provider_name) if provider_name else None
    if (
        not model.startswith("bedrock/")
        and not (provider_cfg and provider_cfg.api_key)
        and not (spec and spec.is_oauth)
    ):
        raise RuntimeError("No API key configured for the review model/provider.")

    provider = LiteLLMProvider(
        api_key=provider_cfg.api_key if provider_cfg else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=provider_cfg.extra_headers if provider_cfg else None,
        provider_name=provider_name,
    )
    return provider, model, provider_name, config.get_api_base(model)


def _iter_review_runtimes(config):
    """Yield candidate review runtimes in priority order."""
    candidates: list[str] = []
    for model in (config.agents.defaults.model, *BACKUP_REVIEW_MODELS):
        if model and model not in candidates:
            candidates.append(model)

    for model in candidates:
        cfg = config.model_copy(deep=True)
        cfg.agents.defaults.model = model
        try:
            yield _make_provider(cfg)
        except RuntimeError as exc:
            print(f"[!] Skipping review runtime {model}: {exc}")


def _extract_bullet_path(entry: str) -> str | None:
    match = re.search(r"`([^`]+)`", entry)
    if match:
        return match.group(1).strip()

    candidate = entry.split(" (", 1)[0].strip()
    return candidate or None


def _parse_markdown_bullets(path: Path, section_name: str) -> list[str]:
    if not path.exists():
        return []

    items: list[str] = []
    in_section = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not in_section:
            if line == section_name or line == f"## {section_name}":
                in_section = True
            continue

        if not line:
            continue

        header = SECTION_HEADER_RE.match(line)
        if header:
            break

        if line.endswith(":") and not line.startswith("- "):
            break

        if not line.startswith("- "):
            continue

        candidate = _extract_bullet_path(line[2:].strip())
        if candidate:
            items.append(candidate)

    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(item)
    return ordered


def _infer_execute_phase_files() -> tuple[list[str], Path | None]:
    artifact_root = REPO_ROOT / ".agent" / "artifacts" / "execute_phase"
    if not artifact_root.exists():
        return [], None

    handoffs = sorted(
        artifact_root.glob("*/codex_handoff.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for handoff in handoffs:
        files = _parse_markdown_bullets(handoff, "Allowed Write Set")
        existing = [item for item in files if (REPO_ROOT / item).exists()]
        if existing:
            return existing, handoff

    results = sorted(
        artifact_root.glob("*/codex_result.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for result in results:
        files = _parse_markdown_bullets(result, "Changed Files")
        existing = [item for item in files if (REPO_ROOT / item).exists()]
        if existing:
            return existing, result

    return [], None


def _resolve_review_files(files: list[str]) -> list[str]:
    if files:
        return files

    inferred, source = _infer_execute_phase_files()
    if inferred and source:
        print(f"[*] Inferred review scope from: {source}")
        return inferred

    return files


def _run_git_diff(files: list[str], *, staged: bool = False) -> str:
    """Run git diff with a repo-local safe.directory override for Windows setups."""
    safe_dir = REPO_ROOT.resolve().as_posix()
    cmd = [
        "git",
        "-c",
        f"safe.directory={safe_dir}",
        "diff",
    ]
    if staged:
        cmd.append("--staged")
    else:
        cmd.append("HEAD")
    cmd.extend(["--", *files])

    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown git diff error"
        raise RuntimeError(f"git diff failed: {stderr}")
    return result.stdout.strip()


def _classify_local_findings(files: list[str], diff_content: str) -> dict[str, list[str]]:
    severity_a: list[str] = []
    severity_b: list[str] = []
    severity_c: list[str] = []

    normalized_files = [item.replace("\\", "/") for item in files]
    changed_python = [
        item for item in normalized_files
        if item.endswith(".py") and not item.startswith("tests/")
    ]
    changed_tests = [
        item for item in normalized_files
        if item.startswith("tests/") and item.endswith(".py")
    ]

    if MERGE_MARKER_RE.search(diff_content):
        severity_a.append(
            "Diff still contains unresolved merge-conflict markers."
        )

    diff_lines = diff_content.splitlines()
    for idx, line in enumerate(diff_lines):
        if not line.startswith("+") or line.startswith("+++"):
            continue

        content = line[1:].strip()
        lower = content.lower()

        if re.match(r"except(\s+exception\b.*|:)", lower):
            window = "\n".join(
                candidate[1:].strip()
                for candidate in diff_lines[idx + 1: idx + 4]
                if candidate.startswith("+") and not candidate.startswith("+++")
            ).lower()
            if any(token in window for token in ("pass", "return true", "return {}", "return []", "continue")):
                severity_b.append(
                    "Added broad exception handling that appears to swallow failures."
                )

        if any(token in lower for token in ("todo", "fixme", "hack")):
            severity_c.append(
                "Added TODO/FIXME/HACK markers in the reviewed diff."
            )

        if content.startswith("print(") and not any(
            item.startswith("tests/") for item in normalized_files
        ):
            severity_c.append(
                "Added debug-style print statements in non-test review scope."
            )

    if changed_python and not changed_tests:
        severity_b.append(
            "Reviewed Python code changed without corresponding test files in scope."
        )

    return {
        "A": list(dict.fromkeys(severity_a)),
        "B": list(dict.fromkeys(severity_b)),
        "C": list(dict.fromkeys(severity_c)),
    }


def _run_local_fallback_review(files: list[str], diff_content: str, context: str) -> bool:
    findings = _classify_local_findings(files, diff_content)
    scoped_files = files or ["<all changed files>"]

    print("[*] Review runtime: local_static_fallback")
    print(f"[*] Local fallback context: {context}")
    print("[*] Local fallback scope:")
    for file_path in scoped_files:
        print(f"    - {file_path}")

    if findings["A"] or findings["B"] or findings["C"]:
        print("\n" + "=" * 60)
        print("[LOCAL L2 REVIEW RESULTS]")
        print("=" * 60)
        print("Review failed. Local fallback detected the following issues:")
        for severity in ("A", "B", "C"):
            items = findings[severity]
            if not items:
                continue
            print(f"Severity {severity}:")
            for item in items:
                print(f"- {item}")
        print("=" * 60 + "\n")
        return False

    print("\n" + "=" * 60)
    print("[LOCAL L2 REVIEW RESULTS]")
    print("=" * 60)
    print("Review passed via local fallback runtime.")
    print("Remote L2 providers were skipped or unavailable, and deterministic checks found no blocking findings in the scoped diff.")
    print("=" * 60 + "\n")
    return True


async def run_review(files: list[str], context: str) -> bool:
    env_path = _load_repo_env()
    if env_path:
        print(f"[*] Loaded env overrides from: {env_path}")

    config = load_config()
    _apply_env_overrides(config)
    review_files = _resolve_review_files(files)

    diff_content = _run_git_diff(review_files, staged=False)
    if not diff_content:
        diff_content = _run_git_diff(review_files, staged=True)
        if not diff_content:
            print("[!] No diff found for the specified files (neither unstaged nor staged).")
            return False

    if len(diff_content) > 30000:
        print(
            f"[!] Warning: Diff is huge ({len(diff_content)} chars). "
            "Truncating to 30000 characters to prevent token explosion."
        )
        diff_content = diff_content[:30000] + "\n...[TRUNCATED]"

    prompt = PROMPT_TEMPLATE.format(context=context, diff_content=diff_content)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Codex, the elite L2 architectural reviewer and ruthless "
                "gatekeeper for the Nanobot project. You are critical, specific, "
                "and evidence-driven."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    local_only = (
        os.getenv("AUTO_REVIEWER_FORCE_LOCAL") == "1"
        or not getattr(getattr(config.agents, "sandbox", None), "allow_network", True)
    )
    if local_only:
        print("[*] Network-disabled review environment detected; using local fallback runtime.")
        return _run_local_fallback_review(review_files, diff_content, context)

    last_error = "unknown error"
    for provider, model, provider_name, api_base in _iter_review_runtimes(config):
        print(
            f"[*] Review runtime: model={model}, "
            f"provider={provider_name or 'unknown'}, "
            f"api_base={api_base or 'default'}"
        )
        print("[*] Connecting to LLM provider...")

        try:
            response = await provider.chat(
                messages=messages,
                model=model,
                temperature=0.2,
                max_tokens=4000,
            )
            if response.finish_reason == "error":
                last_error = response.content
                print(f"[!] Review runtime {model} failed: {response.content}")
                continue

            print("\n" + "=" * 60)
            print("[CODEX L2 REVIEW RESULTS]")
            print("=" * 60)
            print(response.content)
            print("=" * 60 + "\n")
            return True
        except Exception as exc:
            last_error = str(exc)
            print(f"[!] Review runtime {model} failed: {exc}")

    print("[*] Falling back to local static review runtime after remote failures.")
    if _run_local_fallback_review(review_files, diff_content, context):
        return True

    print(f"[!] All review runtimes failed. Last error: {last_error}")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Codex L2 Reviewer")
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Specific files to diff and review (leave empty for all)",
    )
    parser.add_argument(
        "--context",
        type=str,
        required=True,
        help="Short background context for the review session",
    )

    args = parser.parse_args()
    ok = asyncio.run(run_review(args.files, args.context))
    # Some provider stacks crash during interpreter teardown on Windows even
    # after a successful review response. Exit directly after flushing output
    # so automation sees the real status code.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if ok else 1)
