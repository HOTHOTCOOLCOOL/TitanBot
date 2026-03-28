"""Lightweight Entity-Relation Graph for structured memory.

Phase 24 (MDER-DR): Enhanced with triple descriptions, entity disambiguation,
entity-centric summaries, query decomposition, and semantic chunking.
"""

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
import json_repair

from nanobot.providers.base import LLMProvider
from nanobot.agent.task_knowledge import tokenize_key
from nanobot.utils.helpers import safe_replace


class KnowledgeGraph:
    """Manages a lightweight Triples entity-relation graph stored in graph.json.

    Schema (Phase 24):
        {
            "triples": [
                {
                    "subject": str,
                    "predicate": str,
                    "object": str,
                    "description": str,     # KG1: natural language context
                    "timestamp": str,
                    "confidence": float
                }
            ],
            "entities": {                   # KG3: entity-centric summaries
                "David Liu": {
                    "type": str,
                    "summary": str,
                    "triple_indices": [int],
                    "updated_at": str
                }
            },
            "aliases": {                    # KG2: entity disambiguation map
                "刘总": "David Liu",
                "David": "David Liu"
            },
            "updated_at": str
        }
    """

    # E2: Maximum number of triples before auto-pruning
    MAX_TRIPLES = 500

    def __init__(self, workspace: Path, vector_memory: Any = None):
        self.workspace = workspace
        self.vector_memory = vector_memory
        self.graph_file = workspace / "memory" / "graph.json"

        # Structure
        self._triples: list[dict[str, Any]] = []
        self._entities: dict[str, dict[str, Any]] = {}   # KG3
        self._aliases: dict[str, str] = {}                # KG2
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load graph from disk."""
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text(encoding="utf-8"))
                self._triples = data.get("triples", [])
                self._entities = data.get("entities", {})
                self._aliases = data.get("aliases", {})
            except Exception as e:
                logger.error(f"Failed to load knowledge graph: {e}")
                self._triples = []
                self._entities = {}
                self._aliases = {}
        else:
            self._triples = []
            self._entities = {}
            self._aliases = {}

    def _save(self) -> None:
        """Save graph to disk (S5: atomic write via temp + rename)."""
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "triples": self._triples,
            "entities": self._entities,
            "aliases": self._aliases,
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
            safe_replace(tmp_path, str(self.graph_file))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── Triple Management ───────────────────────────────────────────────

    def _normalize_entity(self, name: str) -> str:
        """KG2: Normalize an entity name via alias lookup and stripping."""
        name = name.strip()
        # Check alias map (case-insensitive)
        lower = name.lower()
        for alias, canonical in self._aliases.items():
            if alias.lower() == lower:
                return canonical
        return name

    def _add_triple(
        self, subject: str, predicate: str, obj: str,
        confidence: float = 1.0, description: str = ""
    ) -> None:
        """Add a triple, avoiding exact duplicates. KG1: supports description."""
        subject = self._normalize_entity(subject)
        predicate = predicate.strip()
        obj = self._normalize_entity(obj)

        # Check for duplicates (case-insensitive on s/p/o)
        for t in self._triples:
            if (t.get("subject", "").lower() == subject.lower() and
                t.get("predicate", "").lower() == predicate.lower() and
                t.get("object", "").lower() == obj.lower()):
                # Already exists — update timestamp and description if richer
                t["timestamp"] = datetime.now().isoformat()
                if description and (not t.get("description") or len(description) > len(t.get("description", ""))):
                    t["description"] = description
                return

        triple: dict[str, Any] = {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "confidence": confidence
        }
        self._triples.append(triple)
        # E2: Auto-prune if over capacity
        if len(self._triples) > self.MAX_TRIPLES:
            self._prune()
        # F5/Phase 25: Removed per-triple _save() — callers (extract_triples,
        # add_alias) already handle persistence after batch operations.

    @property
    def count(self) -> int:
        """Return the number of stored triples."""
        return len(self._triples)

    def _prune(self) -> int:
        """E2: Remove oldest triples to stay within MAX_TRIPLES."""
        if len(self._triples) <= self.MAX_TRIPLES:
            return 0
        before = len(self._triples)
        self._triples = self._triples[-self.MAX_TRIPLES:]
        removed = before - len(self._triples)
        logger.info(f"KnowledgeGraph: pruned {removed} oldest triples (cap={self.MAX_TRIPLES})")
        return removed

    def prune(self) -> int:
        """Public prune API — trims and saves."""
        removed = self._prune()
        if removed > 0:
            self._save()
        return removed

    # ── KG5: Semantic Chunking ──────────────────────────────────────────

    @staticmethod
    def _semantic_chunk(text: str, max_chunk_chars: int = 2000) -> list[str]:
        """KG5: Split text at sentence boundaries before triple extraction.

        Uses paragraph breaks and sentence-ending punctuation (. 。 ! ？ ！)
        to split into semantically coherent chunks.
        """
        if len(text) <= max_chunk_chars:
            return [text]

        # Split on paragraph breaks first
        paragraphs = re.split(r'\n{2,}', text)
        chunks: list[str] = []
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= max_chunk_chars:
                current_chunk = (current_chunk + "\n\n" + para).strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If a single paragraph exceeds max, split on sentences
                if len(para) > max_chunk_chars:
                    sentences = re.split(r'(?<=[.。!！?？])\s*', para)
                    sub_chunk = ""
                    for sent in sentences:
                        if len(sub_chunk) + len(sent) + 1 <= max_chunk_chars:
                            sub_chunk = (sub_chunk + " " + sent).strip()
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = sent
                    if sub_chunk:
                        current_chunk = sub_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks if chunks else [text]

    # ── KG1: Triple Extraction with Descriptions ────────────────────────

    async def extract_triples(self, provider: LLMProvider, model: str, text: str) -> None:
        """Extract triples from consolidated memory/history text using LLM.

        KG1: Each triple includes a natural language description preserving
        context (time, conditions, scope) from the source text.
        KG5: Long texts are chunked at sentence boundaries before extraction.
        """
        if not text.strip():
            return

        # KG5: Chunk long texts
        chunks = self._semantic_chunk(text)
        total_added = 0

        for chunk in chunks:
            added = await self._extract_triples_from_chunk(provider, model, chunk)
            total_added += added

        if total_added > 0:
            # KG2: Disambiguate after all new triples are added
            merged = self.disambiguate_entities()
            if merged > 0:
                logger.info(f"KnowledgeGraph: disambiguated {merged} entity aliases")
            # Rebuild entity index after extraction
            self.rebuild_entity_index()
            self._save()
            logger.info(f"KnowledgeGraph: extracted {total_added} triples from {len(chunks)} chunk(s)")

    async def _extract_triples_from_chunk(self, provider: LLMProvider, model: str, text: str) -> int:
        """Extract triples from a single text chunk."""
        prompt = f"""You are a Knowledge Graph Entity Extraction Engine.
Extract core structured facts from the following text as a list of Subject-Predicate-Object triples.
For each triple, also provide a brief natural language "description" that preserves important context
such as time, conditions, scope, or qualifiers from the original text.

Focus on durable facts: people, organizations, preferences, configurations, important locations, and explicit rules.

Text:
\"\"\"{text}\"\"\"

Return ONLY a valid JSON array of objects, where each object has "subject", "predicate", "object", and "description" keys.
Keep subject/predicate/object concise (1-5 words). The description should be 1-2 sentences preserving context.

Example:
[
  {{"subject": "David", "predicate": "works for", "object": "Salesforce", "description": "David has been working for Salesforce since 2020, based in the Shenzhen AI research team."}},
  {{"subject": "Server backend", "predicate": "uses", "object": "Python FastAPI", "description": "The server backend is built with Python FastAPI framework for high-performance async API serving."}}
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
                        desc = str(item.get("description", ""))
                        self._add_triple(
                            str(item["subject"]),
                            str(item["predicate"]),
                            str(item["object"]),
                            description=desc,
                        )
                        added += 1
                return added
            else:
                logger.warning(f"KnowledgeGraph extraction failed, invalid JSON list: {result}")
                return 0
        except Exception as e:
            logger.error(f"KnowledgeGraph triple extraction failed: {e}")
            return 0

    # ── KG2: Entity Disambiguation ──────────────────────────────────────

    def disambiguate_entities(self) -> int:
        """KG2: Merge semantically equivalent entities using lightweight heuristics.

        Strategy:
        1. Collect all unique entity names from triples
        2. Group by substring containment (e.g., "David" ⊂ "David Liu")
        3. Prefer the longer/more specific form as canonical
        4. Update aliases map and rewrite all triples to use canonical names

        Returns:
            Number of new aliases created.
        """
        # Collect all unique entity names
        entities: set[str] = set()
        for t in self._triples:
            entities.add(t.get("subject", ""))
            entities.add(t.get("object", ""))
        entities.discard("")

        # Sort by length descending — longer names are more specific (canonical)
        sorted_entities = sorted(entities, key=len, reverse=True)
        new_aliases = 0

        for i, longer in enumerate(sorted_entities):
            for shorter in sorted_entities[i + 1:]:
                # Skip if already aliased
                if shorter.lower() in {a.lower() for a in self._aliases}:
                    continue
                # Skip very short names (< 2 chars) to avoid false merges
                if len(shorter) < 2:
                    continue
                # Substring containment check (case-insensitive)
                if shorter.lower() in longer.lower() and shorter.lower() != longer.lower():
                    # Additional guard: shorter must be a significant portion (>30%)
                    if len(shorter) / len(longer) < 0.3:
                        continue
                    self._aliases[shorter] = longer
                    new_aliases += 1

        # Rewrite triples to use canonical names
        if new_aliases > 0:
            for t in self._triples:
                subj = t.get("subject", "")
                obj = t.get("object", "")
                t["subject"] = self._normalize_entity(subj)
                t["object"] = self._normalize_entity(obj)

        return new_aliases

    def add_alias(self, alias: str, canonical: str) -> None:
        """Manually add an entity alias."""
        self._aliases[alias.strip()] = canonical.strip()
        # Rewrite existing triples
        for t in self._triples:
            if t.get("subject", "").lower() == alias.strip().lower():
                t["subject"] = canonical.strip()
            if t.get("object", "").lower() == alias.strip().lower():
                t["object"] = canonical.strip()
        self._save()

    # ── KG3: Entity-Centric Summaries ───────────────────────────────────

    def rebuild_entity_index(self) -> dict[str, dict[str, Any]]:
        """KG3: Rebuild entity index from current triples.

        Groups triples by entity (subject/object) and stores triple indices.
        Does NOT regenerate LLM summaries — call generate_entity_summaries() for that.

        Returns:
            The rebuilt entities dict.
        """
        entities: dict[str, dict[str, Any]] = {}

        for idx, t in enumerate(self._triples):
            for field in ("subject", "object"):
                name = t.get(field, "").strip()
                if not name:
                    continue
                if name not in entities:
                    entities[name] = {
                        "type": "",
                        "summary": self._entities.get(name, {}).get("summary", ""),
                        "triple_indices": [],
                        "updated_at": datetime.now().isoformat(),
                    }
                if idx not in entities[name]["triple_indices"]:
                    entities[name]["triple_indices"].append(idx)

        self._entities = entities
        return entities

    async def generate_entity_summaries(self, provider: LLMProvider, model: str) -> int:
        """KG3: Generate LLM summaries for entities that have associated triples.

        For each entity, collects all triple descriptions and asks the LLM
        to produce a concise 1-2 sentence summary.

        Returns:
            Number of entities summarized.
        """
        if not self._triples:
            return 0

        # Rebuild index first to ensure it's current
        self.rebuild_entity_index()

        # Collect entities that need summaries (no summary or stale)
        entities_to_summarize: list[tuple[str, list[str]]] = []
        for name, info in self._entities.items():
            indices = info.get("triple_indices", [])
            if not indices:
                continue
            # Collect descriptions from associated triples
            descriptions = []
            for idx in indices:
                if idx < len(self._triples):
                    t = self._triples[idx]
                    desc = t.get("description", "")
                    fact = f"{t.get('subject', '')} {t.get('predicate', '')} {t.get('object', '')}"
                    descriptions.append(desc if desc else fact)
            if descriptions:
                entities_to_summarize.append((name, descriptions))

        if not entities_to_summarize:
            return 0

        # Batch all entities into one LLM call for efficiency
        entity_blocks = []
        for name, descs in entities_to_summarize[:50]:  # Cap at 50 entities per call
            facts_text = "\n".join(f"  - {d}" for d in descs[:10])  # Cap facts per entity
            entity_blocks.append(f"### {name}\n{facts_text}")

        prompt = f"""You are a Knowledge Graph Summarization Engine.
For each entity below, generate a concise 1-2 sentence summary that captures the key facts.

{chr(10).join(entity_blocks)}

Return ONLY a valid JSON object where each key is the entity name and each value is the summary string.
Example: {{"David Liu": "David Liu is an AI researcher at Salesforce Shenzhen since 2020, focusing on NLP."}}

Do not include markdown fences."""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a summarization engine. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.1,
            )
            resp_text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            resp_text = strip_think_tags(resp_text)
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            summaries = json_repair.loads(resp_text)
            if not isinstance(summaries, dict):
                logger.warning(f"Entity summary generation returned non-dict: {type(summaries)}")
                return 0

            count = 0
            for name, summary in summaries.items():
                if name in self._entities and isinstance(summary, str) and summary.strip():
                    self._entities[name]["summary"] = summary.strip()
                    self._entities[name]["updated_at"] = datetime.now().isoformat()
                    count += 1

            if count > 0:
                self._save()
                logger.info(f"KnowledgeGraph: generated summaries for {count} entities")
                
                # Phase 28C: Sync entity summaries to Vector DB for semantic searching
                if getattr(self, "vector_memory", None):
                    for name, summary in summaries.items():
                        if name in self._entities and isinstance(summary, str) and summary.strip():
                            # Prefix with kg_entity: to easily filter during retrieval
                            self.vector_memory.ingest_text(
                                text=f"{name}: {summary}", 
                                source=f"kg_entity:{name}",
                                metadata={"entity": name, "type": "kg_summary"}
                            )
            return count
        except Exception as e:
            logger.error(f"Entity summary generation failed: {e}")
            return 0

    async def generate_bridging_facts(self, provider: LLMProvider, model: str) -> int:
        """P29-3: Offline Bridging Facts.
        
        Analyzes the graph's entities and triples to discover implicit, multi-hop
        relationships (e.g., A works with B, B works on C -> A might know about C).
        Saves these insights as new 'bridge' triples to speed up future multi-hop queries.
        
        Returns:
            Number of new bridging facts generated.
        """
        if len(self._triples) < 5:
            return 0

        # Sample up to 100 recent triples to avoid massive prompts
        sample_triples = self._triples[-100:]
        facts_text = "\n".join([f"- {t.get('subject')} {t.get('predicate')} {t.get('object')} ({t.get('description', '')})" for t in sample_triples])

        prompt = f"""You are a Knowledge Graph Reasoning Engine.
Analyze the following graph facts and deduce up to 5 implicit "bridging facts" (multi-hop relationships between entities that are indirectly connected).
Focus on meaningful connections (e.g., transitive organizational relationships, shared project contexts, or dependencies).

Facts:
{facts_text}

Return ONLY a valid JSON array of objects representing the new bridging facts.
Each object must have "subject", "predicate", "object", and "description". 
Use predicates like "is indirectly linked to", "shares context with".

Example:
[
  {{"subject": "David", "predicate": "shares context with", "object": "Project X", "description": "David works with Anna, who is the lead for Project X."}}
]
Do not include markdown fences. If no meaningful bridging facts can be deduced, return []."""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a bridging fact extractor. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.2,
            )
            resp_text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            resp_text = strip_think_tags(resp_text)
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            result = json_repair.loads(resp_text)
            added = 0
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and "subject" in item and "predicate" in item and "object" in item:
                        desc = str(item.get("description", ""))
                        self._add_triple(
                            str(item["subject"]),
                            str(item["predicate"]),
                            str(item["object"]),
                            description=f"Bridging Fact: {desc}",
                            confidence=0.8
                        )
                        added += 1
            if added > 0:
                self.rebuild_entity_index()
                self._save()
                logger.info(f"P29-3: Generated {added} bridging facts.")
            return added
        except Exception as e:
            logger.error(f"Bridging facts generation failed: {e}")
            return 0

    def get_entity_context(self, query: str) -> str:
        """KG3: Return matching entity summaries for the query.

        Preferred over get_1hop_context when entity summaries are available.
        Falls back to get_1hop_context if no entity summaries exist.
        """
        if not self._entities:
            return self.get_1hop_context(query)

        # Check if any entities have summaries
        has_summaries = any(e.get("summary") for e in self._entities.values())
        if not has_summaries:
            return self.get_1hop_context(query)

        query_lower = query.lower()
        query_words = set(tokenize_key(query_lower))
        if not query_words:
            return ""

        # Phase 28C: Semantic retrieval from Vector DB
        semantic_boost = {}
        if getattr(self, "vector_memory", None):
            try:
                # Top 5 semantic matches
                v_results = self.vector_memory.search(query, top_k=5, source_filter="kg_entity")
                for r in v_results:
                    entity_name = r.get("metadata", {}).get("entity")
                    if entity_name:
                        # VectorMemory score is typically 0.0-1.0; scale to match local scoring
                        semantic_boost[entity_name.lower()] = float(r.get("score", 0.0)) * 3.0
            except Exception as e:
                logger.warning(f"KnowledgeGraph semantic search failed: {e}")

        matched_entities: list[tuple[str, dict[str, Any], float]] = []
        for name, info in self._entities.items():
            if not info.get("summary"):
                continue
            name_lower = name.lower()
            name_words = set(tokenize_key(name_lower))

            # Priority scoring (Hybrid Exact + Semantic)
            score = 0.0
            if name_lower in query_lower:
                score += 3.0  # Exact substring match
            elif query_words & name_words:
                score += 1.0  # Token overlap
            
            # Add semantic boost
            if name_lower in semantic_boost:
                score += semantic_boost[name_lower]

            if score > 0.0:
                matched_entities.append((name, info, score))

        if not matched_entities:
            # Fallback to raw triple matching
            return self.get_1hop_context(query)

        # Sort by score descending, cap at 5 entities
        matched_entities.sort(key=lambda x: x[2], reverse=True)
        matched_entities = matched_entities[:5]

        parts = []
        for name, info, score in matched_entities:
            summary = info.get("summary", "")
            parts.append(f"- **{name}**: {summary}")

        return "## Entity Knowledge\n" + "\n".join(parts)

    # ── KG4: Query Decomposition ────────────────────────────────────────

    @staticmethod
    def _is_complex_query(query: str) -> bool:
        """KG4: Heuristic to detect queries that need multi-hop decomposition.

        Complex queries typically ask about relationships between entities
        that require graph traversal (e.g., "David同事的邮箱是什么？").
        """
        # Chinese patterns for multi-hop
        zh_patterns = [
            r"的.+的",       # "A的B的C" — chained possession
            r"谁.+的",       # "谁是...的" — indirect reference
            r"哪个.+的.+",   # "哪个...的..."
        ]
        # English patterns for multi-hop
        en_patterns = [
            r"\b\w+'s\s+\w+'s\b",        # "David's colleague's email"
            r"who\s+.+\s+of\s+",          # "who is the manager of..."
            r"what\s+is\s+.+\s+of\s+.+",  # "what is the email of..."
        ]

        for pattern in zh_patterns + en_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False

    async def decompose_query(self, provider: LLMProvider, model: str, query: str) -> list[dict[str, str]]:
        """KG4: Decompose a complex query into a chain of sub-queries.

        Returns:
            List of sub-query dicts: [{"query": "...", "target": "X"}, ...]
        """
        prompt = f"""You are a Query Decomposition Engine for a Knowledge Graph.
Decompose this complex query into a sequence of simpler sub-queries that can be answered
by looking up entity facts one hop at a time.

Query: "{query}"

Return a JSON array where each element has:
- "query": the sub-query to look up
- "target": the placeholder variable being resolved (e.g., "X", "Y")

Example for "What is David's colleague's email?":
[
  {{"query": "Who is David's colleague?", "target": "X"}},
  {{"query": "What is X's email?", "target": "Y"}}
]

Return ONLY valid JSON. If the query is simple (single hop), return a single-element array.
Do not include markdown fences."""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "Query decomposition engine. Return only JSON array."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.1,
            )
            resp_text = (response.content or "").strip()
            from nanobot.utils.think_strip import strip_think_tags
            resp_text = strip_think_tags(resp_text)
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(resp_text)
            if isinstance(result, list):
                return [r for r in result if isinstance(r, dict) and "query" in r]
            return [{"query": query, "target": "answer"}]
        except Exception as e:
            logger.error(f"Query decomposition failed: {e}")
            return [{"query": query, "target": "answer"}]

    async def resolve_multihop(self, provider: LLMProvider, model: str, query: str) -> str:
        """KG4: Resolve a multi-hop query by decomposing and iteratively looking up.

        Returns:
            Assembled context string with resolved facts.
        """
        sub_queries = await self.decompose_query(provider, model, query)
        if len(sub_queries) <= 1:
            # Simple query — just use entity context
            return self.get_entity_context(query)

        resolved_facts: list[str] = []
        resolved_vars: dict[str, str] = {}

        for step in sub_queries:
            sub_q = step.get("query", "")
            target = step.get("target", "")

            # Replace resolved placeholders in the sub-query
            for var, val in resolved_vars.items():
                sub_q = sub_q.replace(var, val)

            # Look up in entity context
            context = self.get_entity_context(sub_q)
            if not context:
                context = self.get_1hop_context(sub_q)

            if context:
                resolved_facts.append(f"Step ({sub_q}): {context}")
                # Try to extract the answer entity from context for next step
                # Simple heuristic: take the first entity mentioned in context
                for name in self._entities:
                    if name.lower() in context.lower() and name.lower() not in sub_q.lower():
                        resolved_vars[target] = name
                        break

        if resolved_facts:
            return "## Multi-hop Knowledge Resolution\n" + "\n".join(resolved_facts)
        return self.get_entity_context(query)

    # ── Legacy 1-hop Context (backward compat) ──────────────────────────

    def get_1hop_context(self, query: str) -> str:
        """Extract entities from the query using basic tokenization and return 1-hop connected facts.

        KG1: Now includes triple descriptions in output when available.
        """
        if not self._triples:
            return ""

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
        seen: set[tuple[str | None, ...]] = set()
        unique_matches = []
        for t in matched_triples:
            k = (t.get("subject"), t.get("predicate"), t.get("object"))
            if k not in seen:
                seen.add(k)
                unique_matches.append(t)
                # Cap at top 10 facts to avoid context bloat
                if len(unique_matches) >= 10:
                    break

        facts = []
        for t in unique_matches:
            fact = f"- {t.get('subject')} {t.get('predicate')} {t.get('object')}."
            desc = t.get("description", "")
            if desc:
                fact += f" ({desc})"
            facts.append(fact)

        return "## Entity Graph Connections\n" + "\n".join(facts)
