"""Vector Store for Long-Term Memory (RAG).

Provides semantic search over historical memory using ChromaDB + sentence-transformers.
This is an *enhancement layer* — all existing file-based memory (MEMORY.md, HISTORY.md,
daily logs) remains untouched. The vector store indexes the same content for semantic
retrieval.

Design:
- ChromaDB persistent storage at workspace/memory/vectordb/
- Embedding: .\models\sentence-transformers\paraphrase-multilingual-minilm-l12-v2 (loaded lazily on first use)
- Deduplication via content-hash-based document IDs
- All public methods are fault-tolerant (return empty on error, never raise)
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Embedding function wrapper (bridges sentence-transformers → ChromaDB)
# ---------------------------------------------------------------------------

from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

class _SentenceTransformerEmbedding(EmbeddingFunction):
    """Lazy-loaded sentence-transformers embedding for ChromaDB."""

    # Default model path (used when no config override is provided)
    _DEFAULT_MODEL = r"..\nanochat\models\sentence-transformers\paraphrase-multilingual-minilm-l12-v2"
    _SHARED_MODEL = None

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or self._DEFAULT_MODEL

    def _load(self) -> None:
        if self.__class__._SHARED_MODEL is not None:
            return
        import os
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["HF_HUB_OFFLINE"] = "1"  # Force offline mode for HuggingFace hub
        
        from sentence_transformers import SentenceTransformer, models
        logger.info(f"Loading embedding model: {self._model_path} (local_files_only=True) …")
        
        try:
            # We explicitly instantiate the two main modules for a standard semantic search model.
            # This avoids the "Pooling missing word_embedding_dimension" error occurring when 
            # the user only downloads the root model folder (pytorch_model.bin) and forgets 
            # the 1_Pooling subdirectory and its config.
            word_embedding_model = models.Transformer(self._model_path, local_files_only=True)
            pooling_model = models.Pooling(
                word_embedding_model.get_word_embedding_dimension(),
                pooling_mode_mean_tokens=True,
                pooling_mode_cls_token=False,
                pooling_mode_max_tokens=False
            )
            self.__class__._SHARED_MODEL = SentenceTransformer(modules=[word_embedding_model, pooling_model])
            logger.info("Embedding model loaded successfully using assembled components.")
        except Exception as e:
            logger.warning(f"Failed to load using assembled components, falling back to standard SentenceTransformer: {e}")
            self.__class__._SHARED_MODEL = SentenceTransformer(self._model_path, local_files_only=True)

    def __call__(self, input: Documents) -> Embeddings:
        """ChromaDB EmbeddingFunction protocol."""
        self._load()
        embeddings = self.__class__._SHARED_MODEL.encode(input, show_progress_bar=False)
        return embeddings.tolist()


# ---------------------------------------------------------------------------
# VectorMemory — the public API
# ---------------------------------------------------------------------------

class VectorMemory:
    """Semantic memory store backed by ChromaDB.

    Indexes HISTORY.md entries and YYYY-MM-DD.md daily logs for retrieval.

    Usage:
        vm = VectorMemory(workspace_path)
        vm.ingest_history_file()          # one-time bulk index
        vm.ingest_daily_logs()            # one-time bulk index
        results = vm.search("上周的销售报告")  # semantic search
    """

    COLLECTION_NAME = "nanobot_memory"

    def __init__(self, workspace: Path | str, provider=None, model=None) -> None:
        self.workspace = Path(workspace)
        self.memory_dir = self.workspace / "memory"
        self._db_path = self.memory_dir / "vectordb"
        self._collection = None
        self._embedding_fn = _SentenceTransformerEmbedding()
        self._init_done = False
        
        # Provider and model for query rewriting
        self.provider = provider
        self.model = model

    # -- Lazy initialisation ------------------------------------------------

    def _ensure_init(self) -> bool:
        """Lazily initialise ChromaDB. Returns True on success."""
        if self._init_done:
            return self._collection is not None
        self._init_done = True
        try:
            import chromadb
            from chromadb.config import Settings

            self._db_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(self._db_path),
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"VectorMemory ready: collection='{self.COLLECTION_NAME}', "
                f"docs={self._collection.count()}"
            )
            return True
        except Exception as e:
            logger.error(f"VectorMemory init failed (non-fatal): {e}")
            self._collection = None
            return False

    # -- Content hashing (for dedup) ----------------------------------------

    @staticmethod
    def _doc_id(source: str, content: str) -> str:
        """Deterministic document ID from source + content."""
        raw = f"{source}::{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # -- Chunking -----------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
        """Split text into paragraph-level chunks.

        Strategy:
        1. Split on double-newline boundaries first (natural paragraphs).
        2. If a paragraph exceeds max_chars, split on single newlines.
        3. As a last resort, split by sentence boundaries.
        """
        paragraphs = re.split(r"\n\s*\n", text.strip())
        chunks: list[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para) <= max_chars:
                chunks.append(para)
            else:
                # Try splitting on single newlines
                lines = para.split("\n")
                current = ""
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if current and len(current) + len(line) + 1 > max_chars:
                        chunks.append(current)
                        current = line
                    else:
                        current = f"{current}\n{line}" if current else line
                if current:
                    chunks.append(current)

        return [c for c in chunks if len(c) >= 2]  # skip trivially short

    # -- Public: ingest arbitrary text --------------------------------------

    def ingest_text(
        self,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Chunk and ingest text into the vector store.

        Args:
            text: Raw text content to index.
            source: Source label, e.g. "history", "daily_log", "daily_log:2026-03-01".
            metadata: Extra metadata to attach to each chunk.

        Returns:
            Number of chunks ingested (0 on failure).
        """
        if not self._ensure_init():
            return 0

        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        base_meta = {"source": source}
        if metadata:
            base_meta.update(metadata)

        for chunk in chunks:
            doc_id = self._doc_id(source, chunk)
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append(dict(base_meta))

        try:
            # upsert = insert or update (handles dedup automatically)
            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            logger.debug(f"VectorMemory: ingested {len(chunks)} chunks from '{source}'")
            return len(chunks)
        except Exception as e:
            logger.error(f"VectorMemory ingest failed: {e}")
            return 0

    # -- Public: ingest HISTORY.md ------------------------------------------

    def ingest_history_file(self) -> int:
        """Parse and ingest workspace/memory/HISTORY.md.

        Each double-newline-separated block becomes one document.

        Returns:
            Total chunks ingested.
        """
        history_file = self.memory_dir / "HISTORY.md"
        if not history_file.exists():
            logger.debug("VectorMemory: HISTORY.md not found, skipping")
            return 0

        content = history_file.read_text(encoding="utf-8").strip()
        if not content:
            return 0

        return self.ingest_text(content, source="history")

    # -- Public: ingest daily logs ------------------------------------------

    def ingest_daily_logs(self) -> int:
        """Parse and ingest all memory/YYYY-MM-DD.md files.

        Returns:
            Total chunks ingested across all files.
        """
        if not self.memory_dir.exists():
            return 0

        total = 0
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")

        for md_file in sorted(self.memory_dir.iterdir()):
            if not date_pattern.match(md_file.name):
                continue
            content = md_file.read_text(encoding="utf-8").strip()
            if not content:
                continue

            date_str = md_file.stem  # e.g. "2026-03-01"
            total += self.ingest_text(
                content,
                source=f"daily_log:{date_str}",
                metadata={"date": date_str},
            )

        logger.info(f"VectorMemory: ingested daily logs — {total} total chunks")
        return total

    # -- Public: full reindex -----------------------------------------------

    def full_reindex(self) -> int:
        """Clear the collection and re-ingest all sources.

        Returns:
            Total chunks ingested.
        """
        if not self._ensure_init():
            return 0

        try:
            # Delete all documents in the collection
            existing = self._collection.count()
            if existing > 0:
                # ChromaDB requires IDs to delete; get all and delete
                all_ids = self._collection.get()["ids"]
                if all_ids:
                    self._collection.delete(ids=all_ids)
                logger.info(f"VectorMemory: cleared {existing} documents for reindex")
        except Exception as e:
            logger.error(f"VectorMemory: failed to clear collection: {e}")

        total = 0
        total += self.ingest_history_file()
        total += self.ingest_daily_logs()
        logger.info(f"VectorMemory: full reindex complete — {total} chunks")
        return total

    # -- Public: semantic search --------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over indexed memory.

        Args:
            query: Natural language query.
            top_k: Max number of results.
            source_filter: Optional — restrict to source prefix, e.g. "history"
                           or "daily_log".

        Returns:
            List of dicts: [{text, source, score, metadata}, ...]
            Empty list on error.
        """
        if not self._ensure_init():
            return []

        if not query or not query.strip():
            return []

        try:
            where_filter = None
            if source_filter:
                # ChromaDB $contains is not supported on metadata strings,
                # so we use a workaround: for "daily_log" filter, we match
                # source starting with "daily_log" using regex-like logic.
                # Since ChromaDB metadata filters are limited, we'll filter
                # post-query if needed.
                pass  # handled in post-filtering below

            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k * 2 if source_filter else top_k, 20),
            )

            if not results or not results["ids"] or not results["ids"][0]:
                return []

            output: list[dict[str, Any]] = []
            ids = results["ids"][0]
            docs = results["documents"][0]
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)

            for doc, dist, meta in zip(docs, distances, metas):
                source = meta.get("source", "unknown") if meta else "unknown"

                # Post-filter by source prefix
                if source_filter and not source.startswith(source_filter):
                    continue

                # ChromaDB cosine distance → similarity score (0-1, higher=better)
                score = max(0.0, 1.0 - dist)

                # Time-decay penalty (Phase 20C): 0.99 ^ days_since_creation
                date_str = meta.get("date", "") if meta else ""
                if not date_str and source == "history":
                    # Try to extract from text, e.g. [2026-03-01 14:00]
                    date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})", doc)
                    if date_match:
                        date_str = date_match.group(1)
                
                if date_str:
                    try:
                        from datetime import datetime
                        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        today = datetime.now().date()
                        days_diff = (today - entry_date).days
                        if days_diff > 0:
                            decay_factor = 0.99 ** days_diff
                            score = score * decay_factor
                    except Exception:
                        pass

                output.append({
                    "text": doc,
                    "source": source,
                    "score": score,  # keep full precision for sorting
                    "metadata": meta or {},
                })

            # Re-sort by time-decayed score descending
            output.sort(key=lambda x: x["score"], reverse=True)
            
            # Format scores and take top_k
            final_output = []
            for item in output[:top_k]:
                item["score"] = round(item["score"], 4)
                final_output.append(item)

            return final_output

        except Exception as e:
            logger.error(f"VectorMemory search failed (non-fatal): {e}")
            return []

    # -- Public: stats ------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return basic stats about the vector store.

        Returns:
            Dict with count, db_path, etc. Empty dict on failure.
        """
        if not self._ensure_init():
            return {"count": 0, "status": "unavailable"}

        try:
            return {
                "count": self._collection.count(),
                "db_path": str(self._db_path),
                "status": "ready",
            }
        except Exception as e:
            logger.error(f"VectorMemory stats failed: {e}")
            return {"count": 0, "status": f"error: {e}"}

    # -- Public: format search results for LLM context ----------------------
    
    # E3: Pronouns that indicate coreference resolution is needed
    _COREFERENCE_PRONOUNS = {
        # English
        "he", "she", "it", "they", "them", "his", "her", "its", "their",
        "this", "that", "these", "those",
        # Chinese
        "他", "她", "它", "他们", "她们", "这个", "那个", "这些", "那些",
        "其", "该",
    }

    async def rewrite_query(self, query: str, conversation_history: list[dict[str, Any]] | None = None) -> str:
        """Rewrite the query to resolve coreferences based on conversational history (P13 feature).
        
        Uses the configured provider to replace pronouns like 'he', 'she', 'it' with their
        actual subjects from the preceding few messages.
        
        Args:
            query: The original user search query.
            conversation_history: List of previous message dictionaries.
             
        Returns:
            The rewritten query, or the original query if no rewriting is needed or an error occurs.
        """
        if not self.provider or not self.model or not conversation_history:
            return query

        # E3: Short-circuit — skip LLM call if query has no coreferential pronouns
        query_lower = query.lower()
        query_words = set(query_lower.split())
        # Check both word-level (English) and substring-level (Chinese)
        has_pronoun = bool(query_words & self._COREFERENCE_PRONOUNS) or any(
            p in query_lower for p in self._COREFERENCE_PRONOUNS if len(p) > 1  # Chinese pronouns
        )
        if not has_pronoun:
            return query
            
        recent_history = conversation_history[-6:]
        if not recent_history:
            return query
            
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in recent_history])
        
        prompt = f"""You are a query rewriting assistant. 
Given the following conversation history, rewrite the user's latest query so that it is fully self-contained without needing the context. 
Resolve any pronouns (e.g. 'it', 'he', 'that issue') to their specific names or entities mentioned in the history.
Do NOT reply with anything other than the rewritten query. If no rewriting is needed, return the original query exactly.

Conversation History:
{history_text}

Latest Query:
{query}

Rewritten Query:"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.provider.chat(
                messages=messages,
                model=self.model,
                temperature=0.0,
                max_tokens=200
            )
            rewritten = response.content.strip()
            if rewritten and rewritten.lower() != query.lower():
                logger.info(f"VectorMemory: Refined query from '{query}' to '{rewritten}'")
                return rewritten
            return query
        except Exception as e:
            logger.error(f"VectorMemory query rewriting failed (non-fatal): {e}")
            return query

    @staticmethod
    def format_results_for_context(results: list[dict[str, Any]]) -> str:
        """Format search results into a text block suitable for system prompt injection.

        Args:
            results: Output from search().

        Returns:
            Formatted text block, or empty string if no results.
        """
        if not results:
            return ""

        lines = ["## Relevant Historical Context\n"]
        for i, r in enumerate(results, 1):
            source = r.get("source", "unknown")
            text = r.get("text", "").strip()
            score = r.get("score", 0)
            meta = r.get("metadata", {})
            date_str = meta.get("date", "")

            header = f"[{source}]"
            if date_str:
                header = f"[{date_str}]"

            lines.append(f"**{i}. {header}** (relevance: {score:.0%})")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)
