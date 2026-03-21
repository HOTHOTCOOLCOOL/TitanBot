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


# E1: LRU cache for key extraction results (avoids redundant LLM calls)
_key_extraction_cache: dict[str, str] = {}
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

        E1: Results are cached (LRU) to avoid redundant LLM calls for
        repeated or similar requests within the same session.

        Returns:
            Extracted key string, or a truncated version of the request as fallback.
        """
        # E1: Check LRU cache first
        cache_key = user_request.strip()[:200]
        if cache_key in _key_extraction_cache:
            logger.debug(f"Key extraction cache hit: '{cache_key[:40]}'")
            return _key_extraction_cache[cache_key]

        result = await key_ext.extract_key(
            user_request,
            provider=self.provider,
            model=self.model,
            history=history,
        )

        # E1: Store in cache (evict oldest if over limit)
        if len(_key_extraction_cache) >= _KEY_CACHE_MAX:
            oldest = next(iter(_key_extraction_cache))
            del _key_extraction_cache[oldest]
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
        return await kj.save_to_knowledge(
            key=key,
            steps=steps,
            user_request=user_request,
            knowledge_store=self.knowledge_store,
            provider=self.provider,
            model=self.model,
            result_summary=result_summary,
        )

    async def evaluate_and_structure_knowledge(
        self, key: str, request: str, steps: list[dict], result: str,
    ) -> dict[str, Any]:
        """Evaluate new knowledge using LLM and structure it into formal fields."""
        return await kj.evaluate_and_structure_knowledge(
            key, request, steps, result,
            provider=self.provider,
            model=self.model,
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
        return await kj.adapt_knowledge(
            match=match,
            current_request=current_request,
            provider=self.provider,
            model=self.model,
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
        return kb_cmd.delete_knowledge(self.knowledge_store, key, lang)

    def cleanup_knowledge(self, lang: str | None = None) -> str:
        """Find and merge duplicate/similar knowledge base entries."""
        return kb_cmd.cleanup_knowledge(self.knowledge_store, lang)
