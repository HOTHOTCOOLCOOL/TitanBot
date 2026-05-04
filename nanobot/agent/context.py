"""Context builder for assembling agent prompts."""

__all__ = ["ContextBuilder"]

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.vector_store import VectorMemory


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "KNOWLEDGE.md", "docs/rules/ARCHITECTURE.md"]
    _REASONING_TEMPLATE_MAX_CHARS = 1000
    _SKILL_INJECTION_BUDGET = 8000
    
    def __init__(self, workspace: Path, language: str = "zh", provider=None, model=None,
                 embedding_model: str | None = None):
        self.workspace = workspace
        self.language = language
        self.memory = MemoryStore(workspace)
        self.vector_memory = VectorMemory(workspace, provider=provider, model=model,
                                          embedding_model=embedding_model)
        self.skills = SkillsLoader(workspace)
        # C3: Track persisted visual memory hashes to avoid duplicates in tool loops
        self._persisted_visual_hashes: set[str] = set()
    
    def build_system_prompt(self, skill_names: list[str] | None = None, evicted_context: str | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity
        parts.append(self._get_identity())

        # Global execution safety protocol
        parts.append(self._get_complex_task_protocol())
        
        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
            
        # Evicted Context Buffer
        if evicted_context:
            parts.append(f"## Evicted Context Buffer\n(Summary of older messages dropped from immediate history)\n{evicted_context}")
        
        # Memory context
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading
        # 1. Always-loaded skills and explicitly requested skills
        target_skills = self.skills.get_always_skills()
        if skill_names:
            for s in skill_names:
                if s not in target_skills:
                    target_skills.append(s)
                    
        # P1: Resolve and inject prerequisites
        final_skills = []
        for s in target_skills:
            deps = self.skills.resolve_dependencies(s)
            for dep in deps:
                if dep not in final_skills:
                    from loguru import logger
                    logger.debug(f"Injected prerequisite skill '{dep}' for target skill '{s}'")
                    final_skills.append(dep)
            if s not in final_skills:
                final_skills.append(s)

        if final_skills:
            budget = getattr(self, "_SKILL_INJECTION_BUDGET", 8000)
            injected_skills = []
            current_len = 0
            
            for skill_name in final_skills:
                # Approximate length based on load_skills_for_context output
                content_raw = self.skills.load_skill(skill_name)
                if content_raw:
                    stripped = self.skills._strip_frontmatter(content_raw)
                    block = f"### Skill: {skill_name}\n\n{stripped}"
                    block_len = len(block) + 4
                    
                    if current_len + block_len > budget:
                        from loguru import logger
                        logger.warning(f"Skill injection budget exceeded ({current_len} > {budget}). Dropping '{skill_name}' and subsequent skills.")
                        break
                        
                    injected_skills.append(skill_name)
                    current_len += block_len

            if injected_skills:
                always_content = self.skills.load_skills_for_context(injected_skills)
                if always_content:
                    parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities, organized by category. To use a skill, read its SKILL.md file using the read_file tool.
CRITICAL: If a task matches a Skill listed below, you MUST use the read_file tool to read its SKILL.md BEFORE attempting to write custom bash/python scripts.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        # Phase 49: IFCC Protocol
        try:
            from nanobot.config.loader import get_config as _get_cfg_c
            _ifcc_enabled = getattr(getattr(_get_cfg_c().agents, 'memory_features', None), 'ifcc_enabled', True)
            if _ifcc_enabled:
                parts.append("## Context Condensation\nWhen you have definitively resolved a step (confirmed root cause, completed analysis),\nsummarize the key finding in <mem>concise conclusion ≤200 chars</mem>.\nPlace it AFTER any <think> block. This milestone survives context truncation.")
        except Exception:
            pass
        
        return "\n\n---\n\n".join(parts)

    @classmethod
    def _truncate_reasoning_template(cls, summary: str) -> str:
        """Apply the strict reasoning-template prompt budget."""
        return summary[:cls._REASONING_TEMPLATE_MAX_CHARS]

    @classmethod
    def _format_kg_context(cls, entries: list[dict[str, Any]]) -> str:
        """Format KG entries while enforcing the reasoning-template cap."""
        if not entries:
            return ""

        parts = []
        for entry in entries:
            name = str(entry.get("name", ""))
            summary = str(entry.get("summary", ""))
            if entry.get("type") == "reasoning_template":
                summary = cls._truncate_reasoning_template(summary)
            parts.append(f"- **{name}**: {summary}")

        return "## Entity Knowledge\n" + "\n".join(parts)

    def _resolve_kg_context(
        self,
        kg: Any,
        query: str,
        prefetch_rag: list[dict[str, Any]] | None = None,
        anchors: list[str] | None = None,
        fallback_text: str | None = None,
    ) -> str:
        """Build KG prompt context with type-aware formatting."""
        if hasattr(kg, "get_entity_context_entries"):
            entries = kg.get_entity_context_entries(
                query,
                prefetch_rag=prefetch_rag,
                anchors=anchors,
            )
            if entries:
                return self._format_kg_context(entries)
            return kg.get_entity_context(query, prefetch_rag=prefetch_rag, anchors=anchors)
        if fallback_text is not None:
            return fallback_text
        return kg.get_entity_context(query, prefetch_rag=prefetch_rag, anchors=anchors)

    @staticmethod
    def _task_step_icon(status: str) -> str:
        """Map task step status to a compact icon for prompt injection."""
        normalized = (status or "").lower()
        if normalized == "completed":
            return "✅"
        if normalized in {"running", "in_progress"}:
            return "🔄"
        if normalized == "failed":
            return "❌"
        return "⏳"

    @classmethod
    def _format_task_tracker_status(cls, tracker: Any | None) -> str:
        """Format active task progress for L0 injection with a hard 400-char cap."""
        if tracker is None:
            return ""

        task = tracker.get_active_task() if hasattr(tracker, "get_active_task") else None
        if not task:
            return ""

        progress = {}
        if hasattr(tracker, "get_progress"):
            try:
                progress = tracker.get_progress(task.task_id) or {}
            except Exception:
                progress = {}

        current_step = progress.get("current_step") or ""
        progress_percent = progress.get("progress_percent", 0)
        task_status = getattr(task.status, "value", task.status)

        lines = [
            f"\n\n## 📋 Active Task Tracker (ID: {task.task_id[:8]})",
            f"**Goal**: {task.user_request[:100]}",
            f"**Status**: {task_status} | **Progress**: {progress_percent}%",
        ]
        if current_step:
            lines.append(f"**Current Step**: {current_step}")

        steps = task.steps[-3:] if task.steps else []
        if steps:
            for step in steps:
                step_status = getattr(step, "status", "pending")
                lines.append(
                    f"- {cls._task_step_icon(step_status)} {step.name} ({step_status})"
                )
        else:
            lines.append("- ⏳ no recorded steps yet")

        return "\n".join(lines)[:400]
    
    def _get_identity(self) -> str:
        """Get the core identity section."""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. 

You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks
- Access Outlook emails

## ⚠️ 重要：消息发送工具的区别

**message 工具**：
- 只用于发送到 飞书/微信/Telegram 等聊天工具
- 不能发送到外部邮箱！

**outlook.send_email 行动**：
- 用于发送到外部邮箱（如 DAVIDMSN@HOTMAIL.COM）
- 用户要求"发邮件"或"发送到邮箱"时，必须使用 outlook 工具的 send_email 行动！
- 绝对不要用 message 工具发送到邮箱！

## Current Time
{now} ({tz})

**日期理解提示**: 日报通常在次日发送。"昨天的销售数据" = 搜索今天的报告；"今天的report" = 昨天的业绩。请结合 KNOWLEDGE.md 中的业务规则判断应搜索哪天的邮件。

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Core Preferences (L1 Memory): {workspace_path}/memory/preferences.json
- Long-term memory (L2 Archive): {workspace_path}/memory/MEMORY.md (Use `memory` tool to search/store/delete)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable)
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to simple questions or greetings, reply directly with text.
BUT when user asks you to DO something (search, analyze, send, execute), you MUST use tools!
- Want to know today's emails? Use outlook tool
- Want to analyze attachments? Use attachment_analyzer tool  
- Want to send email? Use outlook.send_email action
- Want to read files? Use read_file tool
- ⚠️ MISSING SKILLS? If the user asks for something outside your current skills (like creating a PPT, posting to social media), DO NOT simply say you can't or suggest they do it manually. Instead, use `exec` tool to run `npx clawhub search <keyword>` to find and install a skill!

**⚠️ CRITICAL INSTRUCTION FOR REASONING MODELS:**
When you decide to start a task (e.g., "I will start making the PPT, please wait"), **YOU MUST CALL THE TOOLS IN THE SAME TURN**. 
DO NOT simply reply with "稍等" (please wait) without any tool calls! If you only return text, the system will pause and wait for the user, and the task will NOT start. 
If you want to inform the user to wait, you can do so, but NEVER FORGET to include the actual tool calls (e.g., `exec`, `read_file`) in the exact same response!

NEVER say "I have sent the email," "Task completed," or "✅ 已发送" unless you have ACTUALLY used the corresponding tools (like outlook) in this exact turn. DO NOT hallucinate tool execution.

NEVER just describe what you would do - actually call the tools and DO it!

**P0 Pseudo-Plan Guided Retrieval**: Before you call ANY tool for a complex task, you MUST emit a `<think>` block containing a numbered or bulleted list representing your pseudo-plan. You must outline the steps you intend to take.

Always be helpful, accurate, and concise. When using tools, think step by step: what you know, what you need, and why you chose this tool.
When remembering something important, use the `memory` tool with action='store'. Background processes will later distill it into preferences.json.
To recall past events, use the `memory` tool with action='search', or grep {workspace_path}/memory/HISTORY.md.

## 🧠 Memory Strategy
**What to remember:** user preferences, profile facts, project context, important decisions, long-term instructions.
**What NOT to remember:** temporary debugging info, large data blobs, passwords/API keys, one-time task results.
When the user says "记住"/"remember"/"别忘了"/"don't forget", actively store it using the `memory` tool.

## ⚠️ 语言要求 / Language
{self._get_language_instruction()}"""

    def _get_complex_task_protocol(self) -> str:
        """Fallback planning-gate anchor for workspaces with stale bootstrap files."""
        return """## Complex Task Protocol
When the user requests a complex mutating task such as:
- a system migration or logging migration
- a large refactor or bulk file edit
- a database/schema change
- any job that would require more than 3 mutating steps

you MUST call `write_artifact` first and write `implementation_plan.md`.
Do NOT call mutating execution tools until the user approves that plan."""
    
    def _get_language_instruction(self) -> str:
        """Get the language instruction based on configured language."""
        if self.language == "zh":
            return (
                "请始终使用**简体中文**回复用户，禁止使用繁体中文。"
                "用户使用中文提问时，必须用简体中文回答。"
                "包括分析结果、报告摘要、错误提示等所有输出内容都应使用简体中文。"
                "注意：是简体（如：执行、报告、任务），不是繁体（如：執行、報告、任務）。"
            )
        return "Respond in the same language as the user's message."

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        search_query: str | None = None,
        query_anchors: list[str] | None = None,
        context_limit: int = 120_000,
        evicted_context: str | None = None,
        knowledge_graph: "KnowledgeGraph | None" = None,
        pre_fetched_rag: Any | None = None,
        pre_fetched_kg: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.
            channel: Current channel (telegram, feishu, etc.).
            chat_id: Current chat/user ID.
            search_query: Optional pre-rewritten search query for RAG retrieval.
                If None, uses current_message directly.
            context_limit: Max estimated character budget for all messages
                (default 120K chars ≈ 30K tokens).  History is trimmed to fit.
            pre_fetched_rag: Pre-executed RAG search results (Phase 39 optimization).
            pre_fetched_kg: Pre-executed Knowledge string (Phase 39 optimization).

        Returns:
            List of messages including system prompt.
        """
        messages: list[dict[str, Any]] = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names, evicted_context=evicted_context)
        
        # Inject Task Tracker Status
        try:
            from nanobot.agent.task_tracker import get_active_tracker
            tracker = get_active_tracker()
            status_text = self._format_task_tracker_status(tracker)
            if status_text:
                # ADR-59: Strict budget enforcement
                if len(system_prompt) + len(status_text) <= context_limit:
                    system_prompt += status_text
                    task = tracker.get_active_task() if tracker else None
                    if task:
                        logger.debug(f"L0: Injected TaskTracker status for {task.task_id[:8]}")
                else:
                    logger.debug("TaskTracker injection skipped: budget exceeded")
            elif False:
                task = tracker.get_active_task()
                if task:
                    steps = task.steps[-3:] if task.steps else []
                    status_text = f"\n\n## 📋 Active Task Tracker (ID: {task.task_id[:8]})\n"
                    status_text += f"**Goal**: {task.user_request[:100]}\n"
                    for s in steps:
                        icon = "✅" if s.status == "completed" else "🔄" if s.status == "in_progress" else "❌" if s.status == "failed" else "⏳"
                        status_text += f"- {icon} {s.name}\n"
                    
                    status_text = status_text[:400]
                    # ADR-59: Strict budget enforcement
                    if len(system_prompt) + len(status_text) <= context_limit:
                        system_prompt += status_text
        except Exception as e:
            logger.debug(f"TaskTracker injection skipped: {e}")
        
        # Inject VectorMemory RAG context
        try:
            rag_results = pre_fetched_rag
            if rag_results is None:
                rag_query = search_query or current_message
                rag_results = self.vector_memory.search(rag_query, top_k=3)
            if rag_results:
                rag_context = self.vector_memory.format_results_for_context(rag_results)
                if rag_context:
                    system_prompt += f"\n\n{rag_context}"
        except Exception as e:
            logger.debug(f"Vector search skipped: {e}")

        # P1: Inject Knowledge Graph Entity Context (Phase 24: entity summaries)
        # D1: gated behind memory_features.knowledge_graph_enabled
        # D2: Accept pre-cached KnowledgeGraph instance to avoid per-message disk I/O
        try:
            from nanobot.config.loader import get_config
            _mem_feat = get_config().agents.memory_features
            if _mem_feat.knowledge_graph_enabled:
                kg = knowledge_graph  # D2: prefer cached instance
                if kg is None:
                    from nanobot.agent.knowledge_graph import KnowledgeGraph
                    kg = KnowledgeGraph(self.workspace, vector_memory=self.vector_memory)
                kq_query = search_query or current_message
                kg_prefetch_rag = rag_results if 'rag_results' in locals() else pre_fetched_rag
                kg_context = self._resolve_kg_context(
                    kg,
                    kq_query,
                    prefetch_rag=kg_prefetch_rag,
                    anchors=query_anchors,
                    fallback_text=pre_fetched_kg,
                )
                if not kg_context and pre_fetched_kg is not None:
                    kg_context = pre_fetched_kg
                if kg_context:
                    system_prompt += f"\n\n{kg_context}"
        except Exception as e:
            logger.debug(f"Knowledge Graph lookup skipped: {e}")

        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        oversized = []
        # Reconstruct multimodal history blocks before trimming
        for h_msg in history:
            if "media" in h_msg and h_msg["media"]:
                if isinstance(h_msg.get("content"), str):
                    h_msg["content"] = self._build_user_content(h_msg["content"], h_msg["media"], oversized)
                h_msg.pop("media", None)

        # Current message (with optional image attachments) must be built before trimming
        user_content = self._build_user_content(current_message, media, oversized)

        # Trim history so total context stays within budget
        trimmed_history, dropped_imgs, skel_count = self._trim_history(
            history, system_prompt, user_content, context_limit
        )

        # History
        messages.extend(trimmed_history)

        # Append fully resolved user_content
        messages.append({"role": "user", "content": user_content})

        degradation_notices = []
        for path in oversized:
            degradation_notices.append(f"⚠️ An image attachment exceeding 20MB was dropped from the context (file_path: {path}). Processing continues without visual data.")
        if dropped_imgs > 0:
            degradation_notices.append(
                f"⚠️ {dropped_imgs} image(s) removed due to token budget. "
                "Do NOT assume visual context. If the task requires images, ask user to re-provide."
            )
        if skel_count > 0:
            degradation_notices.append(
                f"⚠️ {skel_count} history message(s) compressed to summaries. "
                "Older context details may be incomplete."
            )
        if degradation_notices:
            messages.append({
                "role": "system",
                "content": "[Context Integrity Notice]\n" + "\n".join(degradation_notices)
            })

        # 🟢 Schema Consistency Sanitizer (Schema Strict Fix)
        # Persistent storage (especially HITL async approvals) might inject orphaned `role: tool` messages
        # without the accompanying `assistant[tool_calls]` message. Azure OpenAI strictly forbids this.
        # We rewrite any orphaned `role: tool` messages into `role: user` observations to preserve context
        # without triggering 502 Bad Requests.
        sanitized = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                valid = False
                for j in range(i - 1, -1, -1):
                    prev = messages[j]
                    if prev.get("role") == "assistant":
                        if prev.get("tool_calls"):
                            for tc in prev["tool_calls"]:
                                if isinstance(tc, dict) and tc.get("id") == msg.get("tool_call_id"):
                                    valid = True
                                    break
                        break
                    elif prev.get("role") != "tool":
                        break
                
                if not valid:
                    name = msg.get("name", "unknown_tool")
                    content = msg.get("content", "")
                    sanitized.append({
                        "role": "system",
                        "content": f"[Orphan tool telemetry: '{name}'] {content}"
                    })
                    continue
            sanitized.append(msg)

        return sanitized

    # ── Context window management ──────────────────────────────────────

    @staticmethod
    def _estimate_chars(messages: list[dict[str, Any]]) -> int:
        """Estimate total character count of a message list."""
        total = 0
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image_url":
                        try:
                            # Use token-equivalent char length for images (e.g. ~4000 chars) instead of raw base64 string
                            val = block.get("image_url", {})
                            if isinstance(val, dict):
                                total += 4000
                        except Exception:
                            total += 1000
                    else:
                        total += len(str(block.get("text", "")))
        return total

    def _trim_history(
        self,
        history: list[dict[str, Any]],
        system_prompt: str,
        current_message: list[dict[str, Any]] | str,
        context_limit: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Drop oldest history messages until total fits within *context_limit* chars.

        Keeps at least the last 4 messages so the LLM has immediate conversation
        continuity. Returns (trimmed_list, dropped_images, skeletonized_count).
        """
        # Ensure dynamic system prompt and current message are accurately sized including multimodality
        overhead = self._estimate_chars([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_message}
        ])
        history_chars = self._estimate_chars(history)

        if overhead + history_chars <= context_limit:
            return history, 0, 0  # fits — no trimming needed

        from loguru import logger
        target = int(context_limit * 0.80) - overhead
        min_keep = 4  # always keep at least the last N messages

        trimmed = list(history)
        dropped_imgs = 0
        skel_count = 0
        eviction_idx = 0
        while len(trimmed) - eviction_idx > min_keep and self._estimate_chars(trimmed) > target:
            msg_to_evict = trimmed[eviction_idx]

            # --- Phase 57: Visual Silent Downgrade ---
            has_image = False
            if isinstance(msg_to_evict.get("content"), list):
                new_content = []
                for block in msg_to_evict["content"]:
                    if isinstance(block, dict) and block.get("type") == "image_url":
                        has_image = True
                        dropped_imgs += 1
                        new_content.append({"type": "text", "text": "[图片内容已在相关对话中被分析并压缩]"})
                    else:
                        new_content.append(block)
                if has_image:
                    trimmed[eviction_idx]["content"] = new_content
                    # Re-evaluate budget immediately because stripping base64 saves massive characters
                    continue

            if msg_to_evict.get("milestone_summary") and not msg_to_evict.get("is_skeleton"):
                # Downgrade message to its milestone skeleton
                skel_count += 1
                trimmed[eviction_idx] = {
                    "role": "assistant",
                    "content": f"（上下文已压缩） {msg_to_evict['milestone_summary']}",
                    "is_skeleton": True,
                    "milestone_summary": msg_to_evict['milestone_summary']
                }
                eviction_idx += 1
            else:
                trimmed.pop(eviction_idx)

        dropped = len(history) - len(trimmed)
        if dropped:
            logger.info(
                f"Context window optimization: dropped {dropped} oldest history "
                f"messages ({history_chars} → {self._estimate_chars(trimmed)} chars)"
            )
        return trimmed, dropped_imgs, skel_count

    _MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB

    def _build_user_content(self, text: str, media: list[str] | None, oversized_drops: list[str] = None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            # R11: Skip oversized images to avoid injecting huge base64 payloads
            if p.is_file() and p.stat().st_size > self._MAX_IMAGE_BYTES:
                from loguru import logger
                logger.warning(f"Image too large ({p.stat().st_size} bytes), skipping: {path}")
                if oversized_drops is not None:
                    oversized_drops.append(path)
                continue
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list. Handles special image paths.
        
        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.
        
        Returns:
            Updated message list.
        """
        content: str | list[dict[str, Any]] = result
        user_multimodal_message = None

        # Intercept special screenshot payload: tool returns `__IMAGE__:/path/to/image.jpg`
        # Phase 33: Also handles dual-prefix format `"Error: ...\n__IMAGE__:..."` from
        # diagnostic screenshots. Scan for __IMAGE__: anywhere in the result string.
        if isinstance(result, str) and "__IMAGE__:" in result:
            path_part = result.split("__IMAGE__:", 1)[1]
            path = path_part.split(" | ANCHORS:", 1)[0].strip()
            anchor_text = ""
            if " | ANCHORS:" in path_part:
                anchor_text = path_part.split(" | ANCHORS:", 1)[1].strip()
                
            p = Path(path)
            if p.is_file():
                import mimetypes
                import base64
                mime, _ = mimetypes.guess_type(path)
                if mime and mime.startswith("image/"):
                    b64 = base64.b64encode(p.read_bytes()).decode()
                    content = f"Screenshot captured successfully. Path: {path}"
                    
                    user_content: list[dict[str, Any]] = [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    ]
                    if anchor_text:
                        user_content.append({"type": "text", "text": f"Evaluate the screenshot and continue the task. CRITICAL: When interacting with an element listed below, you MUST use the `ui_index` parameter instead of x and y coordinates! Do NOT hallucinate coordinates.\n\nANCHORS:\n{anchor_text}"})
                    else:
                        user_content.append({"type": "text", "text": "Evaluate the screenshot and continue the task."})
                        
                    user_multimodal_message = {
                        "role": "user",
                        "content": user_content
                    }

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": content
        })
        
        if user_multimodal_message:
            messages.append(user_multimodal_message)
            
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        milestone_summary: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        
        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).
            milestone_summary: Optional phase 49 IFCC summary.
        
        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant"}
        
        if milestone_summary:
            msg["milestone_summary"] = milestone_summary

        # Some backends reject empty text blocks, but require content explicitly set to None or empty.
        # We set it to None if empty so Litellm/OpenAI serializes it as null.
        if content:
            msg["content"] = content
            
            # --- 20G: Visual Memory Text Persistence ---
            # D1: gated behind memory_features.visual_memory_enabled
            _visual_enabled = True
            try:
                from nanobot.config.loader import get_config as _get_cfg_v
                _visual_enabled = _get_cfg_v().agents.memory_features.visual_memory_enabled
            except Exception:
                pass
            if _visual_enabled and len(messages) > 0 and messages[-1].get("role") == "user":
                prev_content = messages[-1].get("content")
                if isinstance(prev_content, list):
                    has_image = any(isinstance(c, dict) and c.get("type", "") == "image_url" for c in prev_content)
                    if has_image:
                        try:
                            # C3: Deduplicate — skip if this exact content was already persisted
                            import hashlib
                            # R16: SHA256 + 16-char prefix for lower collision probability
                            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
                            if content_hash in self._persisted_visual_hashes:
                                from loguru import logger
                                logger.debug(f"Visual memory already persisted (hash={content_hash}), skipping duplicate.")
                            else:
                                self._persisted_visual_hashes.add(content_hash)
                                from datetime import datetime
                                today_str = datetime.now().strftime("%Y-%m-%d")
                                mem_text = f"Visual Memory ([Screenshot/Image Analysis]): {content}"
                                if hasattr(self, 'memory') and self.memory:
                                    self.memory.append_daily_log(mem_text)
                                if hasattr(self, 'vector_memory') and self.vector_memory:
                                    self.vector_memory.ingest_text(
                                        content,
                                        source=f"daily_log:{today_str}",
                                        metadata={"date": today_str, "type": "visual_memory"}
                                    )
                                from loguru import logger
                                logger.info("Visual memory persisted to HISTORY and vector index.")
                        except Exception as e:
                            from loguru import logger
                            logger.error(f"Failed to persist visual memory: {e}")
            # ------------------------------------------
            # ADR-62 Schema Null Compliance: If tool_calls are present, content MUST be null
            if tool_calls:
                msg["content"] = None
        else:
            msg["content"] = None if tool_calls else ""

        if tool_calls:
            msg["tool_calls"] = tool_calls

        # Include reasoning content when provided (required by some thinking models)
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages
