"""Knowledge Workflow Engine.

Implements the user's desired knowledge base workflow:
1. Extract a task Key from user request (via lightweight LLM call)
2. Code-level comparison against stored knowledge base entries
3. If match found: ask user to reuse or re-execute
4. After task completion: prompt to save/update knowledge base

This module serves as a thin facade, delegating to specialized sub-modules:
- key_extractor: Key extraction from user requests
- knowledge_judge: Knowledge quality evaluation, save/merge, and adaptation
- command_recognition: User command parsing
- prompt_formatter: Prompt and display formatting
- outcome_tracker: Implicit feedback and outcome recording
- kb_commands: Knowledge base management commands (/kb list, delete, cleanup)
"""

from collections import OrderedDict
from functools import lru_cache
from typing import Any

from loguru import logger

from nanobot.agent.task_knowledge import TaskKnowledgeStore, tokenize_key
from nanobot.agent.hybrid_retriever import hybrid_retrieve

from nanobot.agent import command_recognition as cmd_rec
from nanobot.agent import prompt_formatter as prompt_fmt
from nanobot.agent import outcome_tracker as out_trk
from nanobot.agent import kb_commands as kb_cmd
from nanobot.agent import key_extractor as key_ext
from nanobot.agent import knowledge_judge as kj


# E1/R10: LRU cache for key extraction results (OrderedDict for true LRU semantics)
_key_extraction_cache: OrderedDict[str, str] = OrderedDict()
_KEY_CACHE_MAX = 128


class KnowledgeWorkflow:
    """Knowledge base workflow engine.

    Responsibilities:
    1. Call lightweight LLM to extract a Key from user request
       (Chinese ≤50 chars, English ≤200 chars)
    2. Code-level comparison of Key against knowledge base entries
       (exact match → substring match → common-word similarity)
    3. Format prompts for user interaction
    4. Save/update knowledge base entries
    """

    def __init__(
        self,
        provider: Any = None,
        model: str | None = None,
        workspace: Any = None,
        vector_memory: Any = None,
    ):
        self.provider = provider
        self.model = model
        self.workspace = workspace
        self.knowledge_store = TaskKnowledgeStore(workspace) if workspace else None
        self.vector_memory = vector_memory  # P3: optional ChromaDB semantic fallback

    # ----------------------------------------------------------------
    # 1. Key Extraction (delegates to key_extractor)
    # ----------------------------------------------------------------

    async def extract_key(self, user_request: str, history: list[dict] | None = None) -> str:
        """Extract a task key from user request using a lightweight LLM call.

        E1/R10: Results are cached with true LRU eviction to avoid
        redundant LLM calls for repeated or similar requests.

        Returns:
            Extracted key string, or a truncated version of the request as fallback.
        """
        # E1/R10: Check LRU cache first
        cache_key = user_request.strip()[:200]
        if cache_key in _key_extraction_cache:
            _key_extraction_cache.move_to_end(cache_key)  # R10: LRU touch
            logger.debug(f"Key extraction cache hit: '{cache_key[:40]}'")
            return _key_extraction_cache[cache_key]

        # P29-2: Workflow Model Routing
        from nanobot.config.loader import get_config
        config = get_config()
        wf_models = getattr(config.agents, 'workflow_models', {})
        ext_model = wf_models.get('key_extraction', self.model)
        ext_provider = self.provider
        if ext_model != self.model:
            from nanobot.providers.factory import ProviderFactory
            ext_provider = ProviderFactory.get_provider(ext_model, config) or self.provider

        result = await key_ext.extract_key(
            user_request,
            provider=ext_provider,
            model=ext_model,
            history=history,
        )

        # E1/R10: Store in cache (evict LRU if over limit)
        if len(_key_extraction_cache) >= _KEY_CACHE_MAX:
            _key_extraction_cache.popitem(last=False)  # R10: evict oldest (LRU)
        _key_extraction_cache[cache_key] = result
        return result


    # ----------------------------------------------------------------
    # 2. Knowledge Base Matching (pure code, no LLM)
    # ----------------------------------------------------------------

    # E1: Adaptive threshold — scales with KB size to reduce false positives
    @staticmethod
    def _adaptive_threshold(num_entries: int, base: float = 0.6) -> float:
        """Return a stricter threshold as the KB grows.

        - ≤10 entries: base (0.60)
        - 50 entries: ~0.68
        - 100+ entries: capped at 0.75
        """
        extra = min(num_entries / 300, 0.15)  # max +0.15
        return round(base + extra, 3)

    def match_knowledge(self, key: str) -> dict[str, Any] | None:
        """Match extracted key against knowledge base entries.

        Matching strategy (in order of priority):
        1. Exact match (key strings identical)
        2. Substring match (one key contains the other)
        3. Hybrid retrieval (Dense + BM25) with E1 adaptive threshold

        The returned dict is augmented with ``_match_confidence`` (0-1).

        Returns:
            Matched task entry dict, or None if no match found.
        """
        if not self.knowledge_store:
            return None

        tasks = self.knowledge_store.get_all_tasks()
        if not tasks:
            return None

        key_lower = key.lower().strip()

        # Pass 1: Exact match
        for task in tasks:
            task_key = task.get("key", "").lower().strip()
            if task_key == key_lower:
                logger.info(f"KnowledgeWorkflow: exact match found: '{task_key}'")
                task["_match_confidence"] = 1.0
                return task

        # Pass 2: Substring match
        best_substring: dict | None = None
        best_ratio = 0.0
        for task in tasks:
            task_key = task.get("key", "").lower().strip()
            if not task_key:
                continue
            if key_lower in task_key or task_key in key_lower:
                shorter = min(len(key_lower), len(task_key))
                longer = max(len(key_lower), len(task_key))
                ratio = shorter / longer if longer > 0 else 0
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_substring = task
        if best_substring and best_ratio >= 0.65 and min(len(key_lower), len(best_substring.get('key', '').lower().strip())) >= 4:
            logger.info(
                f"KnowledgeWorkflow: substring match found: "
                f"'{best_substring.get('key')}' (ratio={best_ratio:.2f})"
            )
            best_substring["_match_confidence"] = round(best_ratio, 3)
            return best_substring

        # Pass 3: True Hybrid Retrieval (Dense + BM25)
        # E1: Adaptive threshold — stricter as KB grows
        threshold = self._adaptive_threshold(len(tasks))
        best_hybrid_match, best_hybrid_score = hybrid_retrieve(
            query=key,
            candidates=tasks,
            text_field="key",
            extra_text_field="triggers",
            match_key_field="key",
            vector_memory=self.vector_memory if self.knowledge_store else None,
            vector_source_filter="knowledge",
            threshold=threshold,
        )

        if best_hybrid_match:
            logger.info(
                f"KnowledgeWorkflow: hybrid match found: "
                f"'{best_hybrid_match.get('key')}' (score={best_hybrid_score:.2f}, threshold={threshold})"
            )
            best_hybrid_match["_match_confidence"] = round(best_hybrid_score, 3)
            return best_hybrid_match

        logger.debug(f"KnowledgeWorkflow: no match found for key '{key}'")
        return None

    def match_experience(self, action_context: str) -> str | None:
        """Find action-level tactical prompts from the Experience Bank (P12 feature).

        Args:
            action_context: The current context of the agent's action.

        Returns:
            A tactical prompt string to inject, or None.
        """
        if not self.knowledge_store:
            return None

        experiences = self.knowledge_store.get_experiences()
        if not experiences:
            return None

        # Hybrid Retrieval (Dense + BM25) for Experiences
        best_match, best_score = hybrid_retrieve(
            query=action_context,
            candidates=experiences,
            text_field="trigger",
            extra_text_field=None,
            match_key_field="trigger",
            vector_memory=self.vector_memory if self.knowledge_store else None,
            vector_source_filter="knowledge_experience",
            threshold=0.4,
            no_dense_penalty=1.0,
        )

        if best_match:
            logger.info(
                f"KnowledgeWorkflow: experience match found: "
                f"'{best_match.get('trigger')}' (score={best_score:.2f})"
            )
            return best_match.get("prompt")

        return None

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for word-similarity matching."""
        return tokenize_key(text)

    # ----------------------------------------------------------------
    # 3. User Command Recognition (delegates to command_recognition)
    # ----------------------------------------------------------------

    @staticmethod
    def is_use_command(text: str) -> bool:
        """Check if user input means 'use knowledge base result'."""
        return cmd_rec.is_use_command(text)

    @staticmethod
    def is_redo_command(text: str) -> bool:
        """Check if user input means 're-execute the task'."""
        return cmd_rec.is_redo_command(text)

    @staticmethod
    def is_save_confirm(text: str) -> bool:
        """Check if user input means 'confirm save to knowledge base'."""
        return cmd_rec.is_save_confirm(text)

    @staticmethod
    def is_upgrade_command(text: str) -> bool:
        """Check if user input means 'confirm skill upgrade'."""
        return cmd_rec.is_upgrade_command(text)

    # ----------------------------------------------------------------
    # 4. Prompt Formatting (delegates to prompt_formatter)
    # ----------------------------------------------------------------

    @staticmethod
    def format_match_prompt(match: dict, lang: str | None = None) -> str:
        """Format the knowledge-match prompt for the user."""
        return prompt_fmt.format_match_prompt(match, lang)

    @staticmethod
    def format_save_prompt(lang: str | None = None) -> str:
        """Format the save-to-knowledge-base prompt."""
        return prompt_fmt.format_save_prompt(lang)

    @staticmethod
    def format_save_confirmed(lang: str | None = None) -> str:
        """Format the save-confirmed message."""
        return prompt_fmt.format_save_confirmed(lang)

    # ----------------------------------------------------------------
    # 5. Knowledge Base Save / Update (delegates to knowledge_judge)
    # ----------------------------------------------------------------

    async def save_to_knowledge(
        self,
        key: str,
        steps: list[dict],
        user_request: str,
        result_summary: str = "",
    ) -> bool:
        """Save or update a task in the knowledge base."""
        success = await kj.save_to_knowledge(
            key=key,
            steps=steps,
            user_request=user_request,
            knowledge_store=self.knowledge_store,
            provider=self.provider,
            model=self.model,
            result_summary=result_summary,
        )
        if success and self.vector_memory and self.knowledge_store:
            task = self.knowledge_store.find_task(key)
            if not task:
                task = self.knowledge_store.find_similar_task(key)
            if task:
                target_key = task.get("key", key)
                desc = task.get("description", "")
                triggers = task.get("triggers", [])
                tags = task.get("tags", [])
                text_parts = [f"Key: {target_key}"]
                if desc: text_parts.append(f"Description: {desc}")
                if triggers: text_parts.append(f"Triggers: {', '.join(triggers)}")
                if tags: text_parts.append(f"Tags: {', '.join(tags)}")
                content = "\n".join(text_parts)
                self.vector_memory.ingest_text(
                    content,
                    source=f"knowledge:{target_key}",
                    metadata={"key": target_key},
                    clear_old_source=True,
                )
        return success

    async def evaluate_and_structure_knowledge(
        self, key: str, request: str, steps: list[dict], result: str,
    ) -> dict[str, Any]:
        """Evaluate new knowledge using LLM and structure it into formal fields."""
        
        # P29-2: Workflow Model Routing
        from nanobot.config.loader import get_config
        config = get_config()
        wf_models = getattr(config.agents, 'workflow_models', {})
        eval_model = wf_models.get('knowledge_evaluation', self.model)
        eval_provider = self.provider
        if eval_model and eval_model != self.model:
            from nanobot.providers.factory import ProviderFactory
            eval_provider = ProviderFactory.get_provider(eval_model, config) or self.provider

        return await kj.evaluate_and_structure_knowledge(
            key, request, steps, result,
            provider=eval_provider,
            model=eval_model,
        )

    def get_knowledge_result(self, match: dict, lang: str | None = None) -> str:
        """Format and return the stored result of a matched knowledge entry."""
        return prompt_fmt.get_knowledge_result(match, lang)

    # ----------------------------------------------------------------
    # 6. Outcome Tracking (delegates to outcome_tracker)
    # ----------------------------------------------------------------

    @classmethod
    def is_negative_feedback(cls, text: str) -> bool:
        """Check if user message implies the previous task failed."""
        return out_trk.is_negative_feedback(text)

    def record_outcome(self, key: str, success: bool) -> None:
        """Record task outcome (success or failure) in knowledge base."""
        out_trk.record_outcome(self.knowledge_store, key, success)

    async def extract_and_save_directive(self, session: Any, user_feedback: str) -> None:
        """P29-1: Extract 'Directive Signal' from user corrections and save to Experience Bank.
        
        This translates a specific user correction (e.g., 'wrong, use X instead of Y')
        into an action-level tactical prompt to be injected next time.
        """
        if not self.knowledge_store or not self.provider:
            return

        recent_messages = session.get_history(max_messages=4)
        conv_text = ""
        for m in recent_messages:
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join([str(b.get("text", "")) for b in content if b.get("type") == "text"])
            conv_text += f"{m['role'].upper()}: {content}\n"

        prompt = f'''Analyze the user's negative feedback alongside the recent conversation.
Extract a concise, actionable "Directive Signal" (a tactical rule) to avoid this mistake in the future.

Recent Conversation:
{conv_text}

User's Corrective Feedback:
{user_feedback}

Return ONLY a valid JSON object:
{{
  "trigger": "A short phrase describing the context or action that was wrong (e.g., 'When calculating revenue')",
  "prompt": "The specific tactical instruction to follow next time (e.g., 'Always exclude taxes from revenue calculations')"
}}
No markdown fences.'''

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a metacognitive component. Respond ONLY in strict JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,
            )
            import json_repair
            text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json_repair.loads(text)
            if isinstance(result, dict) and "trigger" in result and "prompt" in result:
                # Save to Experience Bank
                self.knowledge_store.add_experience(
                    context_trigger=result["trigger"],
                    tactical_prompt=f"USER DIRECTIVE: {result['prompt']}",
                    action_type="correction"
                )
                if self.vector_memory:
                    content = f"Trigger: {result['trigger']}\nPrompt: {result['prompt']}"
                    self.vector_memory.ingest_text(
                        content,
                        source=f"knowledge_experience:{result['trigger']}",
                        metadata={"trigger": result['trigger']},
                        clear_old_source=True
                    )
                logger.info(f"P29-1: Extracted and saved directive for '{result['trigger']}'")
        except Exception as e:
            logger.error(f"Failed to extract directive signal: {e}")

    # ----------------------------------------------------------------
    # 7. Few-shot Prompt Generation (delegates to prompt_formatter / knowledge_judge)
    # ----------------------------------------------------------------

    def format_few_shot_prompt(self, match: dict) -> str:
        """Generate a few-shot reference prompt from a high-success knowledge entry."""
        return prompt_fmt.format_few_shot_prompt(match)

    async def adapt_knowledge(
        self, match: dict, current_request: str, history: list[dict] | None = None,
    ) -> str:
        """Adapt a retrieved knowledge entry into a tailored few-shot prompt."""
        
        # P29-2: Workflow Model Routing
        from nanobot.config.loader import get_config
        config = get_config()
        wf_models = getattr(config.agents, 'workflow_models', {})
        adapt_model = wf_models.get('knowledge_adaptation', self.model)
        adapt_provider = self.provider
        if adapt_model and adapt_model != self.model:
            from nanobot.providers.factory import ProviderFactory
            adapt_provider = ProviderFactory.get_provider(adapt_model, config) or self.provider

        return await kj.adapt_knowledge(
            match=match,
            current_request=current_request,
            provider=adapt_provider,
            model=adapt_model,
            history=history,
        )

    def get_match_stats(self, match: dict) -> dict:
        """Get formatted stats for a knowledge match (for display in prompts)."""
        return prompt_fmt.get_match_stats(match)

    # ----------------------------------------------------------------
    # 8. Skill Upgrade Suggestion
    # ----------------------------------------------------------------

    def should_suggest_skill_upgrade(self, key: str) -> bool:
        """Check if a knowledge entry should be suggested for skill upgrade.

        Criteria: success_count >= 3 (frequently used and proven reliable).
        """
        if not self.knowledge_store:
            return False
        task = self.knowledge_store.find_task(key)
        if not task:
            return False
        return task.get("success_count", 0) >= 3

    @staticmethod
    def format_skill_upgrade_prompt(match: dict, lang: str | None = None) -> str:
        """Format the skill upgrade suggestion prompt."""
        return prompt_fmt.format_skill_upgrade_prompt(match, lang)

    # ----------------------------------------------------------------
    # 9. Silent Steps Update (delegates to outcome_tracker)
    # ----------------------------------------------------------------

    def silent_update_steps(self, key: str, tool_calls: list[dict]) -> bool:
        """Silently update steps_detail for a task after successful execution."""
        return out_trk.silent_update_steps(self.knowledge_store, key, tool_calls)

    # ----------------------------------------------------------------
    # 10. Knowledge Base Management Commands (delegates to kb_commands)
    # ----------------------------------------------------------------

    def format_kb_list(self, lang: str | None = None) -> str:
        """Format a human-readable list of all knowledge base entries."""
        return kb_cmd.format_kb_list(self.knowledge_store, lang)

    def delete_knowledge(self, key: str, lang: str | None = None) -> str:
        """Delete a knowledge base entry by key. Returns user-facing message."""
        return kb_cmd.delete_knowledge(self.knowledge_store, key, lang, self.vector_memory)

    def cleanup_knowledge(self, lang: str | None = None) -> str:
        """Find and merge duplicate/similar knowledge base entries."""
        return kb_cmd.cleanup_knowledge(self.knowledge_store, lang, self.vector_memory)
