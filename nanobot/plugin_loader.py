"""Dynamic Plugin Loader for Nanobot.

Scans a specified directory for .py files, discovers classes that
inherit from Tool, and returns ready-to-register instances.

Usage:
    from nanobot.plugin_loader import scan_plugins
    tools = scan_plugins(Path("nanobot/plugins"))
    for tool in tools:
        registry.register(tool)
"""

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path

from loguru import logger

# NOTE: We do NOT import Tool at module level to avoid circular imports.
# The chain would be: plugin_loader → agent.tools.base → agent.__init__ → agent.loop → plugin_loader
# Instead, we import Tool lazily inside the functions that need it.


def load_plugin(file_path: Path) -> list:
    """Load a single .py file and return all Tool subclass instances found.

    If the file has a syntax error, missing import, or any
    other issue, the error is logged and an empty list is returned.

    Args:
        file_path: Absolute path to a .py file.

    Returns:
        List of instantiated Tool objects found in the module.
    """
    from nanobot.agent.tools.base import Tool

    module_name = f"nanobot_plugin_{file_path.stem}"
    tools: list = []

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            logger.warning(f"Plugin loader: cannot create spec for {file_path}")
            return tools

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # Must be a direct subclass of Tool (not Tool itself, not the base)
            if (
                issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module_name
            ):
                try:
                    instance = obj()
                    tools.append(instance)
                    logger.info(
                        f"Plugin loader: discovered tool '{instance.name}' "
                        f"from {file_path.name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Plugin loader: failed to instantiate {obj.__name__} "
                        f"from {file_path.name}: {e}"
                    )

    except Exception as e:
        logger.warning(f"Plugin loader: failed to load {file_path.name}: {e}")
        # Clean up the broken module
        sys.modules.pop(module_name, None)

    return tools


def scan_plugins(directory: Path) -> list:
    """Scan a directory for .py files and return all discovered Tool instances.

    Skips files starting with '_' (like __init__.py).

    Args:
        directory: Path to the plugins directory.

    Returns:
        List of instantiated Tool objects.
    """
    if not directory.exists():
        logger.debug(f"Plugin loader: directory {directory} does not exist, skipping")
        return []

    tools: list = []
    py_files = sorted(directory.glob("*.py"))

    for py_file in py_files:
        if py_file.name.startswith("_"):
            continue
        discovered = load_plugin(py_file)
        tools.extend(discovered)

    if tools:
        logger.info(
            f"Plugin loader: loaded {len(tools)} tool(s) from {directory}: "
            f"{', '.join(t.name for t in tools)}"
        )
    else:
        logger.debug(f"Plugin loader: no tools found in {directory}")

    return tools


def unload_plugins(registry: "ToolRegistry", plugin_names: list[str]) -> int:
    """Unregister previously loaded plugin tools from the registry.

    Args:
        registry: The ToolRegistry to unregister from.
        plugin_names: List of tool names to unregister.

    Returns:
        Number of tools unregistered.
    """
    count = 0
    for name in plugin_names:
        if registry.has(name):
            registry.unregister(name)
            count += 1
    return count
