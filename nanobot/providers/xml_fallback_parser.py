"""
Provider-Level XML Tool Call Fallback Parser — V2.

Only activated when a provider returns an empty tool_calls field but embeds
tool invocations in the text content. Uses a Read-Only strategy: tool calls
are extracted but `content` is NEVER modified.

Known failure modes handled:
  - Claude <tool_use> leaking into content (LiteLLM gateway degradation)
  - Generic <tool_call><tool_name>...</tool_name> (open-source vLLM fine-tunes)
  - JSON-wrapped <tool_call>{...}</tool_call> (Qwen/DashScope style)

Security invariants:
  - Only tools in `valid_tool_names` are extracted (whitelist gate)
  - All extracted calls pass through AgentLoop's existing L1 + HITL middleware
  - Deterministic IDs ensure WAL checkpoint compatibility (Phase 40B-1)
"""
import hashlib
import json
import re
from loguru import logger
from typing import Any

try:
    import json_repair as _json_repair
except ImportError:
    _json_repair = None  # type: ignore


# ── Precompiled patterns (module-level, compiled once) ──────────────────────
# 每个模式内部均限制匹配长度 (1~8000 chars) 以防 ReDoS 回溯炸弹。
# 故意不包含 _RE_FENCE (纯 JSON 围栏代码块)——该匹配缺乏"工具调用意图"标志，误报率
# 过高，已在 Harness 辩证中被彻底废弃。

# Pattern 1: Claude <tool_use><name>...</name><input>...</input></tool_use>
_RE_CLAUDE = re.compile(
    r"<tool_use>\s*<name>([^<]{1,100})</name>\s*<input>(.{1,8000}?)</input>\s*</tool_use>",
    re.DOTALL,
)

# Pattern 2: Generic <tool_call><tool_name>...</tool_name><parameters>...</parameters></tool_call>
_RE_GENERIC = re.compile(
    r"<tool_call>\s*<tool_name>([^<]{1,100})</tool_name>\s*<parameters>(.{1,8000}?)</parameters>\s*</tool_call>",
    re.DOTALL,
)

# Pattern 3: JSON-wrapped <tool_call>{...}</tool_call> (Qwen/DashScope)
_RE_JSON_WRAP = re.compile(
    r"<tool_call>\s*(\{.{1,8000}?})\s*</tool_call>",
    re.DOTALL,
)

# Keys to look for in JSON-wrapped objects
_NAME_KEYS = ("name", "tool_name", "function", "function_name")
_ARG_KEYS  = ("arguments", "parameters", "args", "input", "inputs")


# ── Internal helpers ────────────────────────────────────────────────────────

def _make_deterministic_id(content_hash: str, index: int) -> str:
    """Deterministic call ID for WAL checkpoint compatibility (Phase 40B-1).

    Format matches LiteLLM's 'call_xxxxxxxx' convention, prefixed with 'xf'
    to signal fallback origin in logs.
    """
    return f"call_xf{content_hash[:14]}{index:02d}"


def _parse_args(raw: str) -> dict[str, Any]:
    """Parse tool arguments from a raw string.

    Priority:
      1. stdlib json.loads  — strict, no over-repair
      2. json_repair.loads  — lenient, for slightly malformed JSON
      3. {"_raw": raw}      — last-resort passthrough so we never raise
    """
    raw = raw.strip()
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    if _json_repair:
        try:
            result = _json_repair.loads(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return {"_raw": raw}


def _extract_name(obj: dict) -> str | None:
    for k in _NAME_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _extract_args(obj: dict) -> dict[str, Any]:
    for k in _ARG_KEYS:
        v = obj.get(k)
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            return _parse_args(v)
    # Fallback: drop all name keys, treat remainder as args
    return {k: v for k, v in obj.items() if k not in _NAME_KEYS}


# ── Public API ───────────────────────────────────────────────────────────────

class XmlFallbackParser:
    """Stateless XML tool call extractor using a Read-Only strategy.

    Designed for use in LLMProvider._parse_response() when structured
    tool_calls is empty but content contains embedded XML tool invocations.
    """

    @staticmethod
    def extract(
        content: str,
        valid_tool_names: set[str] | frozenset[str],
        provider_name: str = "unknown",
    ) -> list[dict[str, Any]]:
        """Extract XML-embedded tool calls.

        Read-Only: `content` is NEVER modified here.

        Args:
            content: Raw LLM response text.
            valid_tool_names: Set of tools currently registered in the active
                              ToolRegistry. Only tools in this set are extracted.
                              Built from the `tools` parameter passed to chat().
            provider_name: For log tagging and metrics.

        Returns:
            List of dicts: [{id, name, arguments}] — same shape as ToolCallRequest.
        """
        if not content or "<" not in content:
            return []
        if not valid_tool_names:
            # No registry info available — unsafe to guess
            logger.debug("XmlFallback: skipped, valid_tool_names is empty")
            return []

        content_hash = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()
        extracted: list[dict[str, Any]] = []

        def _accept(name: str, args_raw: str) -> None:
            n = name.strip()
            if n not in valid_tool_names:
                logger.debug(f"XmlFallback: ignoring unknown tool '{n}' (not in registry)")
                return
            extracted.append({
                "id": _make_deterministic_id(content_hash, len(extracted)),
                "name": n,
                "arguments": _parse_args(args_raw),
            })

        # ── Pattern 1: Claude <tool_use> ────────────────────────────────
        for m in _RE_CLAUDE.finditer(content):
            _accept(m.group(1), m.group(2))

        # ── Pattern 2: Generic <tool_call><tool_name> (try only if P1 failed) ──
        if not extracted:
            for m in _RE_GENERIC.finditer(content):
                _accept(m.group(1), m.group(2))

        # ── Pattern 3: JSON-wrapped <tool_call>{...} ──────────────────────
        if not extracted:
            for m in _RE_JSON_WRAP.finditer(content):
                try:
                    obj = _parse_args(m.group(1))
                    name = _extract_name(obj)
                    if name:
                        args = _extract_args(obj)
                        _accept(name, json.dumps(args, ensure_ascii=False))
                except Exception:
                    continue

        if extracted:
            tool_names = [t["name"] for t in extracted]
            logger.warning(
                f"XmlFallback [{provider_name}]: Rescued {len(extracted)} tool call(s) "
                f"from text content: {tool_names}. "
                f"Provider returned empty tool_calls — possible gateway degradation."
            )
            try:
                from nanobot.utils.metrics import metrics
                metrics.increment("xml_fallback_activations")
            except Exception:
                pass

        return extracted
