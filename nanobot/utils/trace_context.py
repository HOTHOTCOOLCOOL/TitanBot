"""Phase 42B: Zero-dependency full-chain trace context."""
import contextvars
import uuid
from typing import FrozenSet
from loguru import logger

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="no-trace")
_route_tags_var: contextvars.ContextVar[FrozenSet[str]] = contextvars.ContextVar(
    "route_tags", default=frozenset()
)

def generate_trace_id() -> str:
    """Generate a human-readable trace ID with t- prefix."""
    return f"t-{uuid.uuid4().hex[:8]}"

def get_current_trace_id() -> str:
    return _trace_id_var.get()

def add_route_tag(tag: str) -> None:
    """Add a routing/interception tag to current trace context (idempotent)."""
    current = _route_tags_var.get()
    _route_tags_var.set(current | {tag})  # frozenset union — no mutation bugs

def get_route_tags() -> FrozenSet[str]:
    return _route_tags_var.get()


class RoutingTag:
    """Tags for routing decisions (non-exception paths)."""
    CHITCHAT_FAST    = "CHITCHAT_FAST"       # 正则旁路快速路
    VLM_ROUTE        = "VLM_ROUTE"           # 视觉模型路由
    RAG_ADAPT        = "RAG_ADAPT"           # 知识库部分命中自适应
    SUBAGENT_CALLBACK = "SUBAGENT_CALLBACK"  # Subagent 回调入站


class InterceptTag:
    """Tags for middleware interception events."""
    L1_BLOCK       = "L1_BLOCK"        # L1 验证层规则拦截
    HITL_SUSPEND   = "HITL_SUSPEND"    # HITL 挂起等待人工
    CB_TRIP        = "CB_TRIP"         # 熔断器触发
    FLOOD_BLOCK    = "FLOOD_BLOCK"     # 防洪限流
    CRASH_RECOVERY = "CRASH_RECOVERY"  # 崩溃恢复路径


def trace_log_patcher(record: dict) -> None:
    """Loguru record patcher: prepend [trace_id] to every log message.

    Mount at startup: logger.configure(patcher=trace_log_patcher)
    Defensive: never raises, never silences logs.
    """
    try:
        tid = _trace_id_var.get()
        if tid != "no-trace":
            record["message"] = f"[{tid}] {record['message']}"
    except Exception:
        pass  # Patcher must NEVER break the logging pipeline
