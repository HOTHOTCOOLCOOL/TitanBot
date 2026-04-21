import pytest
from typing import Any
from nanobot.agent.context import _WaterfallBudget, _downgrade_old_images, _VISUAL_HOT_STEPS, _CONTEXT_BUDGET
from nanobot.agent.context import _KG_ENTITY_CAP, _EXPERIENCE_CAP, _ACTION_HIST_CAP, _REMINDER_CAP

def test_waterfall_rag_absorbs_everything():
    """Test 1: KG 为空时 RAG 占满全部 8000 字符预算"""
    waterfall = _WaterfallBudget(total=_CONTEXT_BUDGET)
    waterfall.add("", cap=_KG_ENTITY_CAP)  # Empty KG
    rem = waterfall._remaining
    assert rem == 8000
    
    rag_content = "X" * 10000
    consumed = waterfall.add(rag_content, cap=None)
    assert consumed == 8000
    assert len(waterfall.build()) == 8000


def test_waterfall_kg_capped():
    """Test 2: KG 饱和时 RAG 只拿剩余份额"""
    waterfall = _WaterfallBudget(total=_CONTEXT_BUDGET)
    kg = "K" * 3000
    consumed_kg = waterfall.add(kg, cap=_KG_ENTITY_CAP)
    assert consumed_kg == 2400
    
    rag = "R" * 10000
    consumed_rag = waterfall.add(rag, cap=None)
    assert consumed_rag == 8000 - 2400
    assert waterfall._remaining == 0


def test_waterfall_all_empty():
    """Test 3: 所有层均为空时 system_prompt 无额外内容"""
    waterfall = _WaterfallBudget(total=_CONTEXT_BUDGET)
    waterfall.add(None, cap=100)
    waterfall.add("", cap=None)
    assert waterfall.build() == ""
    assert waterfall._remaining == 8000


def test_waterfall_priority_cutoff():
    """Test 4: 所有层均满时按优先级顺序截断，总量不超过 _CONTEXT_BUDGET"""
    waterfall = _WaterfallBudget(total=_CONTEXT_BUDGET)
    
    c1 = waterfall.add("A" * 3000, cap=_KG_ENTITY_CAP)  # 2400
    c2 = waterfall.add("B" * 2000, cap=_EXPERIENCE_CAP) # 1600
    c3 = waterfall.add("C" * 2000, cap=_ACTION_HIST_CAP)# 1200
    c4 = waterfall.add("D" * 1000, cap=_REMINDER_CAP)   # 400
    c5 = waterfall.add("E" * 5000, cap=None)            # remaining: 2400
    
    assert c1 == 2400
    assert c2 == 1600
    assert c3 == 1200
    assert c4 == 400
    assert c5 == 2400
    
    total_len = len(waterfall.build().replace("\n\n", ""))
    assert total_len == 8000


def test_downgrade_hot_steps_untouched():
    """Test 5: _downgrade_old_images - HOT_STEPS 内消息原样保留 Base64"""
    messages = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "val1"}}]},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "val2"}}]},
    ]
    out = _downgrade_old_images(messages)
    assert len(out) == 2
    assert "image_url" in out[0]["content"][0]
    assert "image_url" in out[1]["content"][0]


def test_downgrade_cold_steps_text_block():
    """Test 6 & 7: 第 4+ 步之前图片转为纯文本 block，结构符合 schema"""
    messages = [
        {
            "role": "user", 
            "content": [
                {"type": "image_url", "image_url": {"url": "oldest"}},
                {"type": "text", "text": "ANCHORS: foo"}
            ]
        }
    ]
    # Add dummy hot steps to push the first one out of the hot window
    for i in range(_VISUAL_HOT_STEPS):
        messages.append({"role": "user", "content": f"hot {i}"})
        
    out = _downgrade_old_images(messages)
    assert len(out) == 1 + _VISUAL_HOT_STEPS
    
    # Check the cold message
    cold = out[0]
    assert len(cold["content"]) == 1
    assert cold["content"][0]["type"] == "text"
    assert "ANCHORS: foo" in cold["content"][0]["text"]
    assert "视觉快照已折叠" in cold["content"][0]["text"]
