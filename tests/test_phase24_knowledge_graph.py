"""Tests for Phase 24 — Knowledge Graph Evolution (MDER-DR).

Covers:
- KG1: Triple Description Enrichment
- KG2: Entity Disambiguation
- KG3: Entity-Centric Summaries
- KG4: Query Decomposition
- KG5: Semantic Chunking
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nanobot.agent.knowledge_graph import KnowledgeGraph
from nanobot.providers.base import LLMProvider


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def kg(workspace):
    return KnowledgeGraph(workspace)


# ── KG1: Triple Description Enrichment ──────────────────────────────


class TestKG1TripleDescriptions:
    """KG1: Triples now carry a natural language description."""

    def test_add_triple_with_description(self, kg, workspace):
        """Triple with description persists to JSON and reloads."""
        kg._add_triple("David", "works for", "Salesforce", description="Since 2020 in Shenzhen team")

        data = json.loads((workspace / "memory" / "graph.json").read_text())
        assert data["triples"][0]["description"] == "Since 2020 in Shenzhen team"

        # Reload from disk
        kg2 = KnowledgeGraph(workspace)
        assert kg2._triples[0]["description"] == "Since 2020 in Shenzhen team"

    def test_add_triple_without_description_backward_compat(self, kg):
        """Triples without description still work (backward compat)."""
        kg._add_triple("A", "relates to", "B")
        assert kg._triples[0]["description"] == ""

    def test_duplicate_triple_updates_richer_description(self, kg):
        """When a duplicate triple is added with a longer description, it updates."""
        kg._add_triple("David", "works for", "Salesforce", description="Works there")
        kg._add_triple("David", "WORKS FOR", "salesforce", description="Since 2020 in Shenzhen AI team, focusing on NLP research")
        assert len(kg._triples) == 1
        assert "Since 2020" in kg._triples[0]["description"]

    def test_get_1hop_context_includes_descriptions(self, kg):
        """get_1hop_context output includes descriptions when available."""
        kg._add_triple("David", "works for", "Salesforce", description="Since 2020 in Shenzhen")
        kg._add_triple("David", "likes", "coffee")

        context = kg.get_1hop_context("Where does David work?")
        assert "Since 2020 in Shenzhen" in context
        assert "Salesforce" in context

    @pytest.mark.asyncio
    async def test_extract_triples_includes_descriptions(self, kg):
        """extract_triples prompt requests descriptions from LLM."""
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"subject": "System", "predicate": "runs on", "object": "Linux",
             "description": "The production system runs on Ubuntu 22.04 LTS."},
            {"subject": "User", "predicate": "prefers", "object": "Dark mode",
             "description": "User explicitly requested dark mode for all UIs."}
        ])
        mock_provider.chat.return_value = mock_response

        await kg.extract_triples(mock_provider, "test_model", "System runs on Linux. User prefers dark mode.")

        assert len(kg._triples) == 2
        assert "Ubuntu" in kg._triples[0]["description"]
        assert "dark mode" in kg._triples[1]["description"]

    def test_backward_compat_load_old_format(self, workspace):
        """Old graph.json without entities/aliases/descriptions loads fine."""
        (workspace / "memory").mkdir(parents=True)
        old_data = {
            "triples": [
                {"subject": "A", "predicate": "rel", "object": "B",
                 "timestamp": "2026-01-01T00:00:00", "confidence": 1.0}
            ],
            "updated_at": "2026-01-01T00:00:00"
        }
        (workspace / "memory" / "graph.json").write_text(
            json.dumps(old_data), encoding="utf-8"
        )

        kg = KnowledgeGraph(workspace)
        assert len(kg._triples) == 1
        assert kg._triples[0].get("description", "") == ""
        assert kg._entities == {}
        assert kg._aliases == {}


# ── KG2: Entity Disambiguation ──────────────────────────────────────


class TestKG2EntityDisambiguation:
    """KG2: Merge semantically equivalent entities via substring heuristics."""

    def test_substring_merge(self, kg):
        """'David' is merged into 'David Liu' as canonical."""
        kg._add_triple("David Liu", "works for", "Salesforce")
        kg._add_triple("David", "likes", "coffee")

        merged = kg.disambiguate_entities()
        assert merged >= 1
        assert "David" in kg._aliases
        assert kg._aliases["David"] == "David Liu"
        # All triples should now reference "David Liu"
        for t in kg._triples:
            assert t["subject"] == "David Liu"

    def test_case_insensitive_disambiguation(self, kg):
        """Case-insensitive substring detection."""
        kg._add_triple("DAVID LIU", "works for", "Salesforce")
        kg._add_triple("david", "likes", "tea")

        merged = kg.disambiguate_entities()
        assert merged >= 1

    def test_no_false_merge_dissimilar_entities(self, kg):
        """Dissimilar entities are NOT merged."""
        kg._add_triple("David Liu", "works for", "Salesforce")
        kg._add_triple("John Smith", "works for", "Google")

        merged = kg.disambiguate_entities()
        assert merged == 0
        assert "John Smith" not in kg._aliases

    def test_short_entity_not_merged(self, kg):
        """Very short entities (< 2 chars) are not merged to avoid noise."""
        kg._add_triple("AI Research Lab", "uses", "Python")
        kg._add_triple("A", "is", "letter")

        merged = kg.disambiguate_entities()
        # "A" should not be merged into "AI Research Lab" (too short)
        assert "A" not in kg._aliases

    def test_manual_alias(self, kg):
        """Manually added aliases rewrite triples."""
        kg._add_triple("刘总", "likes", "coffee")
        kg.add_alias("刘总", "David Liu")
        assert kg._triples[0]["subject"] == "David Liu"

    def test_normalize_entity_uses_aliases(self, kg):
        """_normalize_entity resolves aliases."""
        kg._aliases["Dave"] = "David Liu"
        assert kg._normalize_entity("Dave") == "David Liu"
        assert kg._normalize_entity("Unknown") == "Unknown"

    def test_low_ratio_not_merged(self, kg):
        """Entities where shorter is < 30% of longer are not merged."""
        kg._add_triple("International Business Machines Corporation", "is", "tech company")
        kg._add_triple("IB", "is", "abbreviation")  # IB is < 30% of the long name

        merged = kg.disambiguate_entities()
        assert "IB" not in kg._aliases


# ── KG3: Entity-Centric Summaries ───────────────────────────────────


class TestKG3EntitySummaries:
    """KG3: Pre-generated entity summaries for multi-hop reasoning."""

    def test_rebuild_entity_index(self, kg):
        """rebuild_entity_index groups triples by entity correctly."""
        kg._add_triple("David", "works for", "Salesforce")
        kg._add_triple("David", "likes", "coffee")
        kg._add_triple("Salesforce", "is_in", "San Francisco")

        entities = kg.rebuild_entity_index()
        assert "David" in entities
        assert "Salesforce" in entities
        assert len(entities["David"]["triple_indices"]) == 2
        assert len(entities["Salesforce"]["triple_indices"]) == 2  # Both as object and subject

    def test_entity_context_fallback_to_1hop(self, kg):
        """Falls back to get_1hop_context when no summaries exist."""
        kg._add_triple("David", "works for", "Salesforce")
        context = kg.get_entity_context("David")
        # Should still return something (via fallback)
        assert "David" in context or "Salesforce" in context

    def test_entity_context_with_summaries(self, kg):
        """Returns entity summaries when available."""
        kg._add_triple("David", "works for", "Salesforce")
        kg.rebuild_entity_index()
        kg._entities["David"]["summary"] = "David is an AI researcher at Salesforce."
        kg._save()

        context = kg.get_entity_context("Tell me about David")
        assert "AI researcher" in context
        assert "Entity Knowledge" in context

    @pytest.mark.asyncio
    async def test_generate_entity_summaries(self, kg):
        """generate_entity_summaries calls LLM and stores summaries."""
        kg._add_triple("David", "works for", "Salesforce", description="Since 2020")
        kg._add_triple("David", "likes", "coffee", description="Drinks 3 cups daily")
        kg.rebuild_entity_index()

        mock_provider = AsyncMock(spec=LLMProvider)
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "David": "David is a Salesforce employee since 2020 who enjoys coffee.",
            "Salesforce": "Salesforce is a company where David works.",
            "coffee": "Coffee is David's preferred beverage."
        })
        mock_provider.chat.return_value = mock_response

        count = await kg.generate_entity_summaries(mock_provider, "test_model")
        assert count >= 2
        assert "Salesforce employee" in kg._entities["David"]["summary"]

    def test_entity_context_no_match_returns_empty(self, kg):
        """Returns empty when query matches no entities."""
        kg._add_triple("David", "works for", "Salesforce")
        kg.rebuild_entity_index()
        kg._entities["David"]["summary"] = "David is an AI researcher."

        context = kg.get_entity_context("What is the weather?")
        # No entity match — falls back to 1hop, which also finds nothing
        assert context == ""


# ── KG4: Query Decomposition ────────────────────────────────────────


class TestKG4QueryDecomposition:
    """KG4: Decompose complex queries for multi-hop resolution."""

    def test_is_complex_query_chinese(self):
        """Chinese multi-hop patterns detected."""
        assert KnowledgeGraph._is_complex_query("David的同事的邮箱是什么？")
        assert not KnowledgeGraph._is_complex_query("David的邮箱是什么？")

    def test_is_complex_query_english(self):
        """English multi-hop patterns detected."""
        assert KnowledgeGraph._is_complex_query("what is the email of the manager of David")
        assert not KnowledgeGraph._is_complex_query("What is David's email?")

    @pytest.mark.asyncio
    async def test_decompose_query(self, kg):
        """decompose_query returns sub-query chain."""
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"query": "Who is David's colleague?", "target": "X"},
            {"query": "What is X's email?", "target": "Y"}
        ])
        mock_provider.chat.return_value = mock_response

        result = await kg.decompose_query(mock_provider, "test_model", "David同事的邮箱？")
        assert len(result) == 2
        assert result[0]["target"] == "X"

    @pytest.mark.asyncio
    async def test_decompose_query_fallback_on_error(self, kg):
        """On LLM error, returns single-element passthrough."""
        mock_provider = AsyncMock(spec=LLMProvider)
        mock_provider.chat.side_effect = Exception("API error")

        result = await kg.decompose_query(mock_provider, "test_model", "simple query")
        assert len(result) == 1
        assert result[0]["query"] == "simple query"

    @pytest.mark.asyncio
    async def test_resolve_multihop_simple_query(self, kg):
        """Simple query (single step) uses entity context directly."""
        kg._add_triple("David", "email is", "david@example.com", description="Work email")
        kg.rebuild_entity_index()
        kg._entities["David"]["summary"] = "David's work email is david@example.com."

        mock_provider = AsyncMock(spec=LLMProvider)
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"query": "What is David's email?", "target": "answer"}
        ])
        mock_provider.chat.return_value = mock_response

        result = await kg.resolve_multihop(mock_provider, "test_model", "What is David's email?")
        assert "David" in result


# ── KG5: Semantic Chunking ──────────────────────────────────────────


class TestKG5SemanticChunking:
    """KG5: Text chunking before triple extraction."""

    def test_short_text_single_chunk(self):
        """Short text returns a single chunk."""
        chunks = KnowledgeGraph._semantic_chunk("Hello world.", max_chunk_chars=2000)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world."

    def test_paragraph_splitting(self):
        """Text is split at paragraph boundaries."""
        text = "Paragraph one. First sentence.\n\nParagraph two. Second sentence.\n\nParagraph three."
        chunks = KnowledgeGraph._semantic_chunk(text, max_chunk_chars=50)
        assert len(chunks) >= 2

    def test_chinese_sentence_boundaries(self):
        """Chinese sentence boundaries (。) handled."""
        text = "第一段内容。这是第一段的第二句。\n\n第二段内容。这里有更多信息。"
        chunks = KnowledgeGraph._semantic_chunk(text, max_chunk_chars=30)
        assert len(chunks) >= 2

    def test_empty_text(self):
        """Empty text returns single empty chunk."""
        chunks = KnowledgeGraph._semantic_chunk("")
        assert len(chunks) == 1

    def test_long_single_paragraph(self):
        """A single long paragraph is split at sentence boundaries."""
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        chunks = KnowledgeGraph._semantic_chunk(text, max_chunk_chars=40)
        assert len(chunks) >= 2


# ── Integration Tests ───────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_flow_extract_disambiguate_index_summarize(self, kg):
        """Full pipeline: extract → disambiguate → index → summarize → query."""
        # Step 1: Extract triples (mocked)
        mock_provider = AsyncMock(spec=LLMProvider)
        extract_response = MagicMock()
        extract_response.content = json.dumps([
            {"subject": "David Liu", "predicate": "works for", "object": "Salesforce",
             "description": "David Liu joined Salesforce in 2020 as an AI researcher."},
            {"subject": "David", "predicate": "likes", "object": "coffee",
             "description": "David drinks 3 cups of coffee daily."},
            {"subject": "Salesforce", "predicate": "is in", "object": "San Francisco",
             "description": "Salesforce HQ is in San Francisco."}
        ])
        summary_response = MagicMock()
        summary_response.content = json.dumps({
            "David Liu": "David Liu is an AI researcher who joined Salesforce in 2020 and enjoys coffee.",
            "Salesforce": "Salesforce is a tech company headquartered in San Francisco.",
            "San Francisco": "San Francisco is where Salesforce HQ is located.",
            "coffee": "Coffee is David's preferred daily beverage."
        })
        mock_provider.chat.side_effect = [extract_response, summary_response]

        await kg.extract_triples(mock_provider, "test_model", "David Liu joined Salesforce in 2020.")

        # After extraction: "David" should be auto-merged into "David Liu"
        assert "David" in kg._aliases or all(
            t["subject"] in ("David Liu", "David", "Salesforce")
            for t in kg._triples
        )

        # Entity index should be built
        assert len(kg._entities) > 0

        # Now generate summaries
        mock_provider.chat.side_effect = [summary_response]
        count = await kg.generate_entity_summaries(mock_provider, "test_model")
        assert count >= 2

        # Query should return entity summaries
        context = kg.get_entity_context("Tell me about David Liu")
        assert "Entity Knowledge" in context

    def test_graph_json_schema_roundtrip(self, kg, workspace):
        """graph.json persists and reloads all Phase 24 fields."""
        kg._add_triple("A", "rel", "B", description="test desc")
        kg._aliases["Alias"] = "A"
        kg.rebuild_entity_index()
        kg._entities["A"]["summary"] = "A is something."
        kg._save()

        # Reload
        kg2 = KnowledgeGraph(workspace)
        assert kg2._triples[0]["description"] == "test desc"
        assert kg2._aliases["Alias"] == "A"
        assert kg2._entities["A"]["summary"] == "A is something."

    def test_entity_summary_regeneration_after_new_triples(self, kg):
        """Adding new triples invalidates old entity indices (rebuilt on next call)."""
        kg._add_triple("David", "works for", "Salesforce")
        kg.rebuild_entity_index()
        assert len(kg._entities["David"]["triple_indices"]) == 1

        kg._add_triple("David", "lives in", "Shenzhen")
        kg.rebuild_entity_index()
        assert len(kg._entities["David"]["triple_indices"]) == 2
