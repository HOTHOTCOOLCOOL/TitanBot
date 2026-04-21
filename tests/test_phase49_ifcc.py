import pytest
from nanobot.agent.tag_extractor import extract_mem_content
from nanobot.agent.context import ContextBuilder
import json

class StubContextBuilder(ContextBuilder):
    def __init__(self):
        # Override init to avoid loading Heavy vectors/models
        # Just initialize what we need for History testing
        self.language = "en"
        from pathlib import Path
        import tempfile
        self.workspace = Path(tempfile.mkdtemp())

def test_t1_single_tag():
    text = "Here is my reasoning. <mem> Found the root cause </mem> Let me fix it."
    clean, summary = extract_mem_content(text)
    assert summary == "Found the root cause"
    assert clean == "Here is my reasoning.  Let me fix it."

def test_t2_multiple_tags():
    text = "<mem>Step 1 done</mem> some text <mem> Step 2 done </mem>"
    clean, summary = extract_mem_content(text)
    assert summary == "Step 1 done | Step 2 done"
    assert clean == "some text"

def test_t3_unclosed_tag():
    text = "Almost finished <mem> Unclosed tag content"
    clean, summary = extract_mem_content(text)
    assert summary == "Unclosed tag content"
    assert clean == "Almost finished"

def test_t4_no_tag():
    text = "Just a normal response with no tags."
    clean, summary = extract_mem_content(text)
    assert summary is None
    assert clean == text

def test_t5_long_tag_truncation():
    long_text = "A" * 600
    text = f"<mem>{long_text}</mem>"
    clean, summary = extract_mem_content(text)
    assert len(summary) == 500
    assert summary == "A" * 500

def test_t6_nested_or_broken_tags():
    text = "Text <mem>outer <mem>inner</mem></mem>"
    clean, summary = extract_mem_content(text)
    # The regex will match from the first <mem> to the first </mem>
    # So it hits <mem>outer <mem>inner</mem>
    assert summary == "outer <mem>inner"

def test_t8_trim_history_downgrade():
    ctx = StubContextBuilder()
    
    # Create artificial history
    history = [
        {"role": "user", "content": "Req 1"},
        {"role": "assistant", "content": "Resp 1", "milestone_summary": "First step resolved"},
        {"role": "user", "content": "Req 2"},
        {"role": "assistant", "content": "Resp 2"}
    ]
    
    # Force context limit to be extremely small to trigger truncation
    # But overhead (system_prompt + current_message) takes up some space
    # Target = int(100 * 0.8) - 10 = 70.
    system_prompt = "SYS"
    current_message = "Current"
    
    # We will invoke _trim_history directly
    # min_keep is 4 inside _trim_history... wait, if min_keep is 4, it won't pop anything if len <= 4.
    # Let's give it 6 messages.
    history = [
        {"role": "user", "content": "M1" * 100},
        {"role": "assistant", "content": "M2" * 100, "milestone_summary": "Important Milestone"},
        {"role": "user", "content": "M3"},
        {"role": "assistant", "content": "M4"},
        {"role": "user", "content": "M5"},
        {"role": "assistant", "content": "M6"},
    ]
    
    # It should evict M1, then evaluate M2.
    # M2 has milestone, so it gets downgraded.
    trimmed = ctx._trim_history(history, system_prompt="X", current_message="Y", context_limit=50)
    
    # Since 34 < 38, the while loop drops M1, downgrades M2, and then stops. M2 is NOT dropped.
    assert len(trimmed) == 5
    assert trimmed[0]["is_skeleton"] is True
    
    # Let's adjust min_keep trick. Provide 10 small messages, so it drops down to 4.
    history2 = [
        {"role": "user", "content": "A" * 10},
        {"role": "assistant", "content": "B" * 500, "milestone_summary": "Surviving Milestone"},
        {"role": "user", "content": "C"},
        {"role": "assistant", "content": "D"},
        {"role": "user", "content": "E"},
        {"role": "assistant", "content": "F"},
        {"role": "user", "content": "G"},
        {"role": "assistant", "content": "H"},
    ]
    # We want B to be downgraded and stay, meaning length should end up being > 4 or we just verify the downgrade works.
    trimmed2 = ctx._trim_history(history2, "SYS", "MSG", context_limit=100)
    # The while loop pops A. Then downgrades B. B becomes small.
    # Since B is small, total size < target? 
    # Target = 100 * 0.8 - len(SYS MSG) = 80 - 6 = 74.
    # Length of trimmed2 after downgrading B: "（上下文已压缩） Surviving Milestone" = ~30 chars.
    # Remaining messages ~ 6. Total chars ~ 36 < 74. So it stops!
    # B is preserved as a downgraded message!
    assert "上下文已压缩" in trimmed2[0]["content"]
    assert "Surviving Milestone" in trimmed2[0]["content"]
    assert trimmed2[0]["is_skeleton"] is True

def test_t9_trim_history_no_milestone():
    ctx = StubContextBuilder()
    history = [
        {"role": "user", "content": "Giant message" * 500},
        {"role": "assistant", "content": "Small message"},
        {"role": "user", "content": "keep1"},
        {"role": "assistant", "content": "keep2"},
        {"role": "user", "content": "keep3"},
        {"role": "assistant", "content": "keep4"},
    ]
    trimmed = ctx._trim_history(history, "S", "M", 100)
    # Giant message has no milestone, should be dropped entirely
    assert "Giant message" not in trimmed[0]["content"]

def test_t10_serialization():
    from nanobot.session.manager import Session
    s = Session(key="test")
    s.add_message("assistant", "content", milestone_summary="Testing 123")
    
    assert s.messages[0]["milestone_summary"] == "Testing 123"
    
    # get_history test
    hist = s.get_history()
    assert hist[0]["milestone_summary"] == "Testing 123"
    assert "role" in hist[0]
