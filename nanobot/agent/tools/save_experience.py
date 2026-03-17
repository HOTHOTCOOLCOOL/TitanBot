from typing import Any
from pydantic import Field

from nanobot.agent.tools.base import Tool


class SaveExperienceTool(Tool):
    """Tool for the agent to proactively save action-level tactical hints/experiences.
    
    This is part of the Phase 12 Knowledge System Upgrade (Experience Bank).
    When the agent figures out a specific workaround, flag, or localized prompt
    needed to bypass an error or handle a specific system state, it can save it
    here. It will be injected automatically in similar future contexts.
    """

    name: str = "save_experience"
    description: str = (
        "Save an action-level tactical hint or workaround to the Experience Bank. "
        "Use this when you figure out how to solve a specific error or discover "
        "a tricky required parameter/flag. Do NOT use this for entire task workflows; "
        "those are saved automatically at the end of the task."
    )
    
    trigger: str = Field(
        ...,
        description="The context that should trigger this hint. E.g., a specific error message snippet, or a specific tool name + target."
    )
    prompt: str = Field(
        ...,
        description="The tactical hint to inject. E.g., 'When running git commit, always use -m to avoid the editor opening.'"
    )

    def __init__(self, knowledge_store: Any = None):
        super().__init__()
        self.knowledge_store = knowledge_store

    async def _execute(self, trigger: str, prompt: str) -> str:
        """Save the experience tactical prompt."""
        if not self.knowledge_store:
            return "Failed to save: Knowledge system is disabled in this session."
            
        try:
            self.knowledge_store.add_experience(trigger=trigger, prompt=prompt)
            return f"Successfully saved tactical experience for trigger: '{trigger}'"
        except Exception as e:
            return f"Error saving experience: {e}"
