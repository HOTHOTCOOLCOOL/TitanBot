def execute(action: str, step_name: str, status: str = "completed") -> str:
    """Update active task step status. action=update_step|complete_task|fail_task"""
    from nanobot.agent.task_tracker import get_active_tracker
    tracker = get_active_tracker()
    task = tracker.get_active_task() if tracker else None
    if not task:
        return "Error: No active task to update."
    
    if action == "update_step":
        tracker.update_step(task.task_id, step_name, status)
        return f"Step '{step_name}' updated to '{status}'."
    elif action == "complete_task":
        tracker.complete_task(task.task_id)
        return f"Task '{task.task_id}' marked as completed."
    elif action == "fail_task":
        tracker.fail_task(task.task_id, error=status)
        return f"Task '{task.task_id}' marked as failed."
    else:
        return f"Error: unknown action '{action}'"
