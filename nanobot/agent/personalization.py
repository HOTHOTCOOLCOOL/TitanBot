"""Personalization subsystem: Memory Distiller."""

import json
import re

import json_repair
from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.providers.base import LLMProvider

class MemoryDistiller:
    """
    Extracts L1 Core Preferences (JSON) from L2 Long-Term Memory (Markdown).
    
    This solves the context window bloat by ensuring only highly condensed,
    globally applicable facts are injected into the System Prompt.
    """

    def __init__(self, memory: MemoryStore, provider: LLMProvider, model: str):
        self.memory = memory
        self.provider = provider
        self.model = model

    async def distill_preferences(self) -> None:
        """
        Read the bulky MEMORY.md and distill it into a strict JSON structure
        for preferences.json.
        """
        long_term_memory = self.memory.read_long_term()
        
        if not long_term_memory.strip():
            logger.debug("Memory Distiller: MEMORY.md is empty, skipping distillation.")
            return

        current_preferences = self.memory.read_preferences()

        prompt = f"""You are an expert Memory Distiller for an AI Assistant.
Your job is to read the user's verbose Long-Term Memory (L2) and existing core preferences (L1), and extract ONLY the most critical, globally applicable facts into a highly concise JSON format.

RULES:
1. ONLY include durable facts that affect HOW the AI should behave globally (e.g., "Always reply in markdown", "User's name is David", "User prefers concise answers", "Current active project is Nanobot").
2. DO NOT include one-time events, completed task summaries, or historical logs (e.g., "On Jan 1st, I wrote a script" -> EXCLUDE).
3. The output MUST be severely condensed. If a fact isn't actively useful for day-to-day conversation, drop it.
4. Keep the output under 200 words if possible.

## Current L1 Preferences (JSON)
{current_preferences or "{}"}

## Bulky L2 Long-Term Memory (Markdown)
{long_term_memory}

Generate a single flat JSON object where keys are the categories (e.g., "identity", "style_preferences", "active_context", "facts") and values are arrays of concise strings.
Respond with ONLY valid JSON, no markdown fences."""

        try:
            logger.info("Memory Distiller: Starting background distillation process...")
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a JSON-only memory distillation agent."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            
            text = (response.content or "").strip()
            
            # Remove <think> tags if reasoning model leaked them
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                
            result = json_repair.loads(text)
            
            if not isinstance(result, dict):
                logger.error(f"Memory Distiller: Expected dict, got {type(result)}. Content: {text[:100]}")
                return
                
            # If the distillation is effectively empty but memory isn't, just log it.
            if not any(result.values()):
                logger.info("Memory Distiller: No durable globally applicable facts found to extract.")
                
            formatted_json = json.dumps(result, ensure_ascii=False, indent=2)
            self.memory.write_preferences(formatted_json)
            logger.info("Memory Distiller: Successfully updated preferences.json (L1 Memory).")
            
        except Exception as e:
            logger.error(f"Memory Distiller failed: {e}")
