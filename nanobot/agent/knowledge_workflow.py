"""Knowledge Workflow Engine.

Implements the user's desired knowledge base workflow:
1. Extract a task Key from user request (via lightweight LLM call)
2. Code-level comparison against stored knowledge base entries
3. If match found: ask user to reuse or re-execute
4. After task completion: prompt to save/update knowledge base
"""

from typing import Any

from loguru import logger

from nanobot.agent.i18n import msg
from nanobot.agent.task_knowledge import TaskKnowledgeStore, tokenize_key
from nanobot.agent.hybrid_retriever import hybrid_retrieve
from nanobot.utils.metrics import metrics

from nanobot.agent import command_recognition as cmd_rec
from nanobot.agent import prompt_formatter as prompt_fmt
from nanobot.agent import outcome_tracker as out_trk
from nanobot.agent import kb_commands as kb_cmd


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
    # 1. Key Extraction (lightweight LLM call)
    # ----------------------------------------------------------------

    async def extract_key(self, user_request: str, history: list[dict] | None = None) -> str:
        """Extract a task key from user request using a lightweight LLM call.

        The key should be:
        - Chinese: ≤50 characters
        - English: ≤200 characters
        - A concise description of the task's core intent

        Returns:
            Extracted key string, or a truncated version of the request as fallback.
        """
        if not self.provider:
            return self._fallback_key(user_request)

        prompt_parts = [
            "Extract a concise task description from the user request below. ",
            "Rules:\n",
            "- If the request is in Chinese, output ≤50 Chinese characters\n",
            "- If the request is in English, output ≤200 English characters\n",
            "- Output ONLY the key text, nothing else\n",
            "- Focus on the core action and target\n",
        ]

        if history:
            prompt_parts.append("\nRecent conversation history (for context and coreference resolution):\n")
            # Only include the last 5 turns to save tokens
            for msg in history[-5:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # Only take text content up to 500 chars per message to avoid bloat
                if isinstance(content, str):
                    prompt_parts.append(f"[{role}]: {content[:500]}\n")
                elif isinstance(content, list):
                    # Handle multimodal content simply
                    text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    text_content = " ".join(text_parts)
                    prompt_parts.append(f"[{role}]: {text_content[:500]}\n")

        prompt_parts.append(f"\nUser request: {user_request}\n\nKey:")
        prompt = "".join(prompt_parts)

        try:
            response = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.1,
                max_tokens=100,
            )
            content = response.content or ""
            # S6: Strip <think>...</think> tags reliably
            from nanobot.utils.think_strip import strip_think_tags
            content = strip_think_tags(content)
            key = content.strip().strip('"').strip("'")
            if key:
                logger.info(f"KnowledgeWorkflow: extracted key = '{key}'")
                return key
        except Exception as e:
            logger.warning(f"KnowledgeWorkflow: key extraction failed: {e}")

        return self._fallback_key(user_request)

    def _fallback_key(self, user_request: str) -> str:
        """Fallback key extraction without LLM — simple truncation."""
        # Heuristic: if mostly CJK chars, limit to 50; otherwise 200
        cjk_count = sum(1 for c in user_request if '\u4e00' <= c <= '\u9fff')
        limit = 50 if cjk_count > len(user_request) * 0.3 else 200
        return user_request[:limit].strip()

    # ----------------------------------------------------------------
    # 2. Knowledge Base Matching (pure code, no LLM)
    # ----------------------------------------------------------------

    def match_knowledge(self, key: str) -> dict[str, Any] | None:
        """Match extracted key against knowledge base entries.

        Matching strategy (in order of priority):
        1. Exact match (key strings identical)
        2. Substring match (one key contains the other)
        3. Common-word similarity (>= 50% shared words)

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
            return best_substring

        # Pass 3: True Hybrid Retrieval (Dense + BM25)
        best_hybrid_match, best_hybrid_score = hybrid_retrieve(
            query=key,
            candidates=tasks,
            text_field="key",
            extra_text_field="triggers",
            match_key_field="key",
            vector_memory=self.vector_memory if self.knowledge_store else None,
            vector_source_filter="knowledge",
            threshold=0.6,
        )

        if best_hybrid_match:
            logger.info(
                f"KnowledgeWorkflow: hybrid match found: "
                f"'{best_hybrid_match.get('key')}' (score={best_hybrid_score:.2f})"
            )
            return best_hybrid_match

        logger.debug(f"KnowledgeWorkflow: no match found for key '{key}'")
        return None

    def match_experience(self, action_context: str) -> str | None:
        """Find action-level tactical prompts from the Experience Bank (P12 feature).
        
        Args:
            action_context: The current context of the agent's action (e.g., tool name, error message).
             
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
            no_dense_penalty=1.0,  # Don't penalize experience matches without dense scores
        )

        if best_match:
            logger.info(
                f"KnowledgeWorkflow: experience match found: "
                f"'{best_match.get('trigger')}' (score={best_score:.2f})"
            )
            return best_match.get("prompt")
            
        return None

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for word-similarity matching.

        Delegates to the shared tokenize_key() function in task_knowledge.
        """
        return tokenize_key(text)

    # ----------------------------------------------------------------
    # 3. User Command Recognition
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
    # 4. Prompt Formatting
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
    # 5. Knowledge Base Save / Update
    # ----------------------------------------------------------------

    async def save_to_knowledge(
        self,
        key: str,
        steps: list[dict],
        user_request: str,
        result_summary: str = "",
    ) -> bool:
        """Save or update a task in the knowledge base.

        Strategy (P0 — auto-merge):
        1. Exact key match → merge into existing entry (version++)
        2. Similar key found → merge into similar entry (avoid duplicates)
        3. No match → create new entry

        Args:
            key: Task key (extracted by extract_key).
            steps: List of tool call dicts [{tool, args}, ...].
            user_request: Original user request text.
            result_summary: Summary of the task result.

        Returns:
            True if saved successfully.
        """
        if not self.knowledge_store:
            logger.warning("KnowledgeWorkflow: no knowledge store available")
            return False

        try:
            # Phase 12: Knowledge Judge evaluation (LLM)
            judge_result = await self.evaluate_and_structure_knowledge(key, user_request, steps, result_summary)
            decision = judge_result.get("decision", "ADD")
            
            if decision == "DISCARD":
                logger.info(f"KnowledgeWorkflow Judge: discarded new knowledge for '{key}'")
                return True

            triggers = judge_result.get("triggers", [])
            tags = judge_result.get("tags", [])
            anti_patterns = judge_result.get("anti_patterns", [])
            confidence = judge_result.get("confidence", 1.0)

            # 1. Exact key match → merge
            existing = self.knowledge_store.find_task(key)
            if existing or decision == "MERGE":
                target_key = existing.get("key") if existing else key
                # If decision was MERGE but exact key didn't match, try to find a similar one
                if not existing and decision == "MERGE":
                    similar = self.knowledge_store.find_similar_task(key)
                    if similar:
                        target_key = similar.get("key", key)
                        
                self.knowledge_store.merge_task(
                    existing_key=target_key,
                    new_steps=steps,
                    new_result_summary=result_summary or "Task completed",
                    new_steps_detail=steps,
                    new_triggers=triggers,
                    new_tags=tags,
                    new_anti_patterns=anti_patterns,
                    new_confidence=confidence,
                )
                logger.info(f"KnowledgeWorkflow: merged for key='{target_key}'")
                return True

            # 2. Similar key match → merge (fallback if judge said ADD but there's a very similar one)
            similar = self.knowledge_store.find_similar_task(key)
            if similar:
                similar_key = similar.get("key", "")
                self.knowledge_store.merge_task(
                    existing_key=similar_key,
                    new_steps=steps,
                    new_result_summary=result_summary or "Task completed",
                    new_steps_detail=steps,
                    new_triggers=triggers,
                    new_tags=tags,
                    new_anti_patterns=anti_patterns,
                    new_confidence=confidence,
                )
                logger.info(f"KnowledgeWorkflow: merged (similar) '{key}' → '{similar_key}'")
                return True

            # 3. No match → create new
            self.knowledge_store.add_task(
                key=key,
                description=user_request[:100],
                steps=steps,
                params={},
                result_summary=result_summary or "Task completed",
                triggers=triggers,
                tags=tags,
                anti_patterns=anti_patterns,
                confidence=confidence,
            )
            logger.info(f"KnowledgeWorkflow: saved new knowledge for key='{key}'")
            return True
        except Exception as e:
            logger.error(f"KnowledgeWorkflow: save failed: {e}")
            metrics.increment("knowledge_save_error_count")
            return False

    async def evaluate_and_structure_knowledge(self, key: str, request: str, steps: list[dict], result: str) -> dict[str, Any]:
        """Evaluate new knowledge using LLM and structure it into formal fields.
        
        Returns a dict:
            decision: "ADD", "MERGE", or "DISCARD"
            triggers: list of strings
            tags: list of strings
            anti_patterns: list of strings
            confidence: float (0.0 - 1.0)
        """
        default_result = {
            "decision": "ADD",
            "triggers": [key],
            "tags": [],
            "anti_patterns": [],
            "confidence": 0.8
        }
        
        if not self.provider:
            return default_result
            
        # Format the task representation
        task_str = f"Task Key: {key}\nOriginal Request: {request}\nSteps: {steps}\nResult: {result}"
        
        prompt = f"""
You are the Knowledge Management Judge for a personal AI assistant.
Your job is to evaluate a newly completed workflow and structure it for the Knowledge Base.

Workflow Data:
{task_str}

Tasks:
1. DECISION: Decide if this knowledge should be ADDed as new, MERGEd with existing, or DISCARDed entirely (if trivial, completely erroneous, or empty).
2. TRIGGERS: Extract 2-3 short, distinct trigger phrases the user might say next time to request this.
3. TAGS: 1-3 broad categorization tags (e.g., 'email', 'system', 'research').
4. ANTI-PATTERNS: 1-2 warnings or mistakes to avoid when running this workflow in the future (based on the steps or result). If none, empty array.
5. CONFIDENCE: Give a confidence score (0.0 to 1.0) on how reliable and generalizable this workflow is.

Return your evaluation EXACTLY as a JSON object, with no markdown formatting around it:
{{
    "decision": "ADD|MERGE|DISCARD",
    "triggers": ["trigger1", "trigger2"],
    "tags": ["tag1", "tag2"],
    "anti_patterns": ["anti_pattern1"],
    "confidence": 0.9
}}
"""
        import json
        try:
            response = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.1,
                max_tokens=300,
            )
            content = response.content or ""
            # S6: Strip markdown and any <think> tags
            from nanobot.utils.think_strip import strip_think_tags
            content = strip_think_tags(content)
            content = content.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(content)
            
            # Merge with defaults to ensure all keys exist
            return {**default_result, **parsed}
        except Exception as e:
            logger.warning(f"Knowledge Judge failed, using defaults: {e}")
            metrics.increment("knowledge_judge_fallback_count")
            return default_result

    def get_knowledge_result(self, match: dict, lang: str | None = None) -> str:
        """Format and return the stored result of a matched knowledge entry."""
        return prompt_fmt.get_knowledge_result(match, lang)

    # ----------------------------------------------------------------
    # 6. Outcome Tracking (implicit feedback)
    # ----------------------------------------------------------------

    @classmethod
    def is_negative_feedback(cls, text: str) -> bool:
        """Check if user message implies the previous task failed."""
        return out_trk.is_negative_feedback(text)

    def record_outcome(self, key: str, success: bool) -> None:
        """Record task outcome (success or failure) in knowledge base."""
        out_trk.record_outcome(self.knowledge_store, key, success)

    # ----------------------------------------------------------------
    # 7. Few-shot Prompt Generation (for local model accuracy)
    # ----------------------------------------------------------------

    def format_few_shot_prompt(self, match: dict) -> str:
        """Generate a few-shot reference prompt from a high-success knowledge entry."""
        return prompt_fmt.format_few_shot_prompt(match)

    async def adapt_knowledge(self, match: dict, current_request: str, history: list[dict] | None = None) -> str:
        """Adapt a retrieved knowledge entry into a tailored few-shot prompt for the current context.

        This uses a lightweight LLM call to rewrite the generic steps from the knowledge
        base into a specific, actionable reference for the current request.
        """
        if not self.provider:
            return self.format_few_shot_prompt(match)

        key = match.get("key", "")
        steps_detail = match.get("last_steps_detail", [])
        steps = match.get("steps", [])

        if not steps_detail and not steps:
            return ""

        # Construct generic reference first
        generic_prompt = self.format_few_shot_prompt(match)

        prompt_parts = [
            f"You are given a previously successful workflow for the task: '{key}'.\n",
            "Adapt this generic workflow to fit the NEW current user request.\n",
            "Rules:\n",
            "- Extract specific parameters (paths, names, URLs, etc.) from the new request or history.\n",
            "- Replace the old parameters in the generic workflow with the new ones.\n",
            "- Keep the output concise, focusing purely on the modified steps.\n",
            "- Output a markdown formatted reference list of steps.\n\n",
        ]

        if history:
            prompt_parts.append("Recent conversation history (for additional context):\n")
            for msg in history[-5:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt_parts.append(f"[{role}]: {content[:500]}\n")
                elif isinstance(content, list):
                    text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    text_content = " ".join(text_parts)
                    prompt_parts.append(f"[{role}]: {text_content[:500]}\n")

        prompt_parts.append(f"\nUser request: {current_request}\n")
        prompt_parts.append(f"\nGeneric workflow to adapt:\n{generic_prompt}\n\nAdapted workflow:")
        prompt = "".join(prompt_parts)

        try:
            response = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.1,
                max_tokens=300,
            )
            content = response.content or ""
            from nanobot.utils.think_strip import strip_think_tags
            content = strip_think_tags(content)
            adapted = content.strip()
            if adapted:
                logger.info(f"KnowledgeWorkflow: successfully adapted knowledge for '{key}'")
                return f"## Contextual Reference: Adapted from '{key}'\n\n{adapted}"
        except Exception as e:
            logger.warning(f"KnowledgeWorkflow: adaptation failed: {e}")

        # Fallback to the generic prompt if LLM fails or returns empty
        return generic_prompt

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
    # 9. Silent Steps Update (P1)
    # ----------------------------------------------------------------

    def silent_update_steps(self, key: str, tool_calls: list[dict]) -> bool:
        """Silently update steps_detail for a task after successful execution."""
        return out_trk.silent_update_steps(self.knowledge_store, key, tool_calls)

    # ----------------------------------------------------------------
    # 10. Knowledge Base Management Commands (P2)
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

