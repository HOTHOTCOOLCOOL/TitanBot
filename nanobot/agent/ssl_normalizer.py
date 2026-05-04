"""LLM-backed normalizer for SKILL.md -> SSL graphs."""

import asyncio
from typing import Any

import json_repair
from loguru import logger

from nanobot.providers.base import LLMProvider
from nanobot.utils.think_strip import strip_think_tags


class SkillNormalizer:
    """Normalize raw skill text into a strict Scheduling/Structural/Logical graph."""

    _REQUIRED_KEYS = ("Scheduling", "Structural", "Logical")

    def __init__(self, provider: LLMProvider | None = None, model: str | None = None):
        self.provider = provider
        self.model = model

    async def normalize(self, skill_name: str, skill_text: str) -> dict[str, Any] | None:
        """Return a strict SSL graph or None on any parse/provider failure."""
        if self.provider is None:
            logger.warning(f"SkillNormalizer: missing provider for skill '{skill_name}'")
            return None

        prompt = f"""You are an SSL normalizer for agent skills.
Convert the following SKILL.md content into a JSON object with exactly three top-level keys:
"Scheduling", "Structural", and "Logical".

Constraints:
- Return ONLY valid JSON.
- Each top-level key must map to a JSON object.
- Preserve only actionable operational structure from the skill.
- Do not include markdown fences or commentary.

Skill name: {skill_name}

SKILL.md:
\"\"\"{skill_text}\"\"\""""

        try:
            response = await self.provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You convert SKILL.md files into strict SSL JSON. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.0,
            )
            raw = strip_think_tags((response.content or "").strip())
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"SkillNormalizer: fail-closed for '{skill_name}': {exc}")
            return None

        if not isinstance(result, dict):
            logger.warning(
                f"SkillNormalizer: invalid SSL payload type for '{skill_name}': {type(result).__name__}"
            )
            return None

        graph: dict[str, Any] = {}
        for key in self._REQUIRED_KEYS:
            value = result.get(key)
            if not isinstance(value, dict):
                logger.warning(
                    f"SkillNormalizer: missing or invalid '{key}' section for '{skill_name}'"
                )
                return None
            graph[key] = value

        return graph
