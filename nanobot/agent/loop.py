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

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage, ToolExecutedEvent, KnowledgeMatchedEvent, MemoryConsolidatedEvent
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry

from nanobot.agent.subagent import SubagentManager
from nanobot.agent.task_tracker import TaskTracker, TaskStatus
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.personalization import MemoryDistiller
from nanobot.session.manager import Session, SessionManager
from nanobot.agent.commands import CommandHandler
from nanobot.agent.memory_manager import MemoryManager
from nanobot.agent.state_handler import StateHandler
from nanobot.agent.verification import VerificationLayer
from nanobot.utils.metrics import metrics



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
# L3: Removed 'no results' — too generic, causes false negatives in legitimate responses
# DESIGN-4: Use specific action-failure phrases to reduce false positives in analytical responses
_FAIL_INDICATORS = [
    "无法完成此任务", "无法执行此操作", "不能执行此操作",
    "not found", "no emails found",
    "执行失败", "操作失败", "执行出错", "运行失败", "获取失败",
]


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
        )
        
        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._dynamic_tool_names: list[str] = []  # Track plugin tools for /reload
        self._config = None  # Cached Config instance
        self._vlm_provider_cache: dict[str, LLMProvider] = {}  # DESIGN-5: cache VLM providers
        _VLM_CACHE_MAX = 4  # Phase 31 Retro: bound cache to prevent slow leak

        # Task Tracker - 任务状态追踪 (用于 /tasks 命令)
        self.task_tracker = TaskTracker(workspace)

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

        # D2: Cached instances for ReflectionStore and KnowledgeGraph (lazy-init)
        self._reflection_store = None
        self._knowledge_graph = None

        # Phase 31: Verification Layer (lazy-init after config is available)
        self._verification: VerificationLayer | None = None

    def _get_reflection_store(self):
        """D2: Lazy-cached ReflectionStore (avoids disk I/O per message)."""
        if self._reflection_store is None:
            try:
                from nanobot.agent.reflection import ReflectionStore
                self._reflection_store = ReflectionStore(self.workspace)
            except Exception:
                pass
        return self._reflection_store

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
                reflection_store=self._get_reflection_store(),
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
    _CONTEXTUAL_TOOLS = ("message", "spawn", "cron")

    def _set_tool_context(self, channel: str, chat_id: str) -> None:
        """Update context for all tools that support routing info (duck-typed)."""
        for name in self._CONTEXTUAL_TOOLS:
            tool = self.tools.get(name)
            if tool and hasattr(tool, "set_context"):
                tool.set_context(channel, chat_id)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        channel: str | None = None,
        chat_id: str | None = None,
        injection_used: int = 0,
    ) -> tuple[str | None, list[str], list[dict]]:
        """
        Run the agent iteration loop.

        Args:
            initial_messages: Starting messages for the LLM conversation.
            channel: Current communication channel (e.g., feishu, telegram).
            chat_id: Current chat or user ID.

        Returns:
            Tuple of (final_content, list_of_tools_used, tool_calls_with_args).
        """
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        tool_calls_with_args: list[dict] = []
        message_call_count = 0  # Track message() calls to prevent floods
        consecutive_all_exceptions = 0  # B1: circuit breaker counter
        # L14: Track recent tool call signatures to detect infinite loops
        _recent_call_sigs: list[str] = []
        _DUPLICATE_THRESHOLD = 3  # Break after N identical consecutive calls
        # Phase 33: Action log for browser/rpa actions (history awareness)
        _action_log: list[dict] = []
        # Phase 33: Track injection budget consumed by enrich_context (passed from caller)
        _loop_injection_used = injection_used

        while iteration < self.max_iterations:
            iteration += 1

            # Phase 33: Inject action history into system prompt before LLM call
            if _action_log and any(e["tool"] in ("browser", "rpa") for e in _action_log):
                history_summary = _build_action_history_summary(_action_log)
                if history_summary and messages and messages[0].get("role") == "system":
                    sys_content = messages[0]["content"]
                    # Remove stale history from previous iteration (idempotent)
                    sentinel_idx = sys_content.find(_ACTION_HISTORY_SENTINEL)
                    if sentinel_idx != -1:
                        sys_content = sys_content[:sentinel_idx]
                    # Budget check: must fit within BOTH per-injection cap AND global remaining budget
                    history_len = len(history_summary) + len(_ACTION_HISTORY_SENTINEL)
                    remaining_budget = _INJECTION_BUDGET - _loop_injection_used
                    if history_len <= _ACTION_HISTORY_MAX and history_len <= remaining_budget:
                        messages[0]["content"] = sys_content + _ACTION_HISTORY_SENTINEL + history_summary
                        _loop_injection_used += history_len

            # Determine if this turn requires the VLM
            # Phase 33: Only check the most recent N messages for images.
            # This prevents the agent from being permanently downgraded to the
            # weaker VLM model after old screenshots scroll out of relevance.
            # Phase 35 fix: Reduced from 4 to 2 to prevent post-action verify
            # screenshots from permanently trapping the agent in the weaker VLM.
            # With window=2, after the VLM processes one screenshot and responds,
            # the next turn routes back to the main model (stronger reasoning).
            _VLM_RECENCY_WINDOW = 2
            target_model = self.model
            config = self._get_config()
            
            provider_for_turn = self.provider

            if config.agents.vlm.enabled and config.agents.vlm.model:
                has_image = False
                recent_msgs = messages[-_VLM_RECENCY_WINDOW:] if len(messages) > _VLM_RECENCY_WINDOW else messages
                for msg in recent_msgs:
                    if isinstance(msg.get("content"), list):
                        for block in msg["content"]:
                            if block.get("type") == "image_url":
                                has_image = True
                                break
                    if has_image:
                        break
                
                if has_image:
                    target_model = config.agents.vlm.model
                    logger.debug(f"Image detected in recent {_VLM_RECENCY_WINDOW} messages. Routing to VLM: {target_model}")
                    
                    # B4: Graceful fallback if VLM provider config is missing
                    p_conf = config.get_provider(target_model)
                    if not p_conf:
                        logger.warning(f"VLM provider config missing for {target_model}, falling back to default model")
                        target_model = self.model
                    else:
                        # DESIGN-5: Cache VLM provider to avoid re-creating per turn
                        if target_model not in self._vlm_provider_cache:
                            # Phase 31 Retro: evict oldest if cache full
                            if len(self._vlm_provider_cache) >= 4:
                                oldest_key = next(iter(self._vlm_provider_cache))
                                del self._vlm_provider_cache[oldest_key]
                            from nanobot.providers.factory import ProviderFactory
                            self._vlm_provider_cache[target_model] = ProviderFactory.get_provider(target_model, config)
                        provider_for_turn = self._vlm_provider_cache[target_model]
                else:
                    logger.debug(f"No images in recent {_VLM_RECENCY_WINDOW} messages. Using main model: {target_model}")

            # Phase 21E: Check streaming config
            _streaming_enabled = getattr(
                getattr(config.agents, 'streaming', None), 'enabled', False
            )

            try:
              with metrics.timer("llm_call"):
                if _streaming_enabled and channel and chat_id:
                    # Streaming path: forward tokens in real-time
                    response = await asyncio.wait_for(
                        self._stream_llm_call(
                            provider_for_turn, messages, target_model,
                            channel, chat_id,
                        ),
                        timeout=_LLM_CALL_TIMEOUT,
                    )
                else:
                    response = await asyncio.wait_for(
                        provider_for_turn.chat(
                            messages=messages,
                            tools=self.tools.get_definitions(),
                            model=target_model,
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                        ),
                        timeout=_LLM_CALL_TIMEOUT,
                    )
            except asyncio.TimeoutError:
                logger.error(f"LLM call timed out after {_LLM_CALL_TIMEOUT}s (model={target_model})")
                final_content = f"⚠️ LLM call timed out after {_LLM_CALL_TIMEOUT}s. Please try again."
                break

            # Aggregate token usage
            if response.usage:
                metrics.record_tokens(
                    prompt=response.usage.get("prompt_tokens", 0),
                    completion=response.usage.get("completion_tokens", 0),
                    total=response.usage.get("total_tokens", 0),
                )

            if response.has_tool_calls:
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
                )

                # Log and record all tool calls
                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    tool_calls_with_args.append({
                        "tool": tool_call.name,
                        "args": tool_call.arguments
                    })
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")

                # Phase 31 L1: Rigid rule interception (pre-execution)
                verification = self._get_verification()
                rule_result = verification.check_rules(response.tool_calls)
                if not rule_result.passed:
                    # Inject violation feedback as a synthetic tool result
                    # so the LLM can self-correct instead of hard-failing
                    logger.warning(f"L1: Blocking {len(rule_result.violations)} violation(s)")
                    for tool_call in response.tool_calls:
                        messages = self.context.add_tool_result(
                            messages, tool_call.id, tool_call.name,
                            f"Error: Action blocked by verification layer. {rule_result.rewrite_hint}"
                        )
                    continue

                # Phase 32: Smart HITL Approval Check
                hitl_suspended = False
                for tc in response.tool_calls:
                    tool_impl = self.tools.get(tc.name)
                    if tool_impl and hasattr(tool_impl, "get_risk_tier"):
                        from nanobot.agent.tools.base import RiskTier
                        tier = tool_impl.get_risk_tier(tc.arguments)
                        if tier.value >= RiskTier.MUTATE_EXTERNAL.value:
                            approval_store = self._get_approval_store()
                            if approval_store and not approval_store.is_approved(tc.name, tc.arguments):
                                logger.info(f"HITL: Suspending loop for {tc.name} approval")
                                if channel and chat_id:
                                    session_key = self.sessions.resolve_key(f"{channel}:{chat_id}")
                                    session = self.sessions._cache.get(session_key)
                                    if session:
                                        session.pending_approval_task = {
                                            "tool": tc.name,
                                            "arguments": tc.arguments,
                                            "id": tc.id
                                        }
                                        self.sessions.save(session)
                                        hitl_msg = (
                                            f"⚠️ **Action Required!**\n\n"
                                            f"The agent is attempting a High-Risk operation:\n"
                                            f"- **Tool**: `{tc.name}`\n"
                                            f"- **Args**: `{json.dumps(tc.arguments, ensure_ascii=False)}`\n\n"
                                            f"Please reply with:\n"
                                            f"1. `Approve` (allow this time)\n"
                                            f"2. `Always` (allow this and future identical actions)\n"
                                            f"3. `Reject` (block the action)"
                                        )
                                        from nanobot.bus.events import OutboundMessage
                                        await self.bus.publish_outbound(OutboundMessage(
                                            channel=channel,
                                            chat_id=chat_id,
                                            content=hitl_msg
                                        ))
                                        hitl_suspended = True
                                        final_content = "Execution suspended pending human approval."
                                        break
                if hitl_suspended:
                    break

                # Execute tool calls concurrently via asyncio.gather
                async def _exec_tool(tc):
                    _start = time.monotonic()
                    with metrics.timer("tool_execution"):
                        res = await self.tools.execute(tc.name, tc.arguments)
                    _elapsed_ms = (time.monotonic() - _start) * 1000
                    metrics.increment("tool_executions_count")
                    logger.debug(f"Tool {tc.name} completed in {_elapsed_ms / 1000:.1f}s")
                    # Phase 22D: Emit domain event for observability
                    _is_err = isinstance(res, BaseException) or (isinstance(res, str) and res.startswith("Error: "))
                    await self.bus.publish_event(ToolExecutedEvent(
                        event_type="tool_executed",
                        tool_name=tc.name,
                        duration_ms=_elapsed_ms,
                        success=not _is_err,
                        error=str(res)[:200] if _is_err else None,
                    ))
                    return res

                results = await asyncio.gather(
                    *[_exec_tool(tc) for tc in response.tool_calls],
                    return_exceptions=True,
                )

                # Phase 33: Action log tracking (for browser/rpa/browser_use tools)
                for tool_call, result in zip(response.tool_calls, results):
                    if tool_call.name in ("browser", "rpa", "browser_use_worker"):
                        _is_err_al = isinstance(result, BaseException) or (
                            isinstance(result, str) and (
                                result.startswith("Error:") or "⚠️ ACTION FAILED:" in result
                            )
                        )
                        _is_verify = isinstance(result, str) and "__IMAGE__:" in result and not _is_err_al
                        _action_log.append({
                            "tool": tool_call.name,
                            "action": tool_call.arguments.get("action", ""),
                            "outcome": "error" if _is_err_al else ("pending_verify" if _is_verify else "ok"),
                            "detail": str(result)[:80] if _is_err_al else tool_call.arguments.get("selector", "")[:80],
                        })
                        if len(_action_log) > _MAX_ACTION_HISTORY:
                            del _action_log[:-_MAX_ACTION_HISTORY]

                # B1: circuit breaker — count consecutive all-exception turns
                def _is_error_result(r):
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
                    
                error_count = sum(1 for r in results if _is_error_result(r))
                if error_count == len(results) and len(results) > 0:
                    consecutive_all_exceptions += 1
                    logger.warning(f"All {len(results)} tools failed (streak: {consecutive_all_exceptions})")
                    # Phase 35 fix: Uniform threshold of 3 for all tools.
                    # Browser no longer gets extra retries (5→3) because:
                    # 1. Graduated fallback hints (JS→mouse_click→RPA) already guide strategy changes at 3 failures
                    # 2. With weaker VLM making decisions, more retries just wastes time
                    _cb_threshold = 3
                    if consecutive_all_exceptions >= _cb_threshold:
                        logger.error(f"Circuit breaker: {consecutive_all_exceptions} consecutive all-exception turns (threshold={_cb_threshold}). Breaking agent loop.")
                        
                        # P29-5: Error -> Auto Experience. Extract a tactical hint from repeated failures.
                        if getattr(getattr(config.agents, 'memory_features', None), 'experience_enabled', True):
                            try:
                                failed_tc = response.tool_calls[0] if response.tool_calls else None
                                failed_res = results[0] if results else "Unknown error"
                                if failed_tc and hasattr(self, "knowledge_workflow") and self.knowledge_workflow.knowledge_store:
                                    exp_prompt = f"Executing tool '{failed_tc.name}' repeatedly failed with: {failed_res}. When using this tool, verify parameters or check system state."
                                    self.knowledge_workflow.knowledge_store.add_experience(
                                        context_trigger=f"Tool error: {failed_tc.name}",
                                        tactical_prompt=exp_prompt,
                                        action_type="error_recovery"
                                    )
                                    logger.info(f"P29-5: Saved auto-experience for {failed_tc.name} failure.")
                            except Exception as e:
                                logger.error(f"Failed to save auto-experience: {e}")

                        for tool_call, result in zip(response.tool_calls, results):
                            if isinstance(result, BaseException):
                                result = f"Error: {result}"
                            messages = self.context.add_tool_result(
                                messages, tool_call.id, tool_call.name, result
                            )
                        final_content = "⚠️ Multiple consecutive tool failures detected. Please check your request and try again."
                        break
                else:
                    consecutive_all_exceptions = 0

                # Add results to messages in original order
                for tool_call, result in zip(response.tool_calls, results):
                    if isinstance(result, BaseException):
                        logger.error(f"Tool {tool_call.name} raised: {result}")
                        result = f"Error: {result}"
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )

                # Phase 32 L3: Anti-pattern audit (fire-and-forget, log-only)
                try:
                    verification.audit_antipatterns(tool_calls_with_args)
                except Exception as e:
                    logger.debug(f"L3 anti-pattern audit error (non-critical): {e}")
                
                # Track message() calls and guard against floods
                for tc in response.tool_calls:
                    if tc.name == "message":
                        message_call_count += 1
                if message_call_count >= _MAX_MESSAGE_CALLS:
                    logger.warning(f"Message flood guard: {message_call_count} message() calls, breaking loop")
                    break

                # L14: Duplicate tool call detection — prevent infinite loops
                # Build signature for this iteration's tool calls
                # Phase 33: Use _SIG_DELIMITER instead of "|" for fuzzy detection compatibility
                _iter_sig = _SIG_DELIMITER.join(
                    f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
                    for tc in response.tool_calls
                )
                _recent_call_sigs.append(_iter_sig)
                # Phase 33: Keep enough for both exact-match and fuzzy detection
                _SIG_RETENTION = max(_DUPLICATE_THRESHOLD, _FUZZY_LOOP_WINDOW)
                if len(_recent_call_sigs) > _SIG_RETENTION:
                    del _recent_call_sigs[:-_SIG_RETENTION]
                # Check if last N are ALL identical (exact-match L14)
                if (len(_recent_call_sigs) >= _DUPLICATE_THRESHOLD
                        and len(set(_recent_call_sigs[-_DUPLICATE_THRESHOLD:])) == 1):
                    logger.warning(
                        f"Duplicate tool call detected ({_DUPLICATE_THRESHOLD}x): "
                        f"{_iter_sig[:120]}... Breaking loop."
                    )
                    final_content = (
                        "⚠️ I appear to be stuck in a loop calling the same tool repeatedly. "
                        "Please rephrase your request or try a different approach."
                    )
                    break

                # Phase 33: Fuzzy loop detection (semantic loops with similar but not identical calls)
                if _detect_fuzzy_loop(_recent_call_sigs):
                    logger.warning("Fuzzy loop detected: tool-action pattern repeating. Breaking loop.")
                    final_content = (
                        "⚠️ I appear to be stuck repeating similar actions without progress. "
                        "Please check if the page loaded correctly, or try a different approach."
                    )
                    break

                # 根据最后执行的工具决定是否提示继续
                last_tool = response.tool_calls[-1].name if response.tool_calls else ""
                
                if last_tool in _CONTINUE_TOOLS:
                    messages.append({"role": "user", "content": i18n_msg("agent_continue_prompt")})
            else:
                final_content = response.content
                _fc_preview = (final_content or "")[:120]
                logger.debug(f"LLM returned non-tool response: {_fc_preview}")
                
                # Check for premature termination by reasoning models (sending a "wait" message or "fake completion" but no tools)
                _content_str = (final_content or "").lower()
                
                # If it contains wait phrases
                if len(_content_str) < 500 and any(p in _content_str for p in _WAIT_PHRASES):
                    _matched_wait = [p for p in _WAIT_PHRASES if p in _content_str]
                    logger.warning(f"Wait-phrase detected {_matched_wait}, pushing for tool usage: {final_content[:80]}")
                    
                    # Forward this intermediate status to the user
                    if channel and chat_id:
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=channel, chat_id=chat_id, content=final_content
                        ))
                    
                    # Add to context
                    messages = self.context.add_assistant_message(
                        messages, final_content, tool_calls=None, reasoning_content=response.reasoning_content
                    )
                    
                    # Force it to call tools
                    messages.append({
                        "role": "user",
                        "content": i18n_msg("agent_wait_nudge")
                    })
                    continue
                
                # If it contains fake completion phrases
                if len(_content_str) < 500 and any(p in _content_str for p in _FAKE_COMPLETION_PHRASES):
                    _matched_fake = [p for p in _FAKE_COMPLETION_PHRASES if p in _content_str]
                    logger.warning(f"Fake-completion detected {_matched_fake}, pushing for tool usage: {final_content[:80]}")
                    
                    # Add to context
                    messages = self.context.add_assistant_message(
                        messages, final_content, tool_calls=None, reasoning_content=response.reasoning_content
                    )
                    
                    # Force it to call tools
                    messages.append({
                        "role": "user",
                        "content": i18n_msg("agent_fake_completion_nudge")
                    })
                    continue
                
                break

        return final_content, tools_used, tool_calls_with_args

    # ── Phase 21E: streaming helper ──────────────────────────────

    async def _stream_llm_call(
        self,
        provider: LLMProvider,
        messages: list[dict],
        model: str,
        channel: str,
        chat_id: str,
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
            tools=self.tools.get_definitions(),
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
                logger.error(f"Failed to setup tool {tool.name}: {e}", exc_info=True)
        
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
                        with metrics.timer("message_processing"):
                            response = await self._process_message(msg)
                        if response:
                            await self.bus.publish_outbound(response)
                    except Exception as e:
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
    
    async def _process_message(self, msg: InboundMessage, session_key: str | None = None) -> OutboundMessage | None:
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

                # P1: Auto-generate metacognitive reflection memory on failure
                try:
                    reflection_store = self._get_reflection_store()
                    if reflection_store:
                        _safe_create_task(
                            reflection_store.generate_reflection(self.provider, self.model, session, user_input),
                            name="reflection_generation",
                        )
                except Exception as e:
                    logger.error(f"Failed to trigger reflection generation: {e}")
                
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

        # ── Step 0: Awaiting Smart HITL Approval ──
        if session.pending_approval_task:
            if response := await self.state_handler.handle_pending_approval(session, msg, user_input):
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

        # ── Step 4: Extract Key → Match Knowledge Base ──
        try:
            history = session.get_history(max_messages=10)
            task_key = await kw.extract_key(msg.content, history=history)
            match = kw.match_knowledge(task_key)
        except Exception as e:
            logger.error(f"Knowledge workflow error (non-fatal): {e}")
            metrics.increment("knowledge_fallback_count")
            task_key = None
            match = None

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
                    few_shot_context=few_shot,
                )

        # ── Step 5: No match → LLM execution ──
        return await self._execute_with_llm(session, msg, extracted_key=task_key)

    async def _execute_with_llm(
        self,
        session: Session,
        msg: InboundMessage,
        original_request: str | None = None,
        extracted_key: str | None = None,
        few_shot_context: str = "",
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

        # P13: Async query rewriting for coreference resolution (moved from context.py)
        search_query = request_text
        try:
            if hasattr(self.context, 'vector_memory') and hasattr(self.context.vector_memory, 'rewrite_query'):
                history = session.get_history(max_messages=10)
                search_query = await self.context.vector_memory.rewrite_query(request_text, history)
        except Exception as e:
            logger.debug(f"Query rewriting skipped: {e}")

        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=request_text,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            search_query=search_query,
            evicted_context=session.evicted_context,
            knowledge_graph=self._get_knowledge_graph(),  # D2: cached instance
        )

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

        final_content, tools_used, tool_calls_with_args = await self._run_agent_loop(
            initial_messages, channel=msg.channel, chat_id=msg.chat_id,
            injection_used=injection_used,
        )

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

        session.add_message("user", request_text)
        session.add_message(
            "assistant", final_content,
            tools_used=tools_used if tools_used else None,
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
            _safe_create_task(self.memory_manager.consolidate_memory(session), name="auto_consolidation")
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
            _content_lower = (final_content or "").lower()

            # Phase 31 Retro: skip _FAIL_INDICATORS when response is
            # analytical (tool results contain the keywords as data,
            # not as agent failure). Heuristic: if analysis tools were
            # used and no tool errors occurred, treat as quoting.
            _ANALYSIS_TOOLS = {"attachment_analyzer", "web_fetch", "web_search"}
            _is_analytical = bool(set(tools_used) & _ANALYSIS_TOOLS)
            _had_tool_errors = any(
                isinstance(tc.get("args"), str) and tc["args"].startswith("Error:")
                for tc in tool_calls_with_args
            )
            if _is_analytical and not _had_tool_errors:
                _workflow_succeeded = True
            else:
                _workflow_succeeded = not any(
                    ind in _content_lower for ind in _FAIL_INDICATORS
                )

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
                }
                # P1: store tool calls for silent steps update on next implicit feedback
                session.last_tool_calls = tool_calls_with_args
                session.mark_metadata_dirty()
                save_prompt = self.knowledge_workflow.format_save_prompt()
            else:
                logger.info("Skipping save prompt: workflow appears to have failed")

        self.sessions.save(session)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content + save_prompt,
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
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier (overrides channel:chat_id for session lookup).
            channel: Source channel (for tool context routing).
            chat_id: Source chat ID (for tool context routing).
        
        Returns:
            The agent's response.
        """
        await self._connect_mcp()
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg, session_key=session_key)
        return response.content if response else ""
