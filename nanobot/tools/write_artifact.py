import json
from pathlib import Path

from nanobot.agent.capability import CapabilityTag
from nanobot.tools.base import BaseTool


class WriteArtifactTool(BaseTool):
    """
    Write a structured implementation plan artifact to workspace.

    High-Risk: requires HITL approval so the user can review the plan
    before execution begins. This is Nanobot's Planning Mode equivalent.
    """
    static_tags = CapabilityTag.FILE_WRITE | CapabilityTag.IS_HIGH_RISK

    name = "write_artifact"
    description = (
        "Write an implementation plan, ADR, or task breakdown to disk. "
        "ALWAYS use this tool first when the user requests a complex "
        "multi-step operation (refactoring, migration, bulk deletion). "
        "The plan will be reviewed by the user before execution proceeds."
    )

    async def execute(self, path: str, content: str) -> str:
        artifact_path = Path(self.workspace) / path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return f"Artifact written to {path}. Awaiting user approval to proceed."
