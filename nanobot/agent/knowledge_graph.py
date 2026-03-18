"""Lightweight Entity-Relation Graph for structured memory."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
import json_repair

from nanobot.providers.base import LLMProvider
from nanobot.agent.task_knowledge import tokenize_key

class KnowledgeGraph:
    """Manages a lightweight Triples entity-relation graph stored in graph.json."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.graph_file = workspace / "memory" / "graph.json"
        
        # Structure: {"triples": [{"subject": "A", "predicate": "B", "object": "C", "timestamp": "...", "confidence": 1.0}]}
        self._triples: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load graph from disk."""
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text(encoding="utf-8"))
                self._triples = data.get("triples", [])
            except Exception as e:
                logger.error(f"Failed to load knowledge graph: {e}")
                self._triples = []
        else:
            self._triples = []

    def _save(self) -> None:
        """Save graph to disk (S5: atomic write via temp + rename)."""
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "triples": self._triples,
            "updated_at": datetime.now().isoformat()
        }
        content = json.dumps(data, indent=2, ensure_ascii=False)
        # S5: Write to temp file then atomic rename to prevent corruption
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.graph_file.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(self.graph_file))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _add_triple(self, subject: str, predicate: str, obj: str, confidence: float = 1.0) -> None:
        """Add a triple, avoiding exact duplicates."""
        subject = subject.strip()
        predicate = predicate.strip()
        obj = obj.strip()
        
        # Check for duplicates
        for t in self._triples:
            if (t.get("subject", "").lower() == subject.lower() and 
                t.get("predicate", "").lower() == predicate.lower() and 
                t.get("object", "").lower() == obj.lower()):
                # Already exists, just update timestamp
                t["timestamp"] = datetime.now().isoformat()
                return

        triple = {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "timestamp": datetime.now().isoformat(),
            "confidence": confidence
        }
        self._triples.append(triple)
        self._save()

    async def extract_triples(self, provider: LLMProvider, model: str, text: str) -> None:
        """Extract triples from consolidated memory/history text using LLM."""
        if not text.strip():
            return
            
        prompt = f"""You are a Knowledge Graph Entity Extraction Engine.
Extract core structured facts from the following text as a list of Subject-Predicate-Object triples.

Focus on durable facts: people, organizations, preferences, configurations, important locations, and explicit rules.

Text:
\"\"\"{text}\"\"\"

Return ONLY a valid JSON array of objects, where each object has "subject", "predicate", and "object" keys. Keep values concise (1-5 words).
Example:
[
  {{"subject": "David", "predicate": "works for", "object": "Salesforce"}},
  {{"subject": "Server backend", "predicate": "uses", "object": "Python FastAPI"}}
]

Do not include markdown fences."""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a Triple extraction engine. Return only a JSON array."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.1,
            )
            resp_text = (response.content or "").strip()
            # S6: Strip think tags reliably
            from nanobot.utils.think_strip import strip_think_tags
            resp_text = strip_think_tags(resp_text)
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json_repair.loads(resp_text)
            
            if isinstance(result, list):
                added = 0
                for item in result:
                    if isinstance(item, dict) and "subject" in item and "predicate" in item and "object" in item:
                        self._add_triple(str(item["subject"]), str(item["predicate"]), str(item["object"]))
                        added += 1
                if added > 0:
                    self._save()
                    logger.info(f"KnowledgeGraph: extracted and saved {added} triples.")
            else:
                logger.warning(f"KnowledgeGraph extraction failed, invalid JSON list: {result}")
        except Exception as e:
            logger.error(f"KnowledgeGraph triple extraction failed: {e}")

    def get_1hop_context(self, query: str) -> str:
        """Extract entities from the query using basic tokenization and return 1-hop connected facts."""
        if not self._triples:
            return ""
            
        # Very simple entity matching - tokenize query, if token is in subject/object, we consider it a hit.
        # Prefer longer tokens/phrases if possible, but for lightweight we just check token overlap.
        query_words = set(tokenize_key(query.lower()))
        if not query_words:
            return ""

        matched_triples = []
        for t in self._triples:
            subj = str(t.get("subject", "")).lower()
            obj = str(t.get("object", "")).lower()
            
            subj_words = set(tokenize_key(subj))
            obj_words = set(tokenize_key(obj))
            
            # Substring match (high confidence)
            if subj in query.lower() or obj in query.lower():
                matched_triples.insert(0, t)
            # Token overlap match (low confidence backstop)
            elif (query_words & subj_words) or (query_words & obj_words):
                matched_triples.append(t)

        if not matched_triples:
            return ""
            
        # Deduplicate
        seen = set()
        unique_matches = []
        for t in matched_triples:
            k = (t.get("subject"), t.get("predicate"), t.get("object"))
            if k not in seen:
                seen.add(k)
                unique_matches.append(t)
                # Cap at top 10 facts to avoid context bloat
                if len(unique_matches) >= 10:
                    break

        facts = [f"- {t.get('subject')} {t.get('predicate')} {t.get('object')}." for t in unique_matches]
        return "## Entity Graph Connections\n" + "\n".join(facts)
