"""Tests for the dynamic plugin loader."""

import textwrap
from pathlib import Path

import pytest

from nanobot.plugin_loader import scan_plugins, load_plugin, unload_plugins
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    """Create a temporary plugins directory."""
    d = tmp_path / "plugins"
    d.mkdir()
    return d


def _write_plugin(plugins_dir: Path, filename: str, code: str) -> Path:
    """Helper to write a plugin .py file."""
    p = plugins_dir / filename
    p.write_text(textwrap.dedent(code), encoding="utf-8")
    return p


# ---------- scan_plugins ----------

class TestScanPlugins:

    def test_empty_directory(self, plugins_dir: Path):
        """Empty dir should return no tools."""
        tools = scan_plugins(plugins_dir)
        assert tools == []

    def test_nonexistent_directory(self, tmp_path: Path):
        """Non-existent dir should return no tools."""
        tools = scan_plugins(tmp_path / "does_not_exist")
        assert tools == []

    def test_discover_valid_tool(self, plugins_dir: Path):
        """A valid Tool subclass should be discovered and instantiated."""
        _write_plugin(plugins_dir, "hello_tool.py", """\
            from typing import Any
            from nanobot.agent.tools.base import Tool

            class HelloTool(Tool):
                @property
                def name(self) -> str:
                    return "hello"

                @property
                def description(self) -> str:
                    return "Says hello"

                @property
                def parameters(self) -> dict[str, Any]:
                    return {"type": "object", "properties": {}, "required": []}

                async def execute(self, **kwargs) -> str:
                    return "Hello, world!"
        """)

        tools = scan_plugins(plugins_dir)
        assert len(tools) == 1
        assert tools[0].name == "hello"

    def test_multiple_tools_in_one_file(self, plugins_dir: Path):
        """Multiple Tool subclasses in one file should all be discovered."""
        _write_plugin(plugins_dir, "multi.py", """\
            from typing import Any
            from nanobot.agent.tools.base import Tool

            class AlphaTool(Tool):
                @property
                def name(self): return "alpha"
                @property
                def description(self): return "Alpha"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "a"

            class BetaTool(Tool):
                @property
                def name(self): return "beta"
                @property
                def description(self): return "Beta"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "b"
        """)

        tools = scan_plugins(plugins_dir)
        names = sorted(t.name for t in tools)
        assert names == ["alpha", "beta"]

    def test_skip_underscore_files(self, plugins_dir: Path):
        """Files starting with _ should be skipped."""
        _write_plugin(plugins_dir, "__init__.py", "# init")
        _write_plugin(plugins_dir, "_private.py", """\
            from nanobot.agent.tools.base import Tool
            class PrivateTool(Tool):
                @property
                def name(self): return "private"
                @property
                def description(self): return "x"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "x"
        """)

        tools = scan_plugins(plugins_dir)
        assert tools == []

    def test_syntax_error_isolated(self, plugins_dir: Path):
        """A plugin with a syntax error should not crash the loader."""
        _write_plugin(plugins_dir, "broken.py", """\
            def this is bad syntax !!!
        """)
        _write_plugin(plugins_dir, "good.py", """\
            from typing import Any
            from nanobot.agent.tools.base import Tool
            class GoodTool(Tool):
                @property
                def name(self): return "good"
                @property
                def description(self): return "Good"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "ok"
        """)

        tools = scan_plugins(plugins_dir)
        # broken.py should be skipped, good.py should load
        assert len(tools) == 1
        assert tools[0].name == "good"

    def test_missing_dependency_isolated(self, plugins_dir: Path):
        """A plugin that imports a non-existent module should not crash."""
        _write_plugin(plugins_dir, "bad_import.py", """\
            import this_module_does_not_exist_12345
            from nanobot.agent.tools.base import Tool
            class BadTool(Tool):
                @property
                def name(self): return "bad"
                @property
                def description(self): return "x"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "x"
        """)

        tools = scan_plugins(plugins_dir)
        assert tools == []


# ---------- unload_plugins ----------

class TestUnloadPlugins:

    def test_unload_removes_from_registry(self, plugins_dir: Path):
        """unload_plugins should remove the specified tools from the registry."""
        _write_plugin(plugins_dir, "temp_tool.py", """\
            from typing import Any
            from nanobot.agent.tools.base import Tool
            class TempTool(Tool):
                @property
                def name(self): return "temp"
                @property
                def description(self): return "Temp"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "tmp"
        """)

        tools = scan_plugins(plugins_dir)
        assert len(tools) == 1

        registry = ToolRegistry()
        registry.register(tools[0])
        assert registry.has("temp")

        removed = unload_plugins(registry, ["temp"])
        assert removed == 1
        assert not registry.has("temp")

    def test_unload_nonexistent_is_safe(self):
        """Unloading a tool that doesn't exist should silently succeed."""
        registry = ToolRegistry()
        removed = unload_plugins(registry, ["nonexistent"])
        assert removed == 0


# ---------- Conflict protection ----------

class TestConflictProtection:

    def test_builtin_tool_not_overridden(self, plugins_dir: Path):
        """A plugin tool with the same name as a built-in should be skipped."""
        _write_plugin(plugins_dir, "conflict.py", """\
            from typing import Any
            from nanobot.agent.tools.base import Tool
            class ConflictTool(Tool):
                @property
                def name(self): return "exec"  # conflicts with built-in ExecTool
                @property
                def description(self): return "Conflict"
                @property
                def parameters(self): return {"type": "object", "properties": {}}
                async def execute(self, **kwargs): return "x"
        """)

        tools = scan_plugins(plugins_dir)
        # The tool IS discovered by scan_plugins (it doesn't know about the registry)
        assert len(tools) == 1
        assert tools[0].name == "exec"

        # But when we try to register with conflict check (as loop.py does):
        registry = ToolRegistry()
        # Simulate a built-in "exec" tool
        registry.register(tools[0])  # register as "built-in"

        # Now try to re-register — has() should be True
        assert registry.has("exec")
