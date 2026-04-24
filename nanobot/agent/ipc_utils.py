"""Shared Inter-Process Communication (IPC) boundary enforcement."""
import uuid
from pathlib import Path
from loguru import logger

_MAX_IPC_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5MB Hard limit (Azure OpenAI Schema Compliance limit)

def enforce_ipc_limit(payload: str, workspace: Path, process_name: str = "agent", worker_sandbox: Path | None = None) -> str:
    """Enforce a hard max size for IPC passage to protect Coordinator memory.
    
    If the payload exceeds 5MB, it is truncated and spilled to the sandbox disk.
    
    Args:
        payload: The raw string payload returned by an agent.
        workspace: Path to the root workspace.
        process_name: Identifier for the calling process (for semantic logging).
        
    Returns:
        The safe, truncated payload.
    """
    if not payload:
        return ""
        
    payload_bytes = payload.encode("utf-8")
    if len(payload_bytes) <= _MAX_IPC_PAYLOAD_BYTES:
        return payload
        
    # Overflow mitigation: Save to disk and append a notice
    overflow_id = uuid.uuid4().hex[:8]
    sandbox_dir = worker_sandbox if worker_sandbox else workspace / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    overflow_path = sandbox_dir / f"large_{process_name}_output_{overflow_id}.txt"
    overflow_path.write_bytes(payload_bytes)
    
    relative_path_for_logger = overflow_path.relative_to(workspace).as_posix()
    logger.warning(
        f"IPC Enforcement: {process_name} payload ({len(payload_bytes)} bytes) "
        f"exceeded 5MB limit. Overflow redirected to '{relative_path_for_logger}'."
    )
    
    # Truncate and alert
    head_size = 500_000
    tail_size = 500_000
    head_content = payload_bytes[:head_size].decode("utf-8", errors="ignore")
    tail_content = payload_bytes[-tail_size:].decode("utf-8", errors="ignore")
    
    relative_overflow_path = overflow_path.relative_to(workspace).as_posix()
    warning_notice = (
        f"\n\n[System Guard: IPC Payload Truncated]\n"
        f"The {process_name} returned {len(payload_bytes)} bytes, which exceeds the 5MB IPC memory barrier. "
        f"The full raw output has been saved functionally to '{relative_overflow_path}'. "
        f"You are seeing a truncated preview (first 500KB and last 500KB) to prevent context crash."
    )
    
    return f"{head_content}\n... [TRUNCATED] ...\n{tail_content}{warning_notice}"
