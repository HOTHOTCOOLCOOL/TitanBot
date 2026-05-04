import asyncio
"""File system tools: read, write, edit."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.capability import CapabilityTag


def _resolve_path(
    path: str,
    allowed_dir: Path | None = None,
    forbidden_dirs: list[Path] | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Resolve a path and optionally enforce whitelist/blacklist restrictions.

    Relative paths are resolved against ``base_dir`` when provided; otherwise
    they retain the legacy behavior of resolving against the current process
    working directory.
    """
    target = Path(path).expanduser()
    if not target.is_absolute() and base_dir is not None:
        target = base_dir / target

    resolved = target.resolve()
    if allowed_dir and not resolved.is_relative_to(allowed_dir.resolve()):
        raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")
    if forbidden_dirs:
        for fdir in forbidden_dirs:
            if resolved == fdir.resolve() or resolved.is_relative_to(fdir.resolve()):
                raise PermissionError(f"Path {path} is inside forbidden directory {fdir}")
    return resolved


class ReadFileTool(Tool):
    """Tool to read file contents."""
    
    def __init__(
        self,
        allowed_dir: Path | None = None,
        forbidden_dirs: list[Path] | None = None,
        base_dir: Path | None = None,
    ):
        self._allowed_dir = allowed_dir
        self._forbidden_dirs = forbidden_dirs
        self._base_dir = base_dir

    @property
    def name(self) -> str:
        return "read_file"
    
    _MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB


    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.DATA_READ

    
    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            file_path = _resolve_path(
                path,
                self._allowed_dir,
                self._forbidden_dirs,
                self._base_dir,
            )
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"
            
            if file_path.stat().st_size > self._MAX_READ_BYTES:
                content = file_path.read_text(encoding="utf-8")[:self._MAX_READ_BYTES]
                return f"{content}\n\n[CONTENT TRUNCATED: file exceeds 5MB limit]"
            
            content = file_path.read_text(encoding="utf-8")
            return content
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """Tool to write content to a file."""
    
    _MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        allowed_dir: Path | None = None,
        forbidden_dirs: list[Path] | None = None,
        base_dir: Path | None = None,
    ):
        self._allowed_dir = allowed_dir
        self._forbidden_dirs = forbidden_dirs
        self._base_dir = base_dir

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.DATA_WRITE | CapabilityTag.MUTATIVE

    
    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        # R6: Reject oversized writes to prevent disk exhaustion
        if len(content.encode("utf-8")) > self._MAX_WRITE_BYTES:
            return f"Error: Content too large ({len(content)} chars). Max write size is 10MB."
        try:
            file_path = _resolve_path(
                path,
                self._allowed_dir,
                self._forbidden_dirs,
                self._base_dir,
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""
    
    def __init__(
        self,
        allowed_dir: Path | None = None,
        forbidden_dirs: list[Path] | None = None,
        base_dir: Path | None = None,
    ):
        self._allowed_dir = allowed_dir
        self._forbidden_dirs = forbidden_dirs
        self._base_dir = base_dir

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.DATA_WRITE | CapabilityTag.MUTATIVE

    
    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        try:
            file_path = _resolve_path(
                path,
                self._allowed_dir,
                self._forbidden_dirs,
                self._base_dir,
            )
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."
            
            # Count occurrences
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
            
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            
            return f"Successfully edited {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """Tool to list directory contents."""
    
    def __init__(
        self,
        allowed_dir: Path | None = None,
        forbidden_dirs: list[Path] | None = None,
        base_dir: Path | None = None,
    ):
        self._allowed_dir = allowed_dir
        self._forbidden_dirs = forbidden_dirs
        self._base_dir = base_dir

    @property
    def name(self) -> str:
        return "list_dir"
    
    _MAX_ITEMS = 500


    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.DATA_READ

    
    @property
    def description(self) -> str:
        return "List the contents of a directory."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            dir_path = _resolve_path(
                path,
                self._allowed_dir,
                self._forbidden_dirs,
                self._base_dir,
            )
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"
            
            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")
            
            if not items:
                return f"Directory {path} is empty"
            
            if len(items) > self._MAX_ITEMS:
                truncated = len(items) - self._MAX_ITEMS
                items = items[:self._MAX_ITEMS]
                items.append(f"... and {truncated} more items")
            
            return "\n".join(items)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            return f"Error listing directory: {str(e)}"
