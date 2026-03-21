"""Save experience tool for storing tactical hints to the Experience Bank."""

from typing import Any

from nanobot.agent.tools.base import Tool


class SaveExperienceTool(Tool):
    """Tool for the agent to proactively save action-level tactical hints/experiences.
    
    This is part of the Phase 12 Knowledge System Upgrade (Experience Bank).
    When the agent figures out a specific workaround, flag, or localized prompt
    needed to bypass an error or handle a specific system state, it can save it
    here. It will be injected automatically in similar future contexts.
    """

    def __init__(self, knowledge_store: Any = None):
        self._knowledge_store = knowledge_store

    @property
    def name(self) -> str:
        return "save_experience"

    @property
    def description(self) -> str:
        return (
            "Save an action-level tactical hint or workaround to the Experience Bank. "
            "Use this when you figure out how to solve a specific error or discover "
            "a tricky required parameter/flag. Do NOT use this for entire task workflows; "
            "those are saved automatically at the end of the task."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "trigger": {
                    "type": "string",
                    "description": (
                        "The context that should trigger this hint. E.g., a specific "
                        "error message snippet, or a specific tool name + target."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "The tactical hint to inject. E.g., 'When running git commit, "
                        "always use -m to avoid the editor opening.'"
                    ),
                },
            },
            "required": ["trigger", "prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Save the experience tactical prompt."""
        trigger = kwargs.get("trigger", "")
        prompt = kwargs.get("prompt", "")

        if not self._knowledge_store:
            return "Failed to save: Knowledge system is disabled in this session."

        try:
            self._knowledge_store.add_experience(trigger=trigger, prompt=prompt)
            return f"Successfully saved tactical experience for trigger: '{trigger}'"
        except Exception as e:
            return f"Error saving experience: {e}"
