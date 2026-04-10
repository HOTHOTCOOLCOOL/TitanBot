import asyncio
import uuid
import pytest
from loguru import logger
from nanobot.utils.trace_context import (
    _trace_id_var,
    _route_tags_var,
    generate_trace_id,
    get_current_trace_id,
    add_route_tag,
    get_route_tags,
    trace_log_patcher,
    RoutingTag,
    InterceptTag,
)

@pytest.mark.asyncio
async def test_context_isolation_between_tasks():
    """Ensure contextvars do not leak between async tasks."""
    
    async def worker(task_name: str, expected_trace: str):
        _trace_id_var.set(expected_trace)
        _route_tags_var.set(frozenset())
        add_route_tag(task_name)
        
        await asyncio.sleep(0.1)  # Yield control to allow interleaving
        
        assert get_current_trace_id() == expected_trace
        assert f"{task_name}" in get_route_tags()
        
    t1 = asyncio.create_task(worker("tag-A", "t-11111111"))
    t2 = asyncio.create_task(worker("tag-B", "t-22222222"))
    
    await asyncio.gather(t1, t2)
    
    # Main context should be untouched
    assert get_current_trace_id() == "no-trace"
    assert get_route_tags() == frozenset()

def test_log_patcher_safety():
    """Ensure patcher never raises an exception."""
    record = {"message": "hello world"}
    
    # Should not raise exception
    trace_log_patcher(record)
    assert record["message"] == "hello world"  # Default no-trace
    
    _trace_id_var.set("t-12345678")
    trace_log_patcher(record)
    assert "[t-12345678] hello world" in record["message"]
    
    # Simulate a corrupted record
    bad_record = {}
    trace_log_patcher(bad_record)  # Should gracefully catch KeyError and do nothing
    assert "message" not in bad_record

def test_route_tag_idempotent():
    """Ensure add_route_tag uses frozenset and is idempotent."""
    _route_tags_var.set(frozenset())
    
    add_route_tag(InterceptTag.L1_BLOCK)
    add_route_tag(InterceptTag.L1_BLOCK)  # Duplicate
    add_route_tag(RoutingTag.VLM_ROUTE)
    
    tags = get_route_tags()
    assert len(tags) == 2
    assert InterceptTag.L1_BLOCK in tags
    assert RoutingTag.VLM_ROUTE in tags

def test_generate_trace_id():
    """Ensure generated trace IDs match the prefix pattern."""
    tid = generate_trace_id()
    assert tid.startswith("t-")
    assert len(tid) == 10  # t- + 8 hex chars
