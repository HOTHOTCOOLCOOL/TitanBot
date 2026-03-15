"""Agent loop: the core processing engine."""

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
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.save_skill import SaveSkillTool
from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool
from nanobot.agent.tools.task_memory import TaskMemoryTool
from nanobot.agent.tools.memory_search_tool import MemorySearchTool
from nanobot.agent.tools.screen_capture import ScreenCaptureTool
from nanobot.agent.tools.rpa_executor import RPAExecutorTool
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.task_tracker import TaskTracker, TaskStatus
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.personalization import MemoryDistiller
from nanobot.session.manager import Session, SessionManager
from nanobot.plugin_loader import scan_plugins, unload_plugins


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

        self.context = ContextBuilder(workspace, language=language)
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
        self._register_default_tools()
        self._register_dynamic_tools()
        
        # Task Tracker - 任务状态追踪 (用于 /tasks 命令)
        self.task_tracker = TaskTracker(workspace)

        # Knowledge Workflow - 知识库工作流引擎
        self.knowledge_workflow = KnowledgeWorkflow(
            provider=provider,
            model=self.model,
            workspace=workspace,
        )
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
        
        # Save skill tool (for saving workflows as reusable skills)
        self.tools.register(SaveSkillTool(self.workspace))
        
        # Outlook tools (for email processing)
        self.tools.register(OutlookTool())
        self.tools.register(AttachmentAnalyzerTool())
        
        # Task knowledge tool
        self.tools.register(TaskMemoryTool(self.workspace))
        
        # Memory search tool (RAG)
        memory_search_tool = MemorySearchTool()
        if hasattr(self.context, 'vector_memory'):
            memory_search_tool.set_vector_memory(self.context.vector_memory)
        self.tools.register(memory_search_tool)
        
        # Vision tools
        self.tools.register(ScreenCaptureTool(self.workspace))
        self.tools.register(RPAExecutorTool())
    
    def _register_dynamic_tools(self) -> None:
        """Scan the plugins directory and register discovered tools.
        
        Tools that conflict with already-registered built-in tools are skipped.
        Previously loaded dynamic tools are unregistered first (for /reload).
        """
        # Unload any previously loaded plugins
        if self._dynamic_tool_names:
            unload_plugins(self.tools, self._dynamic_tool_names)
            self._dynamic_tool_names.clear()
        
        plugins_dir = self.workspace / "nanobot" / "plugins"
        if not plugins_dir.exists():
            # Try relative to the package itself
            plugins_dir = Path(__file__).parent.parent / "plugins"
        
        discovered = scan_plugins(plugins_dir)
        
        for tool in discovered:
            if self.tools.has(tool.name):
                logger.warning(
                    f"Plugin '{tool.name}' conflicts with built-in tool, skipping"
                )
                continue
            self.tools.register(tool)
            self._dynamic_tool_names.append(tool.name)
        
        if self._dynamic_tool_names:
            logger.info(
                f"Dynamic tools registered: {', '.join(self._dynamic_tool_names)}"
            )
    
    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or not self._mcp_servers:
            return
        self._mcp_connected = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        self._mcp_stack = AsyncExitStack()
        await self._mcp_stack.__aenter__()
        await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)

    def _set_tool_context(self, channel: str, chat_id: str) -> None:
        """Update context for all tools that need routing info."""
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.set_context(channel, chat_id)

        if spawn_tool := self.tools.get("spawn"):
            if isinstance(spawn_tool, SpawnTool):
                spawn_tool.set_context(channel, chat_id)

        if cron_tool := self.tools.get("cron"):
            if isinstance(cron_tool, CronTool):
                cron_tool.set_context(channel, chat_id)

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

        while iteration < self.max_iterations:
            iteration += 1

            # Determine if this turn requires the VLM
            target_model = self.model
            from nanobot.config.schema import Config
            config = Config()
            
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
                    
                    # If the current provider is CustomProvider (which doesn't route) 
                    # or if the target model provider differs, try to use LiteLLMProvider.
                    p_conf = config.get_provider(target_model)
                    from nanobot.providers.litellm_provider import LiteLLMProvider
                    provider_name = config.get_provider_name(target_model)
                    provider_for_turn = LiteLLMProvider(
                        api_key=p_conf.api_key if p_conf else None,
                        api_base=config.get_api_base(target_model),
                        default_model=target_model,
                        extra_headers=p_conf.extra_headers if p_conf else None,
                        provider_name=provider_name
                    )

            response = await provider_for_turn.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=target_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
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

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    # 保存工具名称和参数
                    tool_calls_with_args.append({
                        "tool": tool_call.name,
                        "args": tool_call.arguments
                    })
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                
                # 根据最后执行的工具决定是否提示继续
                last_tool = response.tool_calls[-1].name if response.tool_calls else ""
                
                # 需要继续的工具：outlook, attachment_analyzer, message
                continue_tools = {"outlook", "attachment_analyzer", "message"}
                
                if last_tool in continue_tools:
                    messages.append({"role": "user", "content": "继续执行！如果需要提取附件、分析内容、发邮件，立即调用工具。不要只返回文字，立即行动！"})
            else:
                final_content = response.content
                
                # Check for premature termination by reasoning models (sending a "wait" message or "fake completion" but no tools)
                _content_str = (final_content or "").lower()
                _wait_phrases = [
                    "稍等", "稍候", "马上", "现在开始", "这就开始", "正在为", 
                    "working on it", "wait a", "just a sec", "let me start"
                ]
                _fake_completion_phrases = [
                    "已发送", "已完成", "发送完毕", "处理完成", "task completed", "have sent the email"
                ]
                
                # If it contains wait phrases
                if len(_content_str) < 500 and any(p in _content_str for p in _wait_phrases):
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
                        "content": "你前一句只回复了确认的文字。这会导致动作中断！请你**立即调用实际工具**（如 exec, read_file 等）往下推进任务进程！！！"
                    })
                    continue
                
                # If it contains fake completion phrases
                if len(_content_str) < 500 and any(p in _content_str for p in _fake_completion_phrases):
                    logger.warning(f"LLM returned fake completion message without tools, pushing for tool usage: {final_content[:50]}")
                    
                    # Add to context
                    messages = self.context.add_assistant_message(
                        messages, final_content, tool_calls=None, reasoning_content=response.reasoning_content
                    )
                    
                    # Force it to call tools
                    messages.append({
                        "role": "user",
                        "content": "你声称已经完成了任务或发送了邮件，但实际上系统检测到你并没有调用任何工具！这是你的幻觉。请立刻调用正确的工具执行实际操作！"
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
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
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
            return await self._process_system_message(msg)

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
            else:
                kw.record_outcome(session.last_task_key, success=True)
                logger.info(f"Implicit feedback: positive for '{session.last_task_key}'")
            session.last_task_key = None

        # ── Step 1: Awaiting user reply to knowledge match ──
        if session.pending_knowledge:
            if kw.is_use_command(user_input):
                # User chose to use knowledge base result
                logger.info(f"Session {session.key}: User chose to use knowledge base")
                match = session.pending_knowledge
                session.pending_knowledge = None

                result_content = kw.get_knowledge_result(match)

                session.add_message("user", msg.content)
                session.add_message("assistant", result_content)
                self.sessions.save(session)

                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id, content=result_content
                )

            elif kw.is_redo_command(user_input):
                # User chose to re-execute
                logger.info(f"Session {session.key}: User chose to re-execute")
                original_request = session.pending_knowledge.get("_original_request", "")
                few_shot = kw.format_few_shot_prompt(session.pending_knowledge)
                extracted_key = session.pending_knowledge.get("_extracted_key")
                session.pending_knowledge = None

                if original_request:
                    return await self._execute_with_llm(
                        session, msg, original_request=original_request,
                        extracted_key=extracted_key,
                        few_shot_context=few_shot,
                    )
                else:
                    session.pending_knowledge = None
                    self.sessions.save(session)
                    return OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content=i18n_msg("re_execute_no_previous"),
                    )
            # else: not a use/redo command → clear pending and treat as new message
            session.pending_knowledge = None

        # ── Step 2: Awaiting user confirmation to save ──
        if session.pending_save:
            if kw.is_save_confirm(user_input):
                logger.info(f"Session {session.key}: User confirmed save to knowledge base")
                pending = session.pending_save
                session.pending_save = None

                await kw.save_to_knowledge(
                    key=pending.get("key", "unknown"),
                    steps=pending.get("steps", []),
                    user_request=pending.get("user_request", ""),
                    result_summary=pending.get("result_summary", ""),
                )

                # Check if this task qualifies for skill upgrade
                save_key = pending.get("key", "")
                if save_key and kw.should_suggest_skill_upgrade(save_key):
                    match = kw.knowledge_store.find_task(save_key) if kw.knowledge_store else None
                    if match:
                        session.pending_upgrade = {
                            "key": save_key,
                            "match": match,
                        }
                        self.sessions.save(session)
                        stats = kw.get_match_stats(match)
                        return OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content=kw.format_save_confirmed() + kw.format_skill_upgrade_prompt(
                                match, lang=None
                            ),
                        )

                self.sessions.save(session)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=kw.format_save_confirmed(),
                )
            # else: user didn't confirm → clear pending_save, continue
            session.pending_save = None

        # ── Step 2.5: Awaiting user confirmation to upgrade skill ──
        if session.pending_upgrade:
            if kw.is_upgrade_command(user_input):
                logger.info(f"Session {session.key}: User confirmed skill upgrade")
                pending = session.pending_upgrade
                session.pending_upgrade = None
                self.sessions.save(session)

                # Auto-create skill via SaveSkillTool
                try:
                    match = pending.get("match", {})
                    skill_tool = self.tools.get("save_skill")
                    if skill_tool:
                        steps = match.get("steps", [])
                        tool_names = []
                        for s in steps:
                            if isinstance(s, dict):
                                tool_names.append(s.get("tool", "unknown"))
                            else:
                                tool_names.append(str(s))
                        await skill_tool.execute(
                            name=pending.get("key", "auto_skill"),
                            description=match.get("description", pending.get("key", "")),
                            steps=json.dumps(steps, ensure_ascii=False),
                        )
                        return OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content=i18n_msg("skill_upgrade_confirmed"),
                        )
                except Exception as e:
                    logger.error(f"Skill upgrade failed: {e}")
                    return OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content=i18n_msg("processing_error", error=str(e)),
                    )
            # else: user didn't confirm upgrade → clear and continue
            session.pending_upgrade = None

        # ── Step 3: Slash commands ──
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            messages_to_archive = session.messages.copy()
            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)

            async def _consolidate_and_cleanup():
                temp_session = Session(key=session.key)
                temp_session.messages = messages_to_archive
                await self._consolidate_memory(temp_session, archive_all=True)

            asyncio.create_task(_consolidate_and_cleanup())
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=i18n_msg("new_session"),
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=i18n_msg("help_text"),
            )
        if cmd == "/tasks":
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=self._format_tasks_list(),
            )
        if cmd == "/reload":
            self._register_dynamic_tools()
            if self._dynamic_tool_names:
                tools_list = ", ".join(self._dynamic_tool_names)
                content = f"🔄 Plugins reloaded. Active dynamic tools: {tools_list}"
            else:
                content = "🔄 Plugins reloaded. No dynamic tools found in plugins directory."
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=content,
            )

        # ── Step 4: Extract Key → Match Knowledge Base ──
        try:
            task_key = await kw.extract_key(msg.content)
            match = kw.match_knowledge(task_key)
        except Exception as e:
            logger.error(f"Knowledge workflow error (non-fatal): {e}")
            task_key = None
            match = None

        if match:
            # Found a match — ask user if they want to use or re-execute
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
        session,
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
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=request_text,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        # Inject few-shot reference into system prompt if available
        if few_shot_context and initial_messages and initial_messages[0].get("role") == "system":
            initial_messages[0]["content"] += f"\n\n{few_shot_context}"

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
            asyncio.create_task(self._consolidate_memory(session))

        # After LLM execution with tool calls → prompt user to save
        # But ONLY if the workflow appears to have succeeded
        save_prompt = ""
        if tool_calls_with_args:
            _fail_indicators = [
                "找不到", "没有找到", "未找到", "没找到",
                "无法找到", "无法获取", "无法访问",
                "error:", "not found", "no emails found",
                "no results", "无法", "失败", "出错",
                "sorry", "抱歉",
            ]
            _content_lower = (final_content or "").lower()
            _workflow_succeeded = not any(
                ind in _content_lower for ind in _fail_indicators
            )

            if _workflow_succeeded:
                task_key = extracted_key or request_text[:50]
                session.last_task_key = task_key
                session.pending_save = {
                    "key": task_key,
                    "steps": tool_calls_with_args,
                    "tools_used": tools_used,
                    "user_request": request_text,
                    "result_summary": final_content[:500],
                }
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
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        self._set_tool_context(origin_channel, origin_chat_id)
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        final_content, _, _ = await self._run_agent_loop(
            initial_messages, channel=origin_channel, chat_id=origin_chat_id
        )

        if final_content is None:
            final_content = "Background task completed."
        
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md.

        Args:
            archive_all: If True, clear all messages and reset session (for /new command).
                       If False, only write to files without modifying session.
        """
        memory = MemoryStore(self.workspace)

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(f"Memory consolidation (archive_all): {len(session.messages)} total messages archived")
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                logger.debug(f"Session {session.key}: No consolidation needed (messages={len(session.messages)}, keep={keep_count})")
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                logger.debug(f"Session {session.key}: No new messages to consolidate (last_consolidated={session.last_consolidated}, total={len(session.messages)})")
                return

            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return
            logger.info(f"Memory consolidation started: {len(session.messages)} total, {len(old_messages)} new to consolidate, {keep_count} keep")

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")
        conversation = "\n".join(lines)
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly three keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. ONLY add durable FACTS: user preferences, personal info, project context, technical decisions, tools/services used. Do NOT add one-time events or task results. If nothing new is a durable fact, return the existing content unchanged.

3. "daily_log": A brief summary of notable one-time events from the conversation (tasks completed, errors encountered, emails analyzed, etc.). One line per event. Return empty string if nothing notable.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            text = (response.content or "").strip()
            # Strip <think> tags before parsing JSON, as reasoning models will leak them
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if not text:
                logger.warning("Memory consolidation: LLM returned empty response, skipping")
                return
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            if not isinstance(result, dict):
                logger.warning(f"Memory consolidation: unexpected response type, skipping. Response: {text[:200]}")
                return

            if entry := result.get("history_entry"):
                memory.append_history(entry)
                # Auto-ingest new history entry into vector store
                if hasattr(self.context, 'vector_memory') and self.context.vector_memory:
                    self.context.vector_memory.ingest_text(entry, source="history")

            if update := result.get("memory_update"):
                if isinstance(update, dict):
                    update = __import__("json").dumps(update, ensure_ascii=False, indent=2)
                elif not isinstance(update, str):
                    update = str(update)
                if update != current_memory:
                    memory.write_long_term(update)

            if daily := result.get("daily_log"):
                if daily.strip():
                    memory.append_daily_log(daily.strip())
                    # Auto-ingest new daily log entry into vector store
                    today_str = time.strftime("%Y-%m-%d")
                    if hasattr(self.context, 'vector_memory') and self.context.vector_memory:
                        self.context.vector_memory.ingest_text(
                            daily.strip(),
                            source=f"daily_log:{today_str}",
                            metadata={"date": today_str}
                        )

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            logger.info(f"Memory consolidation done: {len(session.messages)} messages, last_consolidated={session.last_consolidated}")
            
            # Fire an asynchronous distillation to extract L1 core preferences
            # Only distill if the L2 memory actually changed 
            if update := result.get("memory_update"):
                if update != current_memory:
                    distiller = MemoryDistiller(memory, self.provider, self.model)
                    asyncio.create_task(distiller.distill_preferences())
                    
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")

    async def _execute_from_knowledge(
        self,
        msg: InboundMessage,
        knowledge_entry: dict,
        channel: str,
        chat_id: str,
    ) -> str:
        """
        从知识库条目执行任务步骤（不调用 LLM）。
        
        注意：知识库只保存了步骤名称，没有保存参数。
        如果参数缺失，需要让用户选择重新执行。
        
        Args:
            msg: 原始消息
            knowledge_entry: 知识库条目，包含 steps 和 tools_used
            channel: 频道
            chat_id: 聊天 ID
        
        Returns:
            执行结果
        """
        logger.info(f"Executing from knowledge: key={knowledge_entry.get('key')}")
        
        steps = knowledge_entry.get("steps", [])
        if not steps:
            return "知识库中没有执行步骤。"
        
        # 检查是否有参数
        has_params = any(step.get("args") for step in steps)
        
        if not has_params:
            # 知识库没有保存参数，无法正确执行
            logger.warning(f"Knowledge base has no parameters saved, cannot execute")
            return """⚠️ 知识库只保存了步骤，没有保存参数，无法正确执行。

建议选择「重新执行」，让 AI 根据当前情况重新处理。"""
        
        # 设置工具上下文
        self._set_tool_context(channel, chat_id)
        
        results = []
        for i, step in enumerate(steps):
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            
            if not tool_name:
                continue
            
            logger.info(f"Executing step {i+1}/{len(steps)}: {tool_name}")
            
            try:
                result = await self.tools.execute(tool_name, tool_args)
                results.append(f"[{i+1}] {tool_name}: {result[:200]}")
            except Exception as e:
                results.append(f"[{i+1}] {tool_name}: 错误 - {str(e)}")
        
        # 构造最终回复
        final_content = "从知识库执行任务：\n\n" + "\n\n".join(results)
        
        return final_content
    
    def _extract_tool_args_from_history(self, messages: list[dict]) -> dict[str, dict]:
        """
        从 session history 中提取工具调用的参数。
        
        Returns:
            Dict mapping tool_name -> {args}
        """
        tool_args_map: dict[str, dict] = {}
        
        for msg in messages:
            # 检查是否是 assistant 消息且包含 tool_calls
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        if tool_name:
                            # 解析 arguments（可能是 JSON 字符串）
                            args = func.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    args = {}
                            tool_args_map[tool_name] = args
        
        return tool_args_map
    
    def _format_tasks_list(self) -> str:
        """Format recent tasks for the /tasks command."""
        from nanobot.agent.i18n import msg as i18n_msg

        tasks = self.task_tracker.list_tasks(limit=10)
        if not tasks:
            return i18n_msg("tasks_empty")

        status_icons = {
            "completed": "✅",
            "failed": "❌",
            "running": "⏳",
            "created": "📝",
            "planning": "📝",
            "pending_review": "🔍",
            "cancelled": "⛔",
        }
        lines = [i18n_msg("tasks_header")]
        for t in tasks:
            status = t.status.value if hasattr(t.status, 'value') else str(t.status)
            icon = status_icons.get(status, "❓")
            time_str = t.created_at.strftime("%m-%d %H:%M") if t.created_at else ""
            key_display = t.key[:30] + ("..." if len(t.key) > 30 else "")
            lines.append(f"{icon} `{key_display}` — {status} ({time_str})")
        return "\n".join(lines)

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
