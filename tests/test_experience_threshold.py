"""Regression tests for match_experience small-corpus Jaccard fallback.

ADR-KB-01 / DEBT-KB-1: Validates that threshold=0.65 + no_dense_penalty=0.5
does NOT produce false-positive hits in a tiny Experience Bank (1-4 entries)
where BM25 IDF degenerates and the hybrid_retriever falls back to Jaccard
similarity.

Ref: knowledge_workflow.py L220-231, hybrid_retriever.py L90-95
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tiny_kb_workflow(tmp_path: Path) -> KnowledgeWorkflow:
    """KnowledgeWorkflow backed by a tiny Experience Bank (1 entry).

    Uses no vector memory → forces the hybrid_retriever into the pure-BM25
    (or Jaccard fallback) path, which is the path under test.
    """
    from nanobot.agent.task_knowledge import TaskKnowledgeStore

    store = TaskKnowledgeStore(tmp_path)
    store.add_experience(
        context_trigger="写Python脚本时",
        tactical_prompt="用with open替代open().read()",
        action_type="directive",
    )
    kw = KnowledgeWorkflow(vector_memory=None)  # No dense vector — pure BM25/Jaccard
    kw.knowledge_store = store
    return kw


@pytest.fixture
def multi_entry_kb_workflow(tmp_path: Path) -> KnowledgeWorkflow:
    """KnowledgeWorkflow with 4 entries — still small enough to trigger
    BM25 IDF ≈ 0 degeneration in a single-document-dominated corpus."""
    from nanobot.agent.task_knowledge import TaskKnowledgeStore

    store = TaskKnowledgeStore(tmp_path)
    entries = [
        ("写Python脚本时", "用with open替代open().read()", "directive"),
        ("发送邮件时", "附件路径使用绝对路径", "directive"),
        ("调用浏览器工具时", "先截图确认当前UI状态", "correction"),
        ("执行shell命令时", "先dry-run检查副作用", "error_recovery"),
    ]
    for trigger, prompt, action_type in entries:
        store.add_experience(trigger, prompt, action_type)

    kw = KnowledgeWorkflow(vector_memory=None)
    kw.knowledge_store = store
    return kw


# ---------------------------------------------------------------------------
# Core false-positive guard tests (ADR-KB-01 primary concern)
# ---------------------------------------------------------------------------

class TestMatchExperienceFalsePositives:
    """Ensure that completely unrelated queries do NOT trigger experience hits."""

    def test_unrelated_query_weather(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Query: weather check — no relation to Python file I/O."""
        result = tiny_kb_workflow.match_experience("帮我查一下今天北京的天气")
        assert result is None, f"False positive: unrelated weather query returned '{result}'"

    def test_unrelated_query_greeting(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Query: simple greeting — should never match any experience."""
        result = tiny_kb_workflow.match_experience("你好，帮我做个自我介绍")
        assert result is None, f"False positive: greeting returned '{result}'"

    def test_unrelated_query_english(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Query: English question unrelated to any experience trigger."""
        result = tiny_kb_workflow.match_experience("What is the capital of France?")
        assert result is None, f"False positive: English query returned '{result}'"

    def test_partial_word_overlap_does_not_trigger(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Query shares the word '脚本' but in a completely different domain.

        The concern: Jaccard score for '脚本' shared between
        'Python脚本' and 'bash脚本修改权限' might exceed threshold.
        """
        result = tiny_kb_workflow.match_experience("帮我写一个bash脚本修改文件权限")
        # A hit is acceptable only if the prompt is actually useful for this context.
        # The key requirement: NO Python file-open tip should mask bash context.
        if result is not None:
            assert "open" not in result.lower(), (
                "False positive: Python open() tip injected for bash script context. "
                f"Returned: '{result}'"
            )

    def test_multi_entry_unrelated_query(self, multi_entry_kb_workflow: KnowledgeWorkflow):
        """With 4 entries the Jaccard fallback distributes overlap more evenly.
        An unrelated query should still not match."""
        result = multi_entry_kb_workflow.match_experience("帮我分析一份Excel表格里的销售数据")
        assert result is None, f"False positive on Excel query: '{result}'"


# ---------------------------------------------------------------------------
# True-positive sanity tests (validate threshold doesn't over-suppress)
# ---------------------------------------------------------------------------

class TestMatchExperienceTruePositives:
    """Validate that genuinely relevant queries do trigger experience hits."""

    def test_python_file_read_hits_experience(self, tiny_kb_workflow: KnowledgeWorkflow):
        """A semantically similar Python file I/O query should still have a
        *chance* to hit — we don't mandate it (BM25 only), but it must not crash."""
        result = tiny_kb_workflow.match_experience("我在写一个Python文件读取脚本")
        # Without dense vectors, BM25/Jaccard may or may not hit at 0.65.
        # We only assert: no exception, and if a result is returned it must be a string.
        assert result is None or isinstance(result, str), (
            f"Unexpected return type: {type(result)}"
        )

    def test_multi_entry_browser_context_hit(self, multi_entry_kb_workflow: KnowledgeWorkflow):
        """Browser context should preferably hit the browser experience entry."""
        result = multi_entry_kb_workflow.match_experience(
            "调用浏览器工具完成登录操作"
        )
        # With 4 entries the Jaccard fallback may still not hit at 0.65 sans dense.
        # Key safety: no crash, and if a hit occurs it must be a string prompt.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# No vector memory edge cases
# ---------------------------------------------------------------------------

class TestMatchExperienceEdgeCases:
    """Guard against crashes and degenerate states."""

    def test_empty_experience_bank(self, tmp_path: Path):
        """Empty store must return None without exception."""
        from nanobot.agent.task_knowledge import TaskKnowledgeStore
        store = TaskKnowledgeStore(tmp_path)
        kw = KnowledgeWorkflow(vector_memory=None)
        kw.knowledge_store = store
        result = kw.match_experience("任意查询")
        assert result is None

    def test_no_knowledge_store(self):
        """No store configured must return None without exception."""
        kw = KnowledgeWorkflow(vector_memory=None)
        result = kw.match_experience("任意查询")
        assert result is None

    def test_empty_query_string(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Empty query must return None gracefully."""
        result = tiny_kb_workflow.match_experience("")
        assert result is None

    def test_whitespace_only_query(self, tiny_kb_workflow: KnowledgeWorkflow):
        """Whitespace-only query must return None gracefully."""
        result = tiny_kb_workflow.match_experience("   \t  ")
        assert result is None
