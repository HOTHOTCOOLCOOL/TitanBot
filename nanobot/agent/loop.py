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

from nanobot.bus.events import InboundMessage, OutboundMessage
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
from nanobot.utils.metrics import metrics



# ── Module-level constants (extracted from inline for readability) ──

# Tool names that warrant a "continue executing" nudge after their completion
_CONTINUE_TOOLS = {"outlook", "attachment_analyzer", "message"}

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
_FAIL_INDICATORS = [
    "找不到", "没有找到", "未找到", "没找到",
    "无法找到", "无法获取", "无法访问",
    "error:", "not found", "no emails found",
    "无法", "失败", "出错",
    "sorry", "抱歉",
]


# D3: Maximum characters to inject into system prompt from RAG/KG/reflections/experience/few-shot
_INJECTION_BUDGET = 8000

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

        self.context = ContextBuilder(workspace, language=language, provider=provider, model=model)
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
        from nanobot.agent.tool_setup import setup_all_tools
        setup_all_tools(self)
        
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

        # D2: Cached instances for ReflectionStore and KnowledgeGraph (lazy-init)
        self._reflection_store = None
        self._knowledge_graph = None

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
                self._knowledge_graph = KnowledgeGraph(self.workspace)
            except Exception:
                pass
        return self._knowledge_graph
    
    def _get_config(self):
        """Get cached Config instance (avoids re-parsing on every LLM iteration)."""
        if self._config is None:
            from nanobot.config.schema import Config
            self._config = Config()
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
        chat_id: str | None = None
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
        consecutive_all_exceptions = 0  # B1: circuit breaker counter

        while iteration < self.max_iterations:
            iteration += 1

            # Determine if this turn requires the VLM
            target_model = self.model
            config = self._get_config()
            
            provider_for_turn = self.provider

            if config.agents.vlm.enabled and config.agents.vlm.model:
                has_image = False
                for msg in messages:
                    if isinstance(msg.get("content"), list):
                        for block in msg["content"]:
                            if block.get("type") == "image_url":
                                has_image = True
                                break
                    if has_image:
                        break
                
                if has_image:
                    target_model = config.agents.vlm.model
                    logger.debug(f"Image detected in context. Routing to VLM: {target_model}")
                    
                    # B4: Graceful fallback if VLM provider config is missing
                    p_conf = config.get_provider(target_model)
                    if not p_conf:
                        logger.warning(f"VLM provider config missing for {target_model}, falling back to default model")
                        target_model = self.model
                    else:
                        from nanobot.providers.litellm_provider import LiteLLMProvider
                        provider_name = config.get_provider_name(target_model)
                        provider_for_turn = LiteLLMProvider(
                            api_key=p_conf.api_key,
                            api_base=config.get_api_base(target_model),
                            default_model=target_model,
                            extra_headers=p_conf.extra_headers,
                            provider_name=provider_name
                        )

            with metrics.timer("llm_call"):
                response = await provider_for_turn.chat(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=target_model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

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

                # Execute tool calls concurrently via asyncio.gather
                async def _exec_tool(tc):
                    _start = time.monotonic()
                    with metrics.timer("tool_execution"):
                        res = await self.tools.execute(tc.name, tc.arguments)
                    metrics.increment("tool_executions_count")
                    logger.debug(f"Tool {tc.name} completed in {time.monotonic() - _start:.1f}s")
                    return res

                results = await asyncio.gather(
                    *[_exec_tool(tc) for tc in response.tool_calls],
                    return_exceptions=True,
                )

                # B1: circuit breaker — count consecutive all-exception turns
                exception_count = sum(1 for r in results if isinstance(r, BaseException))
                if exception_count == len(results) and len(results) > 0:
                    consecutive_all_exceptions += 1
                    logger.warning(f"All {len(results)} tools failed (streak: {consecutive_all_exceptions})")
                    if consecutive_all_exceptions >= 3:
                        logger.error("Circuit breaker: 3 consecutive all-exception turns. Breaking agent loop.")
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
                
                # 根据最后执行的工具决定是否提示继续
                last_tool = response.tool_calls[-1].name if response.tool_calls else ""
                
                if last_tool in _CONTINUE_TOOLS:
                    messages.append({"role": "user", "content": i18n_msg("agent_continue_prompt")})
            else:
                final_content = response.content
                
                # Check for premature termination by reasoning models (sending a "wait" message or "fake completion" but no tools)
                _content_str = (final_content or "").lower()
                
                # If it contains wait phrases
                if len(_content_str) < 500 and any(p in _content_str for p in _WAIT_PHRASES):
                    logger.warning(f"LLM returned pure wait message, pushing for tool usage: {final_content[:50]}")
                    
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
                    logger.warning(f"LLM returned fake completion message without tools, pushing for tool usage: {final_content[:50]}")
                    
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

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")
        
        # NOTE: idle_checker for automatic memory consolidation is disabled.
        # It was removed because auto-triggering LLM consolidation caused
        # interference with active user tasks. Memory consolidation is now
        # triggered manually by the user (reply "是/好") or via /new command.

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
                
                # P1: Auto-generate metacognitive reflection memory on failure
                try:
                    reflection_store = self._get_reflection_store()
                    if reflection_store:
                        from nanobot.agent.commands import _safe_create_task
                        _safe_create_task(
                            reflection_store.generate_reflection(self.provider, self.model, session, user_input),
                            name="reflection_generation",
                        )
                except Exception as e:
                    logger.error(f"Failed to trigger reflection generation: {e}")

            else:
                kw.record_outcome(session.last_task_key, success=True)
                # P1: silently update steps_detail with last tool calls
                if session.last_tool_calls:
                    kw.silent_update_steps(session.last_task_key, session.last_tool_calls)
                logger.info(f"Implicit feedback: positive for '{session.last_task_key}'")
            session.last_task_key = None
            session.last_tool_calls = None

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
            # Found a match — ask user if they want to use or re-execute
            # L2: Clear other pending states before setting new one
            session.clear_pending()
            session.pending_knowledge = {
                **match,
                "_original_request": msg.content,
                "_extracted_key": task_key,
            }
            self.sessions.save(session)

            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=self._format_match_with_stats(kw, match),
                metadata=msg.metadata or {},
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
            initial_messages[0]["content"] += f"\n\n{few_shot_context}"

        # D3: Track injection budget to prevent context overflow
        injection_used = 0

        # Inject tactical experience hint from Experience Bank (Phase 12)
        # D1: gated behind memory_features.experience_enabled
        config = self._get_config()
        if (hasattr(self, "knowledge_workflow")
                and getattr(getattr(config.agents, 'memory_features', None), 'experience_enabled', True)):
            experience_hint = self.knowledge_workflow.match_experience(request_text)
            if experience_hint and initial_messages and initial_messages[0].get("role") == "system":
                hint_text = (
                    f"\n\n## 💡 Helpful Experience / Tactical Hint:\n{experience_hint}\n"
                    "Consider applying this hint if it's relevant to solving the task."
                )
                if injection_used + len(hint_text) <= _INJECTION_BUDGET:
                    initial_messages[0]["content"] += hint_text
                    injection_used += len(hint_text)

        memory_hint = self.command_handler.detect_memory_intent(request_text)
        if memory_hint and initial_messages and initial_messages[0].get("role") == "system":
            if injection_used + len(memory_hint) <= _INJECTION_BUDGET:
                initial_messages[0]["content"] += f"\n\n{memory_hint}"
                injection_used += len(memory_hint)
            
        # P1: Inject Metacognitive Reflection Memory (Negative Examples)
        # D1: gated behind memory_features.reflection_enabled
        if getattr(getattr(config.agents, 'memory_features', None), 'reflection_enabled', True):
            try:
                reflection_store = self._get_reflection_store()
                if reflection_store:
                    reflections = reflection_store.search_reflections(request_text)
                    if reflections and initial_messages and initial_messages[0].get("role") == "system":
                        reflection_text = "## ⚠️ Avoid Past Mistakes (Negative Examples)\n"
                        for r in reflections:
                            reflection_text += f"- **When**: {r.get('trigger', '')}\n"
                            reflection_text += f"  - **Mistake**: {r.get('failure_reason', '')}\n"
                            reflection_text += f"  - **Correction**: {r.get('corrective_action', '')}\n"
                        if injection_used + len(reflection_text) <= _INJECTION_BUDGET:
                            initial_messages[0]["content"] += f"\n\n{reflection_text}"
                            injection_used += len(reflection_text)
            except Exception as e:
                logger.error(f"Failed to inject reflection memory: {e}")

        final_content, tools_used, tool_calls_with_args = await self._run_agent_loop(
            initial_messages, channel=msg.channel, chat_id=msg.chat_id
        )

        if final_content is None:
            final_content = i18n_msg("no_response")

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
            logger.info(f"Auto-consolidation triggered (count={session.message_count_since_consolidation})")
            session.message_count_since_consolidation = 0
            from nanobot.agent.commands import _safe_create_task
            _safe_create_task(self.memory_manager.consolidate_memory(session), name="auto_consolidation")

        # After LLM execution with tool calls → prompt user to save
        # But ONLY if the workflow appears to have succeeded
        save_prompt = ""
        if tool_calls_with_args:
            _content_lower = (final_content or "").lower()
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
        if use_count > 0:
            return i18n_msg(
                "knowledge_match_with_stats",
                key=match.get("key", ""),
                rate=str(stats["rate"]),
                count=str(use_count),
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
