"""Metacognitive Reflection Memory for agent self-improvement."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
import json_repair

from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session
from nanobot.agent.task_knowledge import tokenize_key


class ReflectionStore:
    """Store and manage negative feedback reflections."""

    # E2: Maximum number of reflections before auto-pruning
    MAX_REFLECTIONS = 100

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.reflections_file = workspace / "memory" / "reflections.json"
        self._reflections: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load reflections from disk."""
        if self.reflections_file.exists():
            try:
                data = json.loads(self.reflections_file.read_text(encoding="utf-8"))
                self._reflections = data.get("reflections", [])
            except Exception as e:
                logger.error(f"Failed to load reflections: {e}")
                self._reflections = []
        else:
            self._reflections = []

    def _save(self) -> None:
        """Save reflections to disk (S5: atomic write via temp + rename)."""
        self.reflections_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "reflections": self._reflections,
            "updated_at": datetime.now().isoformat()
        }
        content = json.dumps(data, indent=2, ensure_ascii=False)
        # S5: Write to temp file then atomic rename to prevent corruption
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.reflections_file.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(self.reflections_file))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def add_reflection(self, trigger: str, failure_reason: str, corrective_action: str) -> None:
        """Add a new reflection."""
        reflection = {
            "trigger": trigger,
            "failure_reason": failure_reason,
            "corrective_action": corrective_action,
            "timestamp": datetime.now().isoformat()
        }
        self._reflections.append(reflection)
        # E2: Auto-prune if over capacity
        if len(self._reflections) > self.MAX_REFLECTIONS:
            self._prune()
        self._save()
        logger.info(f"Added new reflection: {trigger}")

    @property
    def count(self) -> int:
        """Return the number of stored reflections."""
        return len(self._reflections)

    def _prune(self) -> int:
        """E2: Remove oldest reflections to stay within MAX_REFLECTIONS.

        Returns:
            Number of reflections removed.
        """
        if len(self._reflections) <= self.MAX_REFLECTIONS:
            return 0
        before = len(self._reflections)
        self._reflections = self._reflections[-self.MAX_REFLECTIONS:]
        removed = before - len(self._reflections)
        logger.info(f"ReflectionStore: pruned {removed} oldest reflections (cap={self.MAX_REFLECTIONS})")
        return removed

    def prune(self) -> int:
        """Public prune API — trims and saves."""
        removed = self._prune()
        if removed > 0:
            self._save()
        return removed

    def search_reflections(self, query: str, top_k: int = 2) -> list[dict[str, Any]]:
        """Simple substring / Jaccard similarity search for relevant reflections."""
        if not self._reflections:
            return []

        query_words = set(tokenize_key(query.lower()))
        if not query_words:
            return []

        scored = []
        for ref in self._reflections:
            trigger_lower = ref.get("trigger", "").lower()
            trigger_words = set(tokenize_key(trigger_lower))
            if not trigger_words:
                continue
            
            # Jaccard similarity
            intersection = query_words & trigger_words
            union = query_words | trigger_words
            score = len(intersection) / len(union) if union else 0

            # Boost score if exact substring match
            if trigger_lower in query.lower() or query.lower() in trigger_lower:
                score += 0.5

            if score > 0.1:
                scored.append((score, ref))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ref for score, ref in scored[:top_k]]

    async def generate_reflection(self, provider: LLMProvider, model: str, session: Session, user_feedback: str) -> None:
        """Generate and store a reflection using LLM based on recent failed interaction."""
        recent_messages = session.get_history(max_messages=6)
        
        conversation = []
        for m in recent_messages:
            content = m.get("content")
            if not content:
                continue
            if isinstance(content, list):
                # Handle multimodal
                text = " ".join([str(b.get("text", "")) for b in content if b.get("type") == "text"])
                content = text
            tools = f" [tools: {', '.join(m.get('tools_used', []))}]" if m.get("tools_used") else ""
            conversation.append(f"{m['role'].upper()}{tools}: {content}")
            
        if not conversation:
            return
            
        conv_text = "\n".join(conversation)
        
        prompt = f'''You are a metacognitive component of an AI agent. The agent just failed a task or received negative feedback from the user.
        
Analyze the recent conversation and generate a reflection to avoid repeating this mistake.

Recent Conversation:
{conv_text}

User's Negative Feedback:
{user_feedback}

Return ONLY a valid JSON object with the following three keys:
- "trigger": The specific user intent, query, or context that led to the failure (a short sentence or phrase).
- "failure_reason": Exactly what went wrong (e.g., used wrong tool, lacked parameters, hallucinated).
- "corrective_action": How to correctly handle this trigger in the future. Give concrete instructions (e.g., "Must use X tool with Y parameters").

No markdown fences around the JSON.'''

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a metacognitive component. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.2,
            )
            text = (response.content or "").strip()
            # S6: Strip think tags from reasoning models (reliable utility)
            from nanobot.utils.think_strip import strip_think_tags
            text = strip_think_tags(text)
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json_repair.loads(text)
            
            if isinstance(result, dict) and all(k in result for k in ["trigger", "failure_reason", "corrective_action"]):
                self.add_reflection(
                    result["trigger"],
                    result["failure_reason"],
                    result["corrective_action"]
                )
                logger.info("Successfully generated metacognitive reflection.")
            else:
                logger.warning(f"Invalid JSON structure for reflection: {result}")
        except Exception as e:
            logger.error(f"Metacognitive reflection generation failed: {e}")
