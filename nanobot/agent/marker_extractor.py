"""Marker Extractor for K-V Decoupled Indexing (Phase 51).

Implements the M-RAG pattern where Retrieval Keys (short intentional queries)
are decoupled from Generation Values (rich context blocks).
Uses a strict deterministic cache to prevent LLM hallucination and limit token costs.
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.loader import get_config


@dataclass
class MetaMarker:
    key: str
    value: str
    source_hash: str
    paragraphs: list[int]


class MarkerExtractor:
    """Extracts MetaMarkers from documents using a zero-shot LLM approach."""

    def __init__(self, workspace: Path | str, provider: Any = None, model: str | None = None):
        self.workspace = Path(workspace)
        self.cache_dir = self.workspace / ".marker_cache"
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.provider = provider
        self.model = model

    def _compute_hash(self, content: str, version: str) -> str:
        """Compute SHA256 of content + prompt version."""
        raw = f"{version}::{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def extract(self, content: str, source: str) -> list[MetaMarker] | None:
        """Extract MetaMarkers from text. Returns None if coverage is too low or error (to fallback to chunking)."""
        config = get_config()
        if not config.features.marker_indexing:
            return None

        prompt_version = config.features.marker_prompt_version
        content_hash = self._compute_hash(content, prompt_version)
        cache_file = self.cache_dir / f"{content_hash}.json"

        # Check Cache
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return [MetaMarker(**m) for m in data]
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.warning(f"Failed to read marker cache {cache_file}: {e}")

        # Split into original paragraphs to evaluate coverage later
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            return None

        if not self.provider or not self.model:
            return None

        prompt = f"""You are a MetaMarker extractor for semantic search optimization.
Extract key-value pairs from the document, decoupling the retrieval intent (key) from the generation context (value).

Extraction Rules:
1. Granularity: Each meta-marker should cover 1-3 paragraphs.
2. Resolve Pronouns: Replace any pronouns (he/it/that) with explicit names.
3. 'value': A 200-300 word focused context block, covering a single coherent theme.
4. 'key': A detailed query that acts as an intent summary and retrieval anchor. Include specific entities, dates, and numbers.
5. 'paragraphs': An array of integers representing the 0-based index of the original paragraphs this marker covers. Must be valid indices [0 to {len(paragraphs) - 1}].

Original Document Paragraphs (with 0-based indices):
"""
        for i, para in enumerate(paragraphs):
            prompt += f"[{i}] {para}\n\n"

        prompt += """
Return ONLY a valid JSON array of objects.
Format:
[
  {
    "key": "Why was the Q3 revenue target missed by ACME Corp?",
    "value": "ACME Corp missed its Q3 revenue target primarily due to supply chain disruptions in the APAC region causing a 12% drop in component fulfillment...",
    "paragraphs": [0, 1]
  }
]
"""
        try:
            import asyncio
            response = await asyncio.wait_for(
                self.provider.chat(
                    messages=[
                        {"role": "system", "content": "You are a precise JSON extraction component. Do not include markdown formatting or explanations. Output pure JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                    temperature=0.1,
                    max_tokens=4000,
                ),
                timeout=60.0,
            )

            resp_text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            resp_text = strip_think_tags(resp_text)
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            import json_repair
            extracted = json_repair.loads(resp_text)

            if not isinstance(extracted, list):
                logger.warning("Marker extraction failed: output is not a list")
                return None

            markers = []
            covered_indices = set()
            for m in extracted:
                if not isinstance(m, dict) or "key" not in m or "value" not in m or "paragraphs" not in m:
                    continue
                paras = m["paragraphs"]
                if not isinstance(paras, list):
                    continue

                # Sanitize paragraphs
                valid_paras = [idx for idx in paras if isinstance(idx, int) and 0 <= idx < len(paragraphs)]
                if not valid_paras:
                    continue

                covered_indices.update(valid_paras)

                markers.append(MetaMarker(
                    key=str(m["key"]),
                    value=str(m["value"]),
                    source_hash=content_hash,
                    paragraphs=valid_paras
                ))

            # Coverage evaluation
            coverage = len(covered_indices) / len(paragraphs) if paragraphs else 0
            if coverage < 0.95:
                logger.warning(f"Marker coverage too low ({coverage:.1%} < 95%). Falling back to chunking for '{source}'.")
                return None

            if not markers:
                return None

            # Persist to cache
            cache_file.write_text(json.dumps([asdict(m) for m in markers], indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Successfully generated {len(markers)} markers for '{source}' via LLM.")
            return markers

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Failed to generate MetaMarkers via LLM: {e}")
            return None
