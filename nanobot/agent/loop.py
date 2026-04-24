"""Agent loop: the core processing engine."""
from nanobot.agent.i18n import msg as i18n_msg

import asyncio
from contextlib import AsyncExitStack
import json
import json_repair
from pathlib import Path
import time
import traceback
import re
from typing import Any
from dataclasses import dataclass, field

@dataclass
class LoopResult:
    final_content: str | None = None
    tools_used: list[str] = field(default_factory=list)
    tool_calls_with_args: list[dict] = field(default_factory=list)
    milestone_summary: str | None = None
    action_reason: str | None = None
    exit_kind: str = "success"

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage, ToolExecutedEvent, KnowledgeMatchedEvent, MemoryConsolidatedEvent
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry

from nanobot.agent.subagent import SubagentManager
from nanobot.agent.coordinator import CoordinatorManager
from nanobot.agent.task_tracker import TaskTracker, TaskStatus
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.personalization import MemoryDistiller
from nanobot.session.manager import Session, SessionManager
from nanobot.agent.commands import CommandHandler
from nanobot.agent.memory_manager import MemoryManager
from nanobot.agent.state_handler import StateHandler
from nanobot.agent.verification import VerificationLayer
from nanobot.utils.metrics import metrics
from nanobot.agent.routing import IntentClassifier, ModelRouter



# ── Module-level constants (extracted from inline for readability) ──

# Tool names that warrant a "continue executing" nudge after their completion
_CONTINUE_TOOLS = {"outlook", "attachment_analyzer"}

# Safety guard: max number of message() calls per agent loop to prevent runaway floods
_MAX_MESSAGE_CALLS = 3

# Maximum seconds to wait for a single LLM call before treating it as a timeout
_LLM_CALL_TIMEOUT = 120

# Phrases indicating the LLM is stalling instead of calling tools
_WAIT_PHRASES = [
    "稍等", "稍候", "马上", "现在开始", "这就开始", "正在为",
    "working on it", "wait a", "just a sec", "let me start",
]

# Phrases indicating the LLM is hallucinating task completion without tool usage
_FAKE_COMPLETION_PHRASES = [
    "已发送", "已完成", "发送完毕", "处理完成", "task completed", "have sent the email",
]

# Keywords in the LLM response that suggest the workflow failed
# (Removed in Phase 64: ExitKind architectural refactoring ensures failures are explicit)

# Phase 39 / 42C: Chitchat routing extracted to nanobot.agent.routing

# ── Phase 40A-1: Tool Result Truncation Constants ──
_MAX_TOOL_RESULT_CHARS: int = 16_000   # 硬上限：约 8000 token
_TOOL_RESULT_HEAD_CHARS: int = 8_000   # 截断时保留头部字符数

def _normalize_tool_result(result: Any, tool_name: str, max_chars: int = 16_000) -> str:
    """强制截断超长工具结果，保留头尾以保证信息完整性。"""
    if isinstance(result, BaseException):
        return f"Error: {result}"
    text = str(result) if result is not None else "(empty)"
    if len(text) <= max_chars:
        return text
    head_chars = max_chars // 2
    head = text[:head_chars]
    tail = text[-(max_chars - head_chars):] 
    return (
        f"{head}\n\n"
        f"... [TRUNCATED: {len(text)} chars → {max_chars} chars limit] ...\n\n"
        f"... (last segment) {tail}"
    )


# D3: Maximum characters to inject into system prompt from RAG/KG/reflections/experience/few-shot
_INJECTION_BUDGET = 8000

# ── Phase 33: Enhanced loop detection + action history ──

# Signature delimiter for multi-tool iterations (ASCII Record Separator — won't appear in JSON values)
_SIG_DELIMITER = "\x1e"
# Fuzzy loop detection: analyse the most recent N tool call iterations
_FUZZY_LOOP_WINDOW = 12
# A single tool-action pair exceeding this ratio in the window = loop
_FUZZY_DOMINANCE_RATIO = 0.75
# Max recent actions to track for history summary
_MAX_ACTION_HISTORY = 10
# Sentinel prefix for action history injection (used for cleanup and budget tracking)
_ACTION_HISTORY_SENTINEL = "\n\n--- 📋 Recent UI Action History ---\n"
# Cap per injection for action history (must also fit within global _INJECTION_BUDGET)
_ACTION_HISTORY_MAX = 1500


def _detect_fuzzy_loop(recent_sigs: list[str]) -> bool:
    """Detect semantic loops via tool-action frequency dominance + cycle detection.

    Two complementary methods:
    1. Frequency dominance: if a single (tool, action) pair dominates >=75% of the
       recent window AND every call uses the same arguments (no progress), it's a loop.
    2. Cyclic subsequence: if a (tool.action + normalized_args) sequence forms a
       repeating cycle of length 2-4, repeating >=3 times.
    """
    if len(recent_sigs) < 4:
        return False

    from collections import Counter
    window = recent_sigs[-_FUZZY_LOOP_WINDOW:]

    # --- Method 1: Frequency dominance with argument stagnation check ---
    pairs: list[str] = []
    pair_args: dict[str, set] = {}

    for sig in window:
        for sub_sig in sig.split(_SIG_DELIMITER):
            tool_part = sub_sig.split(":", 1)[0].strip()
            args_json = sub_sig.split(":", 1)[1] if ":" in sub_sig else "{}"
            try:
                import json as _json
                args = _json.loads(args_json)
                action = args.get("action", "")
            except Exception:
                action = ""
                args_json = "{}"

            pair_key = f"{tool_part}.{action}"
            pairs.append(pair_key)
            pair_args.setdefault(pair_key, set()).add(args_json)

    if pairs:
        counter = Counter(pairs)
        most_common_name, most_common_count = counter.most_common(1)[0]
        dominance = most_common_count / len(pairs)
        unique_args = len(pair_args.get(most_common_name, set()))

        # Only trigger if: high frequency AND low argument variety (= stuck, not progressing)
        if (dominance >= _FUZZY_DOMINANCE_RATIO
                and most_common_count >= 4
                and unique_args <= most_common_count * 0.4):
            return True

    # --- Method 2: Cyclic subsequence detection (with argument matching) ---
    call_tuples: list[tuple[str, str]] = []
    for sig in window:
        for sub_sig in sig.split(_SIG_DELIMITER):
            tool_part = sub_sig.split(":", 1)[0].strip()
            args_json = sub_sig.split(":", 1)[1] if ":" in sub_sig else "{}"
            try:
                import json as _json
                action = _json.loads(args_json).get("action", "")
            except Exception:
                action = ""
            pair_name = f"{tool_part}.{action}" if action else tool_part
            call_tuples.append((pair_name, args_json))

    for cycle_len in range(2, min(5, len(call_tuples) // 3 + 1)):
        needed = cycle_len * 3
        if len(call_tuples) < needed:
            continue
        tail = call_tuples[-needed:]
        candidate = tail[:cycle_len]
        is_cycle = True
        for rep in range(1, 3):
            if tail[rep * cycle_len:(rep + 1) * cycle_len] != candidate:
                is_cycle = False
                break
        if is_cycle:
            return True

    return False


def _build_action_history_summary(action_log: list[dict]) -> str:
    """Build a compact natural-language summary of recent tool actions and their outcomes.

    'outcome' field uses three states:
      - "ok": Playwright/RPA reported no exception (DOM-level success)
      - "error": Tool raised an exception or returned Error string
      - "pending_verify": VLM screenshot was returned, awaiting model judgment
    """
    if not action_log:
        return ""
    lines = []
    for i, entry in enumerate(action_log[-_MAX_ACTION_HISTORY:], 1):
        outcome = entry.get("outcome", "ok")
        if outcome == "error":
            icon = "❌"
        elif outcome == "pending_verify":
            icon = "👁️"
        else:
            icon = "✓"
        tool = entry["tool"]
        action = entry.get("action", "")
        detail = entry.get("detail", "")[:80]
        lines.append(f"{i}. {icon} {tool}({action}) → {detail}")
    lines.append("\nDo NOT retry failed (❌) actions with identical parameters. Try a different approach.")
    lines.append("For pending (👁️) actions, check the screenshot to verify before proceeding.")
    return "\n".join(lines)

# Phase 41: Promoted from inline closure to module-level for middleware import.
def _is_error_result(r) -> bool:
    """Check if a tool execution result represents an error."""
    if isinstance(r, BaseException):
        return True
    if isinstance(r, str):
        s = str(r).strip()
        if s.startswith("Error:"):
            return True
        # Phase 33: Diagnostic screenshots embed error context in ANCHORS text
        if "⚠️ ACTION FAILED:" in s:
            return True
    return False


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        memory_window: int = 50,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        language: str = "zh",
    ):
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        # Phase 21E: Read embedding model path from config
        from nanobot.config.loader import get_config
        _cfg = get_config()
        _emb_model = _cfg.agents.defaults.embedding_model or None
        self.context = ContextBuilder(
            workspace, language=language, provider=provider, model=model,
            embedding_model=_emb_model,
        )
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            agent_loop_ref=self,
        )
        
        coord_cfg = getattr(_cfg.agents, 'coordinator', None)
        self.coordinator_manager = CoordinatorManager(
            workspace=workspace,
            bus=bus,
            provider=provider,
            enabled=getattr(coord_cfg, 'enabled', False) if coord_cfg else False,
            max_workers=getattr(coord_cfg, 'max_workers', 4) if coord_cfg else 4,
            sandbox_root=getattr(coord_cfg, 'sandbox_root', "workspace/workers") if coord_cfg else "workspace/workers",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            brave_api_key=brave_api_key
        )
        
        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._dynamic_tool_names: list[str] = []  # Track plugin tools for /reload
        self._config = None  # Cached Config instance
        from collections import OrderedDict
        self._vlm_provider_cache: OrderedDict[str, LLMProvider] = OrderedDict()  # DESIGN-5: cache VLM providers
        _VLM_CACHE_MAX = 4  # Phase 31 Retro: bound cache to prevent slow leak

        # Task Tracker - 任务状态追踪 (用于 /tasks 命令)
        self.task_tracker = TaskTracker(workspace)
        from nanobot.agent.task_tracker import set_active_tracker
        set_active_tracker(self.task_tracker)

        # Knowledge Workflow - 知识库工作流引擎
        self.knowledge_workflow = KnowledgeWorkflow(
            provider=provider,
            model=self.model,
            workspace=workspace,
            vector_memory=getattr(self.context, 'vector_memory', None),
        )

        self.memory_manager = MemoryManager(
            workspace=workspace,
            provider=provider,
            model=self.model,
            memory_window=self.memory_window,
            vector_memory=getattr(self.context, 'vector_memory', None)
        )
        self.command_handler = CommandHandler(
            workspace=workspace,
            task_tracker=self.task_tracker
        )
        self.state_handler = StateHandler(self)

        # Register tools AFTER all dependencies (knowledge_workflow, etc.) are initialized
        from nanobot.agent.tool_setup import setup_all_tools
        setup_all_tools(self)

        # D2: Cached instances for KnowledgeGraph (lazy-init)
        self._knowledge_graph = None

        # Phase 31: Verification Layer (lazy-init after config is available)
        self._verification: VerificationLayer | None = None



    def _get_knowledge_graph(self):
        """D2: Lazy-cached KnowledgeGraph (avoids disk I/O per message)."""
        if self._knowledge_graph is None:
            try:
                from nanobot.agent.knowledge_graph import KnowledgeGraph
                self._knowledge_graph = KnowledgeGraph(self.workspace, vector_memory=getattr(self.context, 'vector_memory', None))
            except Exception:
                pass
        return self._knowledge_graph

    def _get_approval_store(self):
        """Lazy-cached ApprovalStore for Smart HITL."""
        if not hasattr(self, '_approval_store'):
            self._approval_store = None
        if self._approval_store is None:
            try:
                from nanobot.agent.hitl_store import ApprovalStore
                self._approval_store = ApprovalStore(self.workspace)
            except Exception:
                pass
        return self._approval_store

    def _get_verification(self) -> VerificationLayer:
        """Phase 31: Lazy-cached VerificationLayer."""
        if self._verification is None:
            config = self._get_config()
            self._verification = VerificationLayer(
                config=config.agents.verification,
                provider=self.provider,
                model=self.model,
                knowledge_workflow=self.knowledge_workflow,
            )
        return self._verification
    
    def _get_config(self):
        """Get cached Config instance (I1: uses process-level singleton)."""
        if self._config is None:
            from nanobot.config.loader import get_config
            self._config = get_config()
        return self._config
    

    
    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or not self._mcp_servers:
            return
        self._mcp_connected = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        self._mcp_stack = AsyncExitStack()
        await self._mcp_stack.__aenter__()
        await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)

    # Names of tools that need channel/chat_id routing context set per message
    _CONTEXTUAL_TOOLS = ("message", "spawn", "cron", "draw_image", "coordinator")

    def _set_tool_context(self, channel: str, chat_id: str, tool_registry_override: ToolRegistry | None = None) -> None:
        """Update context for all tools that support routing info (duck-typed)."""
        current_tools = tool_registry_override or self.tools
        for name in self._CONTEXTUAL_TOOLS:
            tool = current_tools.get(name)
            if tool and hasattr(tool, "set_context"):
                tool.set_context(channel, chat_id)

    # Phase 37: Tools whose failures warrant a full post-mortem trace
    _HIGH_COMPLEXITY_TOOLS = {"browser", "rpa", "browser_use_worker", "exec"}

    async def _extract_trace_postmortem(
        self,
        request_text: str,
        tool_calls_with_args: list[dict],
        action_log: list[dict],
        last_error: str,
        break_reason: str = "circuit_breaker",
    ) -> None:
        """Phase 37: Extract a structured post-mortem from a failed complex task.

        Replaces the P29-5 1-line experience with an LLM-driven analysis
        that captures root cause, failed strategy, and recommended fix.
        Result is stored in the existing Experience Bank — zero new data
        structures or retrieval systems.

        Called as fire-and-forget from circuit breaker, fuzzy loop, and
        L14 duplicate detection break points.
        """
        config = self._get_config()
        if not getattr(config.agents.verification, 'trace_archive_enabled', True):
            return
        if not getattr(getattr(config.agents, 'memory_features', None), 'experience_enabled', True):
            return
        if not self.knowledge_workflow or not self.knowledge_workflow.knowledge_store:
            return

        # Only trace high-complexity tool failures
        tools_in_chain = {tc.get("tool", "") for tc in tool_calls_with_args}
        if not tools_in_chain & self._HIGH_COMPLEXITY_TOOLS:
            # Fallback to simple 1-line experience for non-complex failures
            failed_tool = tool_calls_with_args[-1].get("tool", "unknown") if tool_calls_with_args else "unknown"
            self.knowledge_workflow.knowledge_store.add_experience(
                context_trigger=f"Tool error: {failed_tool}",
                tactical_prompt=f"Tool '{failed_tool}' repeatedly failed ({break_reason}): {last_error[:200]}. Verify parameters or try alternative approach.",
                action_type="error_recovery",
            )
            return

        # Build compact failure summary (input ≤ 2000 chars)
        chain_summary = []
        for i, tc in enumerate(tool_calls_with_args[-8:], 1):
            outcome = "❌" if any(
                e.get("tool") == tc.get("tool") and e.get("outcome") == "error"
                for e in action_log
            ) else "✓"
            args_brief = json.dumps(tc.get("args", {}), ensure_ascii=False)[:120]
            chain_summary.append(f"{i}. {outcome} {tc.get('tool', '?')}({args_brief})")

        prompt = (
            f"An AI agent attempted this task and FAILED ({break_reason}):\n"
            f"Task: {request_text[:200]}\n\n"
            f"Tool chain (last {len(chain_summary)} steps):\n" + "\n".join(chain_summary) + "\n\n"
            f"Final error: {last_error[:300]}\n\n"
            f"Generate a POST-MORTEM analysis. Return ONLY valid JSON:\n"
            '{\n'
            '  "root_cause": "Why did the task fail? (1 sentence)",\n'
            '  "failed_approach": "What strategy was tried and failed? (1 sentence)",\n'
            '  "recommended_fix": "Concrete alternative approach for next attempt (2-3 sentences)"\n'
            '}'
        )

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a failure analysis expert. Respond ONLY in strict JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=300,
            )
            text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            import json_repair
            result = json_repair.loads(text)

            if isinstance(result, dict) and "root_cause" in result:
                tactical = (
                    f"TRACE POST-MORTEM ({break_reason}):\n"
                    f"Root cause: {result.get('root_cause', '')}\n"
                    f"Failed approach: {result.get('failed_approach', '')}\n"
                    f"Recommended: {result.get('recommended_fix', '')}"
                )
                self.knowledge_workflow.knowledge_store.add_experience(
                    context_trigger=request_text[:80],
                    tactical_prompt=tactical[:800],  # Hard cap within injection budget
                    action_type="trace_postmortem",
                )
                logger.info(f"Phase 37: Post-mortem extracted for '{request_text[:50]}' ({break_reason})")
            else:
                logger.warning(f"Phase 37: Invalid post-mortem JSON: {text[:100]}")
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Phase 37: Post-mortem extraction failed: {e}")

        # Developer-only: dump raw trace for offline debugging
        try:
            from nanobot.agent.trace_archive import TraceArchive
            archive = TraceArchive(self.workspace)
            archive.dump_debug_trace(
                request_text=request_text,
                tool_calls_with_args=tool_calls_with_args,
                action_log=action_log,
                final_content=last_error,
            )
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.debug(f"Phase 37: Debug trace dump failed (non-critical): {e}")


    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        channel: str | None = None,
        chat_id: str | None = None,
        injection_used: int = 0,
        target_model_override: str | None = None,
        tool_registry_override: ToolRegistry | None = None,
        session_key: str | None = None,
        is_headless: bool = False,
    ) -> LoopResult:
        """
        Run the agent iteration loop.

        Args:
            initial_messages: Starting messages for the LLM conversation.
            channel: Current communication channel (e.g., feishu, telegram).
            chat_id: Current chat or user ID.

        Returns:
            Strongly typed LoopResult representation of the iteration output.
        """
        # Phase 64: Unified provenance base invariant
        # All tracking and provenance validation occurs strictly via the middleware stack context rules.
        return await self._run_agent_loop_v2(
            initial_messages, channel, chat_id,
            injection_used, target_model_override,
            tool_registry_override=tool_registry_override,
            session_key=session_key,
            is_headless=is_headless,
        )

    # ── Phase 41: Middleware-based agent loop helpers ──────────────

    def _get_middleware_pipeline(self):
        """Phase 41: Lazy-init the middleware pipeline."""
        if not hasattr(self, '_pipeline') or self._pipeline is None:
            from nanobot.agent.middleware.pipeline import MiddlewarePipeline
            from nanobot.agent.middleware.metrics import MetricsMiddleware
            from nanobot.agent.middleware.circuit_breaker import CircuitBreakerMiddleware
            from nanobot.agent.middleware.action_history import ActionHistoryMiddleware
            from nanobot.agent.middleware.verification_mw import VerificationMiddleware
            from nanobot.agent.middleware.hitl import HITLMiddleware
            from nanobot.agent.middleware.crash_recovery import CrashRecoveryMiddleware
            from nanobot.agent.middleware.flood_guard import FloodGuardMiddleware
            from nanobot.agent.middleware.tool_executor import ToolExecutor
            self._pipeline = MiddlewarePipeline(
                middlewares=[
                    MetricsMiddleware(),              # Outermost: timing
                    CircuitBreakerMiddleware(self),    # Failure detection
                    ActionHistoryMiddleware(),         # Browser/RPA history
                    VerificationMiddleware(self),      # L1 rules
                    HITLMiddleware(self),              # Approval gate
                    CrashRecoveryMiddleware(self),     # WAL checkpoint (innermost)
                    FloodGuardMiddleware(),            # Post-only: message floods
                ],
                executor=ToolExecutor(self),
            )
        return self._pipeline

    async def _call_llm_for_turn(
        self,
        messages: list[dict],
        channel: str | None,
        chat_id: str | None,
        target_model_override: str | None,
        loop_injection_used: int,
        tool_registry_override: ToolRegistry | None = None,
    ):
        """Phase 41: Extract the LLM call logic (VLM routing + streaming) from _run_agent_loop.

        Returns:
            LLMResponse or None (on timeout).
        """
        config = self._get_config()

        # Phase 42C: Decoupled target model and VLM routing logic to ModelRouter
        target_model, provider_for_turn = ModelRouter.determine_target_model(
            messages=messages,
            default_model=self.model,
            default_provider=self.provider,
            config=config,
            vlm_provider_cache=self._vlm_provider_cache,
            target_model_override=target_model_override,
        )

        has_image = any(
            isinstance(m.get("content"), list) and any(b.get("type") == "image_url" for b in m["content"])
            for m in messages[-3:]
        )
        if has_image:
            from nanobot.utils.trace_context import add_route_tag, RoutingTag
            add_route_tag(RoutingTag.VLM_ROUTE)

        # Streaming config
        _streaming_enabled = getattr(
            getattr(config.agents, 'streaming', None), 'enabled', False
        )

        try:
            with metrics.timer("llm_call"):
                if _streaming_enabled and channel and chat_id:
                    response = await asyncio.wait_for(
                        self._stream_llm_call(
                            provider_for_turn, messages, target_model,
                            channel, chat_id, tool_registry_override,
                        ),
                        timeout=_LLM_CALL_TIMEOUT,
                    )
                else:
                    response = await asyncio.wait_for(
                        provider_for_turn.chat(
                            messages=messages,
                            tools=(tool_registry_override or self.tools).get_definitions(),
                            model=target_model,
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                        ),
                        timeout=_LLM_CALL_TIMEOUT,
                    )
        except asyncio.TimeoutError:
            logger.error(f"LLM call timed out after {_LLM_CALL_TIMEOUT}s (model={target_model})")
            return None

        return response

    async def _run_agent_loop_v2(
        self,
        initial_messages: list[dict],
        channel: str | None = None,
        chat_id: str | None = None,
        injection_used: int = 0,
        target_model_override: str | None = None,
        tool_registry_override: ToolRegistry | None = None,
        session_key: str | None = None,
        is_headless: bool = False,
    ) -> LoopResult:
        """Phase 41: Middleware-based agent loop.

        This is the v2 replacement for _run_agent_loop that uses the onion
        middleware pipeline for cross-cutting concerns. The while loop and
        LLM call/nudge logic remain here; only tool-related concerns
        (metrics, circuit breaker, L1/L3, HITL, WAL, action history,
        flood guard) are delegated to middlewares.
        """
        from nanobot.agent.middleware.base import TurnContext, TurnAction
        from nanobot.agent.i18n import msg as i18n_msg

        messages = list(initial_messages)
        iteration = 0
        final_content = None
        action_reason = None
        _exit_kind = "failure"
        tools_used: list[str] = []
        tool_calls_with_args: list[dict] = []

        # Cross-turn persistent state
        consecutive_all_exceptions = 0
        recent_call_sigs: list[str] = []
        action_log: list[dict] = []
        message_call_count = 0
        loop_injection_used = injection_used

        pipeline = self._get_middleware_pipeline()
        _milestone_summary = None

        while iteration < self.max_iterations:
            iteration += 1

            # 1. LLM call (VLM routing + streaming)
            response = await self._call_llm_for_turn(
                messages, channel, chat_id,
                target_model_override, loop_injection_used,
                tool_registry_override=tool_registry_override,
            )
            if response is None:
                final_content = f"⚠️ LLM call timed out after {_LLM_CALL_TIMEOUT}s. Please try again."
                break

            # Aggregate token usage
            if response.usage:
                metrics.record_tokens(
                    prompt=response.usage.get("prompt_tokens", 0),
                    completion=response.usage.get("completion_tokens", 0),
                    total=response.usage.get("total_tokens", 0),
                )

            # Phase 49 IFCC extraction
            _resp_content = response.content
            if _resp_content:
                import re
                _resp_content = re.sub(r'\[System:', r'[\\System:', _resp_content)
                response.content = _resp_content
            _milestone_summary = None
            if _resp_content:
                try:
                    from nanobot.config.loader import get_config as _get_cfg_l
                    if getattr(getattr(_get_cfg_l().agents, 'memory_features', None), 'ifcc_enabled', True):
                        from nanobot.agent.tag_extractor import extract_mem_content
                        _clean, _milestone_summary = extract_mem_content(_resp_content)
                        response.content = _clean
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    logger.debug(f"IFCC extraction failed: {e}")

            # 2. Non-tool response: wait-phrase / fake-completion detection
            if not response.has_tool_calls:
                final_content = response.content
                _cs = (final_content or "").lower()

                # Wait-phrase detection
                if len(_cs) < 150 and any(p in _cs for p in _WAIT_PHRASES):
                    _matched_wait = [p for p in _WAIT_PHRASES if p in _cs]
                    logger.warning(f"Wait-phrase detected {_matched_wait}: {final_content[:80]}")
                    if channel and chat_id:
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=channel, chat_id=chat_id, content=final_content
                        ))
                    messages = self.context.add_assistant_message(
                        messages, final_content, tool_calls=None,
                        reasoning_content=response.reasoning_content,
                        milestone_summary=_milestone_summary,
                    )
                    messages.append({"role": "user", "content": i18n_msg("agent_wait_nudge")})
                    continue

                # Fake-completion detection
                if len(_cs) < 150 and any(p in _cs for p in _FAKE_COMPLETION_PHRASES):
                    logger.warning(f"Fake-completion detected: {final_content[:80]}")
                    messages = self.context.add_assistant_message(
                        messages, final_content, tool_calls=None,
                        reasoning_content=response.reasoning_content,
                        milestone_summary=_milestone_summary,
                    )
                    messages.append({"role": "user", "content": i18n_msg("agent_fake_completion_nudge")})
                    continue

                _exit_kind = "success"
                break

            # 3. Has tool calls — build TurnContext and run pipeline
            tool_call_dicts = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                }
                for tc in response.tool_calls
            ]
            messages = self.context.add_assistant_message(
                messages, response.content, tool_call_dicts,
                reasoning_content=response.reasoning_content,
                milestone_summary=_milestone_summary,
            )

            # Record tool calls for return value
            for tc in response.tool_calls:
                tools_used.append(tc.name)
                tool_calls_with_args.append({"tool": tc.name, "args": tc.arguments})
                args_str = json.dumps(tc.arguments, ensure_ascii=False)
                logger.info(f"Tool call: {tc.name}({args_str[:200]})")

            ctx = TurnContext(
                messages=messages,
                iteration=iteration,
                channel=channel,
                chat_id=chat_id,
                session_key=session_key,
                is_headless=is_headless,
                consecutive_all_exceptions=consecutive_all_exceptions,
                recent_call_sigs=recent_call_sigs,
                action_log=action_log,
                message_call_count=message_call_count,
                loop_injection_used=loop_injection_used,
            )
            ctx.tool_registry_override = tool_registry_override
            ctx.tool_calls = list(response.tool_calls)
            ctx.llm_response = response

            await pipeline.run_turn(ctx)

            # 4. Sync cross-turn state back to while-loop variables
            messages = ctx.messages
            consecutive_all_exceptions = ctx.consecutive_all_exceptions
            message_call_count = ctx.message_call_count
            # recent_call_sigs, action_log are mutable refs — auto-synced

            # 5. Decide while-loop behavior based on TurnAction
            if ctx.action == TurnAction.ABORT:
                # P5: L1 violation → continue (let LLM self-correct)
                if ctx.action_reason == "l1_violation":
                    continue
                final_content = ctx.final_content
                action_reason = ctx.action_reason
                _exit_kind = "approval_pending" if action_reason == "hitl" else "abort"
                break

            if ctx.action == TurnAction.FINISH:
                final_content = ctx.final_content
                action_reason = ctx.action_reason
                _exit_kind = "success"
                break

            # CONTINUE_TOOLS nudge
            last_tool = response.tool_calls[-1].name if response.tool_calls else ""
            if last_tool in _CONTINUE_TOOLS:
                messages.append({"role": "user", "content": i18n_msg("agent_continue_prompt")})

        # Unconditional trace dump for side-effect checking (ADR-44)
        from nanobot.utils.trace_context import get_current_trace_id
        tid = get_current_trace_id()
        if tid != "no-trace":
            try:
                from nanobot.agent.trace_archive import TraceArchive
                archive = TraceArchive(self.workspace)
                # Note: v2 action log is in context.action_log
                action_hist = ctx.action_log if 'ctx' in locals() else []
                archive.dump_tool_calls(tid, tool_calls_with_args, action_hist)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.debug(f"Failed to dump tool calls for {tid} in v2 loop: {e}")

        final_milestone = _milestone_summary
        if not final_milestone:
            for m in reversed(messages):
                if m.get("role") == "assistant" and "milestone_summary" in m:
                    final_milestone = m["milestone_summary"]
                    break

        return LoopResult(
            final_content=final_content,
            tools_used=tools_used,
            tool_calls_with_args=tool_calls_with_args,
            milestone_summary=final_milestone,
            action_reason=action_reason,
            exit_kind=_exit_kind,
        )

    # ── Phase 21E: streaming helper ──────────────────────────────

    async def _stream_llm_call(
        self,
        provider: LLMProvider,
        messages: list[dict],
        model: str,
        channel: str,
        chat_id: str,
        tool_registry_override: ToolRegistry | None = None,
    ) -> "LLMResponse":
        """Call provider.stream_chat(), publishing StreamEvents to the bus.

        Returns a fully assembled LLMResponse so the rest of the agent loop
        can proceed without changes.
        """
        from nanobot.bus.events import StreamEvent
        from nanobot.providers.base import LLMResponse

        content_parts: list[str] = []
        final_usage: dict[str, int] = {}
        final_tool_calls = []
        final_reasoning: str | None = None
        final_finish = "stop"

        async for chunk in provider.stream_chat(
            messages=messages,
            tools=(tool_registry_override or self.tools).get_definitions(),
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            # Publish text deltas for live display
            if chunk.delta:
                content_parts.append(chunk.delta)
                await self.bus.publish_stream(StreamEvent(
                    channel=channel,
                    chat_id=chat_id,
                    delta=chunk.delta,
                    done=False,
                ))

            # Final chunk carries accumulated metadata
            if chunk.finish_reason:
                final_usage = chunk.usage
                final_tool_calls = chunk.tool_calls
                final_reasoning = chunk.reasoning_content
                final_finish = chunk.finish_reason

                # Send done event
                await self.bus.publish_stream(StreamEvent(
                    channel=channel,
                    chat_id=chat_id,
                    delta="",
                    done=True,
                ))

        content = "".join(content_parts) or None
        return LLMResponse(
            content=content,
            tool_calls=final_tool_calls,
            finish_reason=final_finish,
            usage=final_usage,
            reasoning_content=final_reasoning,
        )

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")
        
        # Initialize plugin lifecycles
        for tool in self.tools._tools.values():
            try:
                await tool.setup()
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.error(f"Failed to setup tool {tool.name}: {e}", exc_info=True)
        
        # Phase 40B-1: Recover stale checkpoints from previous crash
        await self._recover_stale_checkpoints()
        
        # NOTE: idle_checker for automatic memory consolidation is disabled.
        # It was removed because auto-triggering LLM consolidation caused
        # interference with active user tasks. Memory consolidation is now
        # triggered manually by the user (reply "是/好") or via /new command.

        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(
                        self.bus.consume_inbound(),
                        timeout=1.0
                    )
                    try:
                        session_lock = self.sessions.get_session_lock(msg.session_key)
                        async with session_lock:
                            with metrics.timer("message_processing"):
                                response = await self._process_message(msg)
                            if response:
                                await self.bus.publish_outbound(response)
                    except Exception as e:
                        if isinstance(e, asyncio.CancelledError):
                            raise
                        logger.error(f"Error processing message: {e}", exc_info=True)
                        metrics.increment("message_error_count")
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="Sorry, I encountered an internal error. Please try again or contact the administrator."
                        ))
                except asyncio.TimeoutError:
                    continue
        finally:
            logger.info("Cleaning up agent resources...")
            for tool in self.tools._tools.values():
                try:
                    await tool.teardown()
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    logger.error(f"Failed to teardown tool {tool.name}: {e}", exc_info=True)
            await self.close_mcp()
    
    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
        # Gracefully shutdown the compute broker
        from nanobot.compute import shutdown_broker
        shutdown_broker(wait=False)

    async def _recover_stale_checkpoints(self) -> None:
        """Phase 40B-1: Scan for stale checkpoints from a previous crash and notify masters.

        Called once at startup. If a checkpoint file exists, it means the process
        crashed mid-tool-execution. We notify master_identities with a recovery
        summary so the user knows what was interrupted.

        We do NOT attempt to re-execute the interrupted tools — tool calls may
        have side effects (email, file writes, RPA) and the system state is uncertain.

        Delivery strategy (dual-path):
        1. Bus OutboundMessage → goes through dispatch_outbound → global subscribers → WS
        2. Direct broadcast_ws_message → bypasses bus routing entirely (dashboard guaranteed)
        Both paths are attempted at each retry interval.
        """
        config = self._get_config()
        if not getattr(getattr(config.agents, 'reliability', None), 'checkpoint_enabled', True):
            return

        try:
            stale_checkpoints = self.sessions.scan_stale_checkpoints()
            if not stale_checkpoints:
                return

            logger.info("Phase 40B: Stale checkpoints found. Initiating broadcast loop...")
            logger.warning(f"Phase 40B: Found {len(stale_checkpoints)} stale checkpoint(s) from previous crash")

            for ckpt in stale_checkpoints:
                session_key = ckpt.get("session_key", "unknown")
                tools = ckpt.get("tools", [])
                timestamp = ckpt.get("timestamp", "unknown")

                tool_names = ", ".join(t.get("name", "?") for t in tools[:5])
                recovery_msg = (
                    f"⚠️ **进程恢复通知 (Phase 40B)**\n\n"
                    f"检测到上次进程崩溃时有未完成的操作：\n"
                    f"- **会话**: `{session_key}`\n"
                    f"- **中断工具**: `{tool_names}`\n"
                    f"- **中断时间**: {timestamp}\n\n"
                    f"请检查上次任务是否需要重新执行。"
                )

                # Build broadcast target set:
                # 1. master_identities (configured admin channels)
                # 2. Original session key (the crashed session's channel)
                # 3. dashboard:direct (fallback — always reachable if UI is open)
                targets = set(config.master_identities.keys())
                if session_key != "unknown":
                    targets.add(session_key)
                # Always include dashboard as a guaranteed fallback target
                targets.add("dashboard:direct")

                async def _delayed_broadcast(tgts, msg, s_key):
                    # Wait for at least one WebSocket client to connect before broadcasting.
                    # This handles the race where the server starts before the browser reconnects.
                    _ws_connected = False
                    try:
                        from nanobot.dashboard.app import _active_websockets
                        for _poll in range(30):  # Poll up to 15s (30 × 0.5s)
                            if _active_websockets:
                                _ws_connected = True
                                logger.info(f"Phase 40B: WebSocket client detected after {_poll * 0.5:.1f}s, broadcasting recovery.")
                                break
                            await asyncio.sleep(0.5)
                        if not _ws_connected:
                            logger.warning("Phase 40B: No WebSocket clients after 15s. Broadcasting anyway.")
                    except ImportError:
                        # Dashboard not available — still broadcast to bus targets
                        await asyncio.sleep(3)

                    # Broadcast via both paths at each retry interval
                    delays = [0, 3, 5]  # First attempt immediate (after WS wait), then retries
                    for delay in delays:
                        if delay > 0:
                            await asyncio.sleep(delay)

                        # Path 1: Bus OutboundMessage (reaches channel subscribers + global WS logger)
                        for target in tgts:
                            if ":" in target:
                                t_chan, t_chat = target.split(":", 1)
                                try:
                                    await self.bus.publish_outbound(OutboundMessage(
                                        channel=t_chan, chat_id=t_chat, content=msg,
                                    ))
                                except Exception as e:
                                    if isinstance(e, asyncio.CancelledError):
                                        raise
                                    logger.error(f"Phase 40B: Path 1 bus routing failed for {target}: {e}")

                        # Path 2: Direct WebSocket push (bypasses bus routing entirely)
                        try:
                            from nanobot.dashboard.app import broadcast_ws_message
                            await broadcast_ws_message("log", {"sender": "system", "message": msg})
                            await broadcast_ws_message("notification", {"message": msg})
                        except Exception as e:
                            if isinstance(e, asyncio.CancelledError):
                                raise
                            logger.error(f"Phase 40B: Path 2 direct WS push failed: {e}")

                # Fire and forget the delayed broadcast task so we don't block agent startup
                _bg_task = asyncio.create_task(_delayed_broadcast(targets, recovery_msg, session_key))
                
                # Prevent GC from destroying the task during long verification sleeps
                if getattr(self, '_bg_tasks', None) is None:
                    self._bg_tasks = set()
                self._bg_tasks.add(_bg_task)
                _bg_task.add_done_callback(self._bg_tasks.discard)

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Phase 40B: Checkpoint recovery scan failed: {e}")
    
    async def _process_message(
        self, msg: InboundMessage, session_key: str | None = None, is_headless: bool = False
    ) -> OutboundMessage | None:
        from nanobot.utils.trace_context import (
            generate_trace_id, _trace_id_var, _route_tags_var,
            get_current_trace_id, get_route_tags, RoutingTag, add_route_tag,
        )

        # 1. 解析 Subagent 回调携带的 parent trace
        parent_trace_id = (msg.metadata or {}).get("trace_id")

        # 2. 生成本次请求的新 trace
        new_trace = generate_trace_id()
        t_token = _trace_id_var.set(new_trace)
        r_token = _route_tags_var.set(frozenset())

        if parent_trace_id:
            logger.info(f"Subagent callback from parent trace={parent_trace_id}")
            add_route_tag(RoutingTag.SUBAGENT_CALLBACK)

        try:
            out_msg = await self._core_process_message(msg, session_key, is_headless)

            # 3. 统一出站打标 — 所有 return 路径在此一次性覆盖，零遗漏
            if out_msg is not None:
                if out_msg.metadata is None:
                    out_msg.metadata = {}
                out_msg.metadata["trace_id"] = new_trace
                tags = get_route_tags()
                if tags:
                    out_msg.metadata["route_tags"] = sorted(tags)
                if parent_trace_id:
                    out_msg.metadata["parent_trace_id"] = parent_trace_id

            return out_msg

        finally:
            # 4. 强制重置 — 防止协程取消后 ContextVar 悬挂（内存泄漏）
            _trace_id_var.reset(t_token)
            _route_tags_var.reset(r_token)

    async def _core_process_message(self, msg: InboundMessage, session_key: str | None = None, is_headless: bool = False) -> OutboundMessage | None:
        """
        Process a single inbound message.

        Workflow:
        1. Check if awaiting user reply on knowledge match (pending_knowledge)
        2. Check if awaiting user confirmation to save (pending_save)
        3. Handle slash commands (/new, /help)
        4. Extract task key → match knowledge base → ask user or LLM execute
        5. After LLM execution with tools, prompt user to save

        Args:
            msg: The inbound message to process.
            session_key: Override session key (used by process_direct).

        Returns:
            The response message, or None if no response needed.
        """
        from nanobot.agent.i18n import msg as i18n_msg

        # System messages route back via chat_id ("channel:chat_id")
        if msg.channel == "system":
            return await self.state_handler.handle_system_message(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)
        kw = self.knowledge_workflow
        user_input = msg.content.strip()

        # ── Implicit feedback: infer previous task outcome ──
        if session.last_task_key:
            if kw.is_negative_feedback(user_input):
                kw.record_outcome(session.last_task_key, success=False)
                logger.info(f"Implicit feedback: negative for '{session.last_task_key}'")
                
                from nanobot.agent.commands import _safe_create_task


                # P29-1: Auto-generate Directive Signal (Actionable tactical rule)
                _safe_create_task(
                    kw.extract_and_save_directive(session, user_input),
                    name="directive_extraction"
                )

            else:
                kw.record_outcome(session.last_task_key, success=True)
                # P1: silently update steps_detail with last tool calls
                if session.last_tool_calls:
                    kw.silent_update_steps(session.last_task_key, session.last_tool_calls)
                logger.info(f"Implicit feedback: positive for '{session.last_task_key}'")
            session.last_task_key = None
            session.last_tool_calls = None
            session.mark_metadata_dirty()

        # ── Intercept Remote HITL Approval ──
        content_lower = user_input.lower()
        if content_lower.startswith(("approve ", "reject ", "always ", "1 ", "2 ", "3 ")):
            parts = user_input.split()
            if len(parts) == 2:
                short_id = parts[1].upper()
                target_session_key = self.sessions.get_approval_session(short_id)
                if target_session_key:
                    resolved_key = self.sessions.resolve_key(f"{msg.channel}:{msg.chat_id}")
                    if resolved_key.startswith("master:") or resolved_key.startswith("dashboard:"):
                        target_session = self.sessions.get_or_create(target_session_key)
                        if target_session.pending_approval_task:
                            self.sessions.remove_approval(short_id)
                            # Execute on the target session but return the result to THIS admin's channel
                            if response := await self.state_handler.handle_pending_approval(target_session, msg, parts[0]):
                                response.content = f"*[任务发起端: {target_session_key}]*\n\n{response.content}"
                                return response

        # ── Step 0: Awaiting Smart HITL Approval (Local to session) ──
        if session.pending_approval_task:
            if response := await self.state_handler.handle_pending_approval(session, msg, user_input):
                # Always remove mapped short_id on any local action
                short_id = session.pending_approval_task.get("short_id") if isinstance(session.pending_approval_task, dict) else None
                if short_id:
                    self.sessions.remove_approval(short_id)
                return response

        # ── Step 1: Awaiting user reply to knowledge match ──
        if session.pending_knowledge:
            if response := await self.state_handler.handle_pending_knowledge(session, msg, user_input):
                return response

        # ── Step 2: Awaiting user confirmation to save ──
        if session.pending_save:
            if response := await self.state_handler.handle_pending_save(session, msg, user_input):
                return response

        # ── Step 2.5: Awaiting user confirmation to upgrade skill ──
        if session.pending_upgrade:
            if response := await self.state_handler.handle_pending_upgrade(session, msg, user_input):
                return response

        # ── Step 3: Slash commands ──
        cmd = msg.content.strip().lower()
        if cmd.startswith("/"):
            response = await self.command_handler.dispatch_command(cmd, msg, session, kw, self)
            if response:
                return response

        # ── Phase 42C: Intent Classification ──
        intent = IntentClassifier.detect_intent(user_input)
        is_chitchat = (intent == "chitchat_safe")

        # ── Step 4: Extract Key → Match Knowledge Base ──
        task_key = None
        match = None
        
        if not is_chitchat:
            try:
                history = session.get_history(max_messages=10)
                task_key = await kw.extract_key(msg.content, history=history)
                match = kw.match_knowledge(task_key)

                # Phase 46A: Fallback query expansion (only when all 3 layers miss)
                if match is None and task_key:
                    match = await kw.query_expansion_fallback(task_key)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.error(f"Knowledge workflow error (non-fatal): {e}")
                metrics.increment("knowledge_fallback_count")

        if match:
            confidence = match.get("_match_confidence", 0.0)

            # Phase 22D: Emit knowledge match event (always)
            await self.bus.publish_event(KnowledgeMatchedEvent(
                event_type="knowledge_matched",
                task_key=task_key or "",
                confidence=confidence,
                match_method=match.get("_match_method", "exact"),
            ))

            if confidence >= 1.0:
                # Exact match → ask user if they want to use or re-execute
                # L2: Clear other pending states before setting new one
                session.clear_pending()
                session.pending_knowledge = {
                    **match,
                    "_original_request": msg.content,
                    "_extracted_key": task_key,
                    "timestamp": time.time(),
                }
                session.mark_metadata_dirty()
                self.sessions.save(session)

                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=self._format_match_with_stats(kw, match),
                    metadata=msg.metadata or {},
                )
            else:
                # Partial match → auto-execute with few-shot adaptation
                logger.info(
                    f"Partial match (confidence={confidence:.2f}), "
                    f"auto-executing with few-shot reference from '{match.get('key', '')}'"
                )

                # Send brief notification (non-blocking) so user knows
                # a knowledge reference is being used
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=i18n_msg(
                        "knowledge_auto_adapt",
                        key=match.get("key", ""),
                        score=f"{confidence:.2f}",
                    ),
                ))

                # Adapt knowledge into few-shot prompt and execute
                history = session.get_history(max_messages=10)
                few_shot = await kw.adapt_knowledge(
                    match=match, current_request=msg.content, history=history
                )
                return await self._execute_with_llm(
                    session, msg, extracted_key=task_key,
                    few_shot_context=few_shot, intent=intent,
                    session_key=session_key, is_headless=is_headless
                )

        # ── Step 5: No match → LLM execution ──
        return await self._execute_with_llm(session, msg, extracted_key=task_key, intent=intent, session_key=session_key, is_headless=is_headless)

    def _snip_history(
        self,
        messages: list[dict],
        context_window: int | None = None,
    ) -> list[dict]:
        """基于 Token 估算的动态历史裁剪。
        
        使用 litellm.token_counter 做跨模型估算。
        对含 image_url 的消息附加启发式视觉 Token 权重。
        """
        if not context_window:
            # 回退: 用 max_tokens * 4 作为 context_window 估算
            context_window = self.max_tokens * 4
        
        # Phase 40A schema default snip buffer is 1024
        budget = context_window - self.max_tokens - _INJECTION_BUDGET - 1024
        if budget <= 0:
            return messages
        
        try:
            import litellm
            
            def _count_tokens(msgs: list[dict]) -> int:
                total = 0
                for m in msgs:
                    content = m.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if block.get("type") == "image_url":
                                total += 1024
                    try:
                        total += litellm.token_counter(model=self.model, messages=[m])
                    except Exception:
                        total += len(str(m.get("content", ""))) // 4  # fallback 估算
                return total
            
            # 从最旧消息开始渐进丢弃，确保始终从 user 消息开始
            system_msgs = [m for m in messages if m.get("role") == "system"]
            non_system = [m for m in messages if m.get("role") != "system"]
            
            original_non_system_len = len(non_system)
            
            while non_system and _count_tokens(system_msgs + non_system) > budget:
                # 丢弃最旧的消息，定位到下一个合法 user-turn 边界
                non_system = non_system[1:]
                # 确保不以 tool/assistant 消息开头
                while non_system and non_system[0].get("role") != "user":
                    non_system = non_system[1:]
            
            if len(non_system) < original_non_system_len:
                # ADR-64: Inject degradation structural notice to preserve zero-trust guarantees
                evicted_turns = original_non_system_len - len(non_system)
                system_msgs.append({
                    "role": "system",
                    "content": f"[Context Integrity Notice]\n⚠️ {evicted_turns} recent turn(s) were physically snipped to satisfy the rigid {budget} token window limit. The user context below is incomplete."
                })
            
            return system_msgs + non_system
        except Exception as e:
            logger.debug(f"Token-budget snip failed ({e}), using raw messages")
            return messages

    async def _execute_with_llm(
        self,
        session: Session,
        msg: InboundMessage,
        original_request: str | None = None,
        extracted_key: str | None = None,
        few_shot_context: str = "",
        intent: str = "task",
        session_key: str | None = None,
        is_headless: bool = False,
    ) -> OutboundMessage:
        """Execute a user request via the LLM agent loop.

        Args:
            session: Current session.
            msg: The inbound message (used for channel/chat_id routing).
            original_request: If re-executing, the original request text.
            extracted_key: Pre-extracted task key (from knowledge workflow).
            few_shot_context: Optional few-shot reference prompt to inject.

        Returns:
            OutboundMessage with the agent's response.
        """
        from nanobot.agent.i18n import msg as i18n_msg

        request_text = original_request or msg.content

        self._set_tool_context(msg.channel, msg.chat_id)

        target_model_override = None
        if intent == "chitchat_safe":
            from nanobot.utils.trace_context import add_route_tag, RoutingTag
            add_route_tag(RoutingTag.CHITCHAT_FAST)
            config = self._get_config()
            if hasattr(config.agents, 'fast_model') and config.agents.fast_model.enabled and config.agents.fast_model.model:
                target_model_override = config.agents.fast_model.model
        
        # P13/Phase 34: Async query rewriting and anchor extraction
        search_query = request_text
        query_anchors = []
        if intent != "chitchat_safe":
            try:
                if hasattr(self.context, 'vector_memory') and hasattr(self.context.vector_memory, 'rewrite_query_with_anchors'):
                    history = session.get_history(max_messages=10)
                    search_query, query_anchors = await self.context.vector_memory.rewrite_query_with_anchors(request_text, history)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.debug(f"Query rewriting skipped: {e}")
        else:
            logger.info("Chitchat intent detected, skipping query rewrite and overriding target model.")

        # Phase 39: Async decouple contextual data pre-fetching
        pre_fetched_rag = None
        pre_fetched_kg = None
        if intent != "chitchat_safe":
            try:
                import asyncio
                kg_instance = self._get_knowledge_graph()
                
                def _sync_fetch_both():
                    r = None
                    k = None
                    try:
                        r = self.context.vector_memory.search(search_query, top_k=3)
                    except Exception as _e:
                        if isinstance(_e, asyncio.CancelledError):
                            raise
                        pass
                    try:
                        if kg_instance:
                            from nanobot.config.loader import get_config
                            if get_config().agents.memory_features.knowledge_graph_enabled:
                                k = kg_instance.get_entity_context(
                                    search_query,
                                    prefetch_rag=r,
                                    anchors=query_anchors
                                )
                    except Exception as _e:
                        if isinstance(_e, asyncio.CancelledError):
                            raise
                        pass
                    return r, k
                    
                loop = asyncio.get_running_loop()
                pre_fetched_rag, pre_fetched_kg = await loop.run_in_executor(None, _sync_fetch_both)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.debug(f"Async pre-fetch skipped: {e}")
        else:
            pre_fetched_rag = []
            pre_fetched_kg = ""

        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=request_text,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            search_query=search_query,
            query_anchors=query_anchors,
            evicted_context=session.evicted_context,
            knowledge_graph=self._get_knowledge_graph(),  # D2: cached instance
            pre_fetched_rag=pre_fetched_rag,
            pre_fetched_kg=pre_fetched_kg,
        )

        # Phase 40A-3: Dynamic token-budget trimming
        config = self._get_config()
        ctx_window = getattr(getattr(config.agents, 'context', None), 'context_window_tokens', None)
        initial_messages = self._snip_history(initial_messages, context_window=ctx_window)

        # Inject few-shot reference into system prompt if available
        if few_shot_context and initial_messages and initial_messages[0].get("role") == "system":
            initial_messages[0]["content"] += (
                f"\n\n---\n"
                f"⚡ KNOWLEDGE BASE DIRECTIVE (follow this approach):\n"
                f"{few_shot_context}"
            )

        # Phase 31 L0: Consolidated context enrichment via VerificationLayer
        config = self._get_config()
        verification = self._get_verification()
        injection_used = verification.enrich_context(
            initial_messages,
            request_text,
            session.message_count_since_consolidation,
            memory_features=config.agents.memory_features,
        )

        memory_hint = self.command_handler.detect_memory_intent(request_text)
        if memory_hint and initial_messages and initial_messages[0].get("role") == "system":
            if injection_used + len(memory_hint) <= _INJECTION_BUDGET:
                initial_messages[0]["content"] += f"\n\n{memory_hint}"
                injection_used += len(memory_hint)

        result = await self._run_agent_loop(
            initial_messages, channel=msg.channel, chat_id=msg.chat_id,
            injection_used=injection_used,
            target_model_override=target_model_override,
            session_key=session_key,
            is_headless=is_headless,
        )
        final_content = result.final_content
        tools_used = result.tools_used
        tool_calls_with_args = result.tool_calls_with_args
        final_milestone = result.milestone_summary
        action_reason = result.action_reason

        # Phase 31 L3: Post-reflection & knowledge extraction (fire-and-forget)
        if tools_used and verification.config.l3_enabled:
            from nanobot.agent.commands import _safe_create_task
            _safe_create_task(
                verification.post_reflect(
                    request_text=request_text,
                    final_content=final_content or "",
                    tools_used=tools_used,
                    tool_calls_with_args=tool_calls_with_args,
                    session=session,
                    exit_kind=result.exit_kind,
                ),
                name="l3_post_reflect",
            )

        if final_content is None:
            final_content = i18n_msg("no_response")
        else:
            # Strip <think> tags from reasoning models (DeepSeek-R1, etc.)
            # Must happen BEFORE _FAIL_INDICATORS check to avoid false positives
            # from reasoning content containing words like 无法, 失败, etc.
            from nanobot.utils.think_strip import strip_think_tags
            final_content = strip_think_tags(final_content)

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")

        session.add_message("user", request_text, media=msg.media if getattr(msg, 'media', None) else None)
        session.add_message(
            "assistant", final_content,
            tools_used=tools_used if tools_used else None,
            milestone_summary=final_milestone,
        )
        session.message_count_since_consolidation += 2  # user + assistant

        # P1-B: Auto-consolidation every 20 messages (only when no pending states)
        if (session.message_count_since_consolidation >= 20
                and not session.pending_knowledge
                and not session.pending_save
                and not session.pending_upgrade):
            _consolidation_count = session.message_count_since_consolidation
            logger.info(f"Auto-consolidation triggered (count={_consolidation_count})")
            session.message_count_since_consolidation = 0
            from nanobot.agent.commands import _safe_create_task
            session_snapshot = session.to_snapshot()
            _safe_create_task(self.memory_manager.consolidate_memory_from_snapshot(session_snapshot, session_manager=self.sessions), name="auto_consolidation")
            # Phase 22D: Emit memory consolidation event
            await self.bus.publish_event(MemoryConsolidatedEvent(
                event_type="memory_consolidated",
                session_key=session.key,
                messages_consolidated=_consolidation_count,
            ))

        # After LLM execution with tool calls → prompt user to save
        # But ONLY if the workflow appears to have succeeded
        save_prompt = ""
        if tool_calls_with_args and not session.pending_approval_task:
            if result.exit_kind == "success":
                _workflow_succeeded = True
            else:
                _workflow_succeeded = False

            if _workflow_succeeded:
                task_key = extracted_key or request_text[:50]
                session.last_task_key = task_key
                # L2: Clear other pending states before setting pending_save
                session.clear_pending()
                session.pending_save = {
                    "key": task_key,
                    "steps": tool_calls_with_args,
                    "tools_used": tools_used,
                    "user_request": request_text,
                    "result_summary": final_content[:500],
                    "timestamp": time.time(),
                }
                # P1: store tool calls for silent steps update on next implicit feedback
                session.last_tool_calls = tool_calls_with_args
                session.mark_metadata_dirty()
                save_prompt = self.knowledge_workflow.format_save_prompt()
            else:
                logger.info("Skipping save prompt: workflow appears to have failed")

        self.sessions.save(session)
        
        media_attachments = []
        if getattr(session, 'metadata', {}).get('voice_response_enabled'):
            try:
                from nanobot.providers.tts import EdgeTTSProvider
                tts = EdgeTTSProvider()
                text_to_speak = final_content[:500] if final_content else "No response"
                # Strip markdown/images before speaking
                import re
                clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', text_to_speak)
                clean_text = re.sub(r'```.*?```', '代码块', clean_text, flags=re.DOTALL)
                audio_path = await tts.synthesize(clean_text)
                if audio_path:
                    media_attachments.append(str(audio_path))
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.error(f"Failed to generate TTS: {e}")

        outbound_content = final_content
        if not outbound_content.strip() and not tool_calls_with_args:
            outbound_content = "*(系统上下文记忆已更新)*"
            
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=outbound_content + save_prompt,
            media=media_attachments,
            metadata=msg.metadata or {},
        )
    
    
    


    def _format_match_with_stats(self, kw: KnowledgeWorkflow, match: dict) -> str:
        """Format knowledge match prompt with success rate stats if available."""
        from nanobot.agent.i18n import msg as i18n_msg

        stats = kw.get_match_stats(match)
        use_count = stats.get("use_count", 0)
        score = match.get("_match_confidence", 0.0)
        if use_count > 0:
            return i18n_msg(
                "knowledge_match_with_stats",
                key=match.get("key", ""),
                rate=str(stats["rate"]),
                count=str(use_count),
                score=f"{score:.2f}",
            )
        return kw.format_match_prompt(match)



    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        return_trace: bool = False,
        is_headless: bool = False,
    ) -> str | tuple[str, str | None]:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier (overrides channel:chat_id for session lookup).
            channel: Source channel (for tool context routing).
            chat_id: Source chat ID (for tool context routing).
            return_trace: If true, returns a tuple of (content, trace_id).
        
        Returns:
            The agent's response, or a tuple of (response, trace_id).
        """
        await self._connect_mcp()
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        response = await self._process_message(msg, session_key=session_key, is_headless=is_headless)
        out_content = response.content if response else ""
        
        # ADR-64: Routine garbage collection self-sustains GC invariants implicitly during automatic background operations
        if session_key == "heartbeat" and hasattr(self, "task_tracker") and hasattr(self, "vector_store"):
            self.task_tracker.clear_old_tasks(vector_memory=self.vector_store)
        
        if return_trace:
            trace_id = response.metadata.get("trace_id") if response and response.metadata else None
            return out_content, trace_id
            
        return out_content
