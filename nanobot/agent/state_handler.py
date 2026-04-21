"""Session state handlers for the agent loop."""

__all__ = ["StateHandler"]

import json
import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.session.manager import Session
from nanobot.agent.i18n import msg as i18n_msg

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop

class StateHandler:
    """Handles pending interactive states like knowledge confirmation."""
    def __init__(self, agent: "AgentLoop"):
        self.agent = agent

    async def handle_pending_knowledge(self, session: Session, msg: InboundMessage, user_input: str) -> OutboundMessage | None:
        pending = session.pending_knowledge
        if not pending:
            return None
        if hasattr(msg, "timestamp") and pending.get("timestamp") and msg.timestamp.timestamp() < pending.get("timestamp", 0.0):
            logger.info(f"Session {session.key}: Ignoring stale message for pending knowledge (arrived before prompt)")
            return None

        kw = self.agent.knowledge_workflow
        if kw.is_use_command(user_input):
            logger.info(f"Session {session.key}: User chose to use knowledge base")
            match = pending
            session.pending_knowledge = None
            session.mark_metadata_dirty()

            result_content = kw.get_knowledge_result(match)

            session.add_message("user", msg.content)
            session.add_message("assistant", result_content)
            self.agent.sessions.save(session)

            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=result_content
            )

        elif kw.is_redo_command(user_input):
            logger.info(f"Session {session.key}: User chose to re-execute")
            original_request = session.pending_knowledge.get("_original_request", "")
            
            history = session.get_history(max_messages=10)
            few_shot = await kw.adapt_knowledge(
                match=pending, 
                current_request=msg.content, 
                history=history
            )
            
            extracted_key = pending.get("_extracted_key")
            session.pending_knowledge = None
            session.mark_metadata_dirty()

            if original_request:
                return await self.agent._execute_with_llm(
                    session, msg, original_request=original_request,
                    extracted_key=extracted_key,
                    few_shot_context=few_shot,
                )
            else:
                self.agent.sessions.save(session)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=i18n_msg("re_execute_no_previous"),
                )
        session.pending_knowledge = None
        session.mark_metadata_dirty()
        return None

    async def handle_pending_save(self, session: Session, msg: InboundMessage, user_input: str) -> OutboundMessage | None:
        pending = session.pending_save
        if not pending:
            return None
        if hasattr(msg, "timestamp") and pending.get("timestamp") and msg.timestamp.timestamp() < pending.get("timestamp", 0.0):
            logger.info(f"Session {session.key}: Ignoring stale message for pending save (arrived before prompt)")
            return None

        kw = self.agent.knowledge_workflow
        if kw.is_save_confirm(user_input):
            logger.info(f"Session {session.key}: User confirmed save to knowledge base")
            session.pending_save = None
            session.mark_metadata_dirty()

            await kw.save_to_knowledge(
                key=pending.get("key", "unknown"),
                steps=pending.get("steps", []),
                user_request=pending.get("user_request", ""),
                result_summary=pending.get("result_summary", ""),
            )

            save_key = pending.get("key", "")
            if save_key and kw.should_suggest_skill_upgrade(save_key):
                match = kw.knowledge_store.find_task(save_key) if kw.knowledge_store else None
                if match:
                    session.pending_upgrade = {
                        "key": save_key,
                        "match": match,
                        "timestamp": time.time(),
                    }
                    session.mark_metadata_dirty()
                    self.agent.sessions.save(session)
                    return OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content=kw.format_save_confirmed() + kw.format_skill_upgrade_prompt(
                            match, lang=None
                        ),
                    )

            self.agent.sessions.save(session)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=kw.format_save_confirmed(),
            )
        session.pending_save = None
        session.mark_metadata_dirty()
        return None

    async def handle_pending_upgrade(self, session: Session, msg: InboundMessage, user_input: str) -> OutboundMessage | None:
        pending = session.pending_upgrade
        if not pending:
            return None
        if hasattr(msg, "timestamp") and pending.get("timestamp") and msg.timestamp.timestamp() < pending.get("timestamp", 0.0):
            logger.info(f"Session {session.key}: Ignoring stale message for pending upgrade (arrived before prompt)")
            return None

        kw = self.agent.knowledge_workflow
        if kw.is_upgrade_command(user_input):
            logger.info(f"Session {session.key}: User confirmed skill upgrade")
            session.pending_upgrade = None
            session.mark_metadata_dirty()
            self.agent.sessions.save(session)

            try:
                match = pending.get("match", {})
                skill_tool = self.agent.tools.get("save_skill")
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
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.error(f"Skill upgrade failed: {e}")
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=i18n_msg("processing_error", error=str(e)),
                )
        session.pending_upgrade = None
        session.mark_metadata_dirty()
        return None

    async def handle_pending_approval(self, session: Session, msg: InboundMessage, user_input: str) -> OutboundMessage | None:
        pending = session.pending_approval_task
        if not pending:
            return None
        if hasattr(msg, "timestamp") and pending.get("timestamp") and msg.timestamp.timestamp() < pending.get("timestamp", 0.0):
            logger.info(f"Session {session.key}: Ignoring stale message for pending approval (arrived before prompt)")
            return None
            
        action = user_input.strip().lower()
        tool_name = pending.get("tool")
        arguments = pending.get("arguments", {})
        tool_id = pending.get("id")
        
        session.pending_approval_task = None
        session.mark_metadata_dirty()
        self.agent.sessions.save(session)
        
        approved = False
        # Check if the user is explicitly rejecting
        explicit_reject = action in ["0", "3", "reject", "no", "n", "deny", "不", "拒绝"] or action.startswith("reject ")
        
        if action in ["1", "approve", "ok", "yes", "y", "allow", "同意", "是"] or action.startswith("approve ") or action.startswith("1 "):
            approved = True
            logger.info(f"Session {session.key}: User approved High-Risk tool {tool_name}")
        elif action in ["2", "always", "a", "总是"] or action.startswith("always ") or action.startswith("2 "):
            approved = True
            logger.info(f"Session {session.key}: User always-approved tool {tool_name}")
            auth_store = self.agent._get_approval_store()
            if auth_store:
                # 提取特定的行为动作（例如 'send_email', 'get_attachment'）
                target_action = arguments.get("action", "")
                match_context = {}
                
                # 针对不同工具提取不变的“任务锚点”作为绑定上下文
                if tool_name == "outlook" and target_action == "send_email":
                    # 绑定固定收件人（忽略会随着日期变化的 subject/body）
                    if "recipient" in arguments:
                        match_context["recipient"] = arguments["recipient"]
                    elif "to" in arguments:
                        match_context["to"] = arguments["to"]
                elif tool_name == "exec":
                    # 绑定固定的执行脚本或命令
                    if "command" in arguments:
                        match_context["command"] = arguments["command"]
                
                # 替代粗暴的全局放行，注册细粒度规则
                auth_store.add_approval(tool_name, target_action, match_context)
        else:
            logger.info(f"Session {session.key}: User rejected or interrupted tool {tool_name}")

        self.agent._set_tool_context(msg.channel, msg.chat_id)

        if approved:
            try:
                await self.agent.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=f"⚙️ 正在执行 `{tool_name}`，可能需要较长时间，请耐心稍候..."
                ))
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.warning(f"Failed to publish execution feedback: {e}")
                
            # Phase 40B-1: Write checkpoint WAL before tool execution (HITL branch)
            _ckpt_path = None
            _ckpt_enabled = getattr(getattr(self.agent._get_config().agents, 'reliability', None), 'checkpoint_enabled', True)
            if _ckpt_enabled and msg.channel and msg.chat_id:
                _ckpt_session_key = self.agent.sessions.resolve_key(f"{msg.channel}:{msg.chat_id}")
                _ckpt_tool_infos = [{"name": tool_name, "arguments": arguments}]
                _ckpt_path = self.agent.sessions.write_checkpoint(_ckpt_session_key, _ckpt_tool_infos)
                
            try:
                res = await self.agent.tools.execute(tool_name, arguments)
                from nanobot.agent.loop import _normalize_tool_result
                result_str = _normalize_tool_result(res, tool_name)
                # Phase 40B-1: Clear checkpoint after successful execution (HITL branch)
                if _ckpt_path:
                    self.agent.sessions.clear_checkpoint(_ckpt_path)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                result_str = f"Error executing tool: {e}"
                if _ckpt_path:
                    self.agent.sessions.clear_checkpoint(_ckpt_path)
        else:
            result_str = "Error: Execution blocked by user rejection."

        # Remove the previous Action Required message from session history to maintain clean dialog
        try:
            for i in range(len(session.messages)-1, -1, -1):
                msg_dict = session.messages[i]
                if msg_dict.get("role") == "assistant" and "⚠️ **Action Required!**" in str(msg_dict.get("content", "")):
                    session.messages.pop(i)
                    break
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.warning(f"Session {session.key}: Failed to cleanup UI message, ignoring: {e}")

        # Reconstruct the missing assistant message before the tool message to satisfy strict API schema
        session.add_message("assistant", content=None, tool_calls=[{
            "id": tool_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(arguments, ensure_ascii=False)
            }
        }])

        session.add_message("tool", result_str, tool_call_id=tool_id, name=tool_name)
        
        # Build prompt to resume loop — include original user request for context
        history = session.get_history(max_messages=self.agent.memory_window)
        original_request = ""
        for m in reversed(history):
            if m.get("role") == "user" and not m.get("content", "").startswith("[System:"):
                original_request = m["content"]
                break
        if approved:
            resume_msg = (
                f"[System message: The action for '{tool_name}' was completed successfully. "
                f"Please review the returned result in the history and continue the conversation normally.]"
            )
        else:
            resume_msg = (
                f"Validation / Information: {user_input}\n"
                f"The user has declined the tool execution for '{tool_name}' and provided additional input.\n"
                f"Original user request: {original_request[:500]}\n"
                f"Please address the user's input safely and proceed."
            )
        initial_messages = self.agent.context.build_messages(
            history=history,
            current_message=resume_msg,
            channel=msg.channel,
            chat_id=msg.chat_id
        )
        
        final_content, tools_used, tc_args, _ = await self.agent._run_agent_loop(
            initial_messages, channel=msg.channel, chat_id=msg.chat_id
        )
        
        # B-1: Guard against final_content being None (e.g., max iterations
        # reached without LLM producing a non-tool response).
        if final_content is None:
            final_content = "Task processing completed."
        
        session.add_message("assistant", final_content)
        if tools_used:
             session.last_tool_calls = tc_args
        self.agent.sessions.save(session)
        
        # We must return OutboundMessage so the dashboard receives the final output.
        # Removing Phase 32 logic which assumed all UIs subscribed to streaming endpoints.
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id,
            content=final_content
        )

    async def handle_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.agent.sessions.get_or_create(session_key)
        self.agent._set_tool_context(origin_channel, origin_chat_id)
        initial_messages = self.agent.context.build_messages(
            history=session.get_history(max_messages=self.agent.memory_window),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        final_content, _, _, _ = await self.agent._run_agent_loop(
            initial_messages, channel=origin_channel, chat_id=origin_chat_id
        )

        if final_content is None:
            final_content = "Background task completed."
        
        # Phase 62: Use virtual tool roundtrip instead of 'user' role for system events
        import uuid
        call_id = f"call_{uuid.uuid4().hex[:10]}"
        session.add_message(
            role="assistant",
            content=None,
            tool_calls=[{"id": call_id, "type": "function", "function": {"name": "system_event_listener", "arguments": "{}"}}]
        )
        session.add_message(
            role="tool", 
            content=f"[System Notice from {msg.sender_id}] {msg.content}", 
            tool_call_id=call_id, 
            name="system_event_listener"
        )
        session.add_message("assistant", final_content)
        self.agent.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
