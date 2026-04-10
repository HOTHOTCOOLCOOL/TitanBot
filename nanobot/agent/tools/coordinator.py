from nanobot.agent.tools.base import BaseTool, Parameter, RiskTier
from typing import Any

class CoordinatorTool(BaseTool):
    """
    Tool for spawning truly isolated Worker subprocesses over JSON-RPC.
    Part of Phase 38 Coordinator Mode.
    """
    name = "coordinator"
    description = "Spawn or inspect truly independent background Worker subprocesses. Use this to run long, isolated tasks in parallel without blocking."
    parameters = [
        Parameter("action", str, "Action to perform: 'spawn' or 'list'", required=True),
        Parameter("task", str, "Task description if spawning. Must be highly detailed.", required=False),
        Parameter("label", str, "Short label for the worker if spawning (max 30 chars)", required=False)
    ]

    def __init__(self, coordinator_manager: Any):
        super().__init__()
        self.coordinator = coordinator_manager
        self.channel = "cli"
        self.chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self.channel = channel
        self.chat_id = chat_id

    def get_risk_tier(self, params: dict[str, Any]) -> RiskTier:
        # Phase 38: Enforce HITL approval before spawning any subprocess
        return RiskTier.MUTATE_EXTERNAL 

    async def execute(self, action: str, **kwargs) -> str | dict[str, Any]:
        if action == "list":
            cnt = self.coordinator.get_running_count()
            workers = []
            for tid, info in self.coordinator.workers.items():
                workers.append(f"- Worker {tid} ({info.get('label')}): port={info['port']}, PID={info['process'].pid}")
            details = "\n".join(workers)
            return f"Currently {cnt} worker(s) running:\n{details}" if cnt > 0 else "No workers currently running."
            
        elif action == "spawn":
            task = kwargs.get("task")
            if not task:
                return "Error: 'task' parameter is required for spawn action."
            label = kwargs.get("label")
            
            return await self.coordinator.spawn(
                task=task,
                label=label,
                origin_channel=self.channel,
                origin_chat_id=self.chat_id
            )
        else:
            return f"Error: Unknown action '{action}'"
