from pathlib import Path
from typing import Any

from nanobot.agent.capability import CapabilityTag
from nanobot.agent.tools.base import Tool


class WriteArtifactTool(Tool):
    """Write a reviewable planning artifact inside the active workspace."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()

    @property
    def name(self) -> str:
        return "write_artifact"

    @property
    def description(self) -> str:
        return (
            "Write an implementation plan, ADR, or task breakdown to disk. "
            "Use this first for complex multi-step work such as migrations, "
            "large refactors, or bulk edits. Prefer writing "
            "'implementation_plan.md' before any mutating execution."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative artifact path. "
                        "For complex execution planning, use 'implementation_plan.md'."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The artifact contents to write.",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        }

    @property
    def static_tags(self) -> CapabilityTag:
        # Planning artifacts are intentionally review-gated, but not destructive.
        return CapabilityTag.DATA_WRITE | CapabilityTag.MUTATIVE | CapabilityTag.SENSITIVE

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        artifact_path = self._resolve_artifact_path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return f"Artifact written to {artifact_path.relative_to(self.workspace)}. Awaiting user approval to proceed."

    def _resolve_artifact_path(self, path: str) -> Path:
        candidate = (self.workspace / path).resolve()
        if not candidate.is_relative_to(self.workspace):
            raise PermissionError(
                f"Path {path!r} is outside workspace {self.workspace}"
            )
        return candidate
