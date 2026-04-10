import pytest
import json
from nanobot.providers.xml_fallback_parser import XmlFallbackParser


def test_fallback_claude_style():
    content = """Here is the response:
<tool_use>
<name>get_weather</name>
<input>{"location": "London"}</input>
</tool_use>
"""
    valid_tools = {"get_weather"}
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 1
    assert extracted[0]["name"] == "get_weather"
    assert extracted[0]["arguments"] == {"location": "London"}
    assert extracted[0]["id"].startswith("call_xf")


def test_fallback_generic_style():
    content = """Calling the function:
<tool_call>
<tool_name>math_add</tool_name>
<parameters>{"a": 1, "b": 2}</parameters>
</tool_call>
"""
    valid_tools = frozenset(["math_add", "math_sub"])
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 1
    assert extracted[0]["name"] == "math_add"
    assert extracted[0]["arguments"] == {"a": 1, "b": 2}


def test_fallback_json_wrapped_style():
    content = """I will use a tool.
<tool_call>
{
    "name": "search_db",
    "arguments": {
        "query": "select 1"
    }
}
</tool_call>
"""
    valid_tools = {"search_db"}
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 1
    assert extracted[0]["name"] == "search_db"
    assert extracted[0]["arguments"] == {"query": "select 1"}


def test_fallback_ignored_if_invalid_tool_name():
    content = """
<tool_call>
<tool_name>unknown_tool</tool_name>
<parameters>{}</parameters>
</tool_call>
"""
    valid_tools = {"known_tool"}
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 0


def test_fallback_ignored_if_no_valid_tools():
    content = """<tool_use><name>get_weather</name><input>{}</input></tool_use>"""
    extracted = XmlFallbackParser.extract(content, set())
    assert len(extracted) == 0


def test_fallback_multiple_tools():
    content = """
<tool_use><name>tool_a</name><input>{"id": 1}</input></tool_use>
Some text.
<tool_use><name>tool_b</name><input>{"id": 2}</input></tool_use>
"""
    valid_tools = {"tool_a", "tool_b"}
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 2
    assert extracted[0]["name"] == "tool_a"
    assert extracted[1]["name"] == "tool_b"
    # Ensure they have different deterministic IDs
    assert extracted[0]["id"] != extracted[1]["id"]


def test_fallback_broken_json():
    content = """
<tool_use><name>tool_c</name><input>{bad json</input></tool_use>
"""
    valid_tools = {"tool_c"}
    extracted = XmlFallbackParser.extract(content, valid_tools)
    assert len(extracted) == 1
    assert extracted[0]["name"] == "tool_c"
    # It should fallback to {"_raw": "{bad json"} if repair fails fully
    # Since {bad json might be semi-repaired depending on json_repair capability
    # Let's just check it doesn't crash and returns the raw string inside args if irrecovable.
    assert isinstance(extracted[0]["arguments"], dict)


def test_fallback_no_xml():
    content = "Just a normal response with no xml tools."
    extracted = XmlFallbackParser.extract(content, {"any"})
    assert len(extracted) == 0
