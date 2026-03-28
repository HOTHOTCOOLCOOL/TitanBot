"""Session state handlers for the agent loop."""

__all__ = ["StateHandler"]

import json
import asyncio
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
        kw = self.agent.knowledge_workflow
        if kw.is_use_command(user_input):
            logger.info(f"Session {session.key}: User chose to use knowledge base")
            match = session.pending_knowledge
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
                match=session.pending_knowledge, 
                current_request=msg.content, 
                history=history
            )
            
            extracted_key = session.pending_knowledge.get("_extracted_key")
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
        kw = self.agent.knowledge_workflow
        if kw.is_save_confirm(user_input):
            logger.info(f"Session {session.key}: User confirmed save to knowledge base")
            pending = session.pending_save
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
        kw = self.agent.knowledge_workflow
        if kw.is_upgrade_command(user_input):
            logger.info(f"Session {session.key}: User confirmed skill upgrade")
            pending = session.pending_upgrade
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
            
        action = user_input.strip().lower()
        tool_name = pending.get("tool")
        arguments = pending.get("arguments", {})
        tool_id = pending.get("id")
        
        session.pending_approval_task = None
        session.mark_metadata_dirty()
        
        approved = False
        if action in ["1", "approve", "ok", "yes", "y", "allow"]:
            approved = True
            logger.info(f"Session {session.key}: User approved High-Risk tool {tool_name}")
        elif action in ["2", "always", "a"]:
            approved = True
            logger.info(f"Session {session.key}: User always-approved tool {tool_name}")
            auth_store = self.agent._get_approval_store()
            if auth_store:
                # Tool-level rule: approve ALL actions for this tool (no action filter, no context)
                auth_store.add_approval(tool_name, "")
        else:
            logger.info(f"Session {session.key}: User rejected tool {tool_name}")

        self.agent._set_tool_context(msg.channel, msg.chat_id)

        if approved:
            try:
                res = await self.agent.tools.execute(tool_name, arguments)
                result_str = str(res)
            except Exception as e:
                result_str = f"Error executing tool: {e}"
        else:
            result_str = "Error: Execution blocked by user rejection."

        session.add_message("tool", result_str, tool_call_id=tool_id, name=tool_name)
        
        # Build prompt to resume loop — include original user request for context
        history = session.get_history(max_messages=self.agent.memory_window)
        original_request = ""
        for m in reversed(history):
            if m.get("role") == "user" and not m.get("content", "").startswith("[System:"):
                original_request = m["content"]
                break
        resume_msg = (
            f"[System: HITL confirmation completed. Tool '{tool_name}' returned: {result_str[:200]}]\n"
            f"Original user request: {original_request[:500]}\n"
            f"Continue executing the original task."
        )
        initial_messages = self.agent.context.build_messages(
            history=history,
            current_message=resume_msg,
            channel=msg.channel,
            chat_id=msg.chat_id
        )
        
        final_content, tools_used, tc_args = await self.agent._run_agent_loop(
            initial_messages, channel=msg.channel, chat_id=msg.chat_id
        )
        
        session.add_message("assistant", final_content)
        if tools_used:
             session.last_tool_calls = tc_args
        self.agent.sessions.save(session)
        
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
        final_content, _, _ = await self.agent._run_agent_loop(
            initial_messages, channel=origin_channel, chat_id=origin_chat_id
        )

        if final_content is None:
            final_content = "Background task completed."
        
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.agent.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
