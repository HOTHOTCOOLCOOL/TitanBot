"""Nanobot unified exception hierarchy.

Phase 55 Architecture Maintenance: Centralize all custom exceptions here
to enable structured error handling in manager.py, providers, and tools.

Hierarchy:
    NanobotError
    ├── ProviderExecutionError
    ├── ToolExecutionError
    └── SessionPersistenceError
"""

__all__ = [
    "NanobotError",
    "ProviderExecutionError",
    "ToolExecutionError",
    "SessionPersistenceError",
    "ToolValidationFailure",
    "SkillLoadError",
]


class NanobotError(Exception):
    """Base class for all Nanobot custom exceptions."""


class ProviderExecutionError(NanobotError):
    """LLM Provider execution failed (timeout / parse error / auth error).

    Raised by provider implementations (LiteLLMProvider, etc.) when a
    non-retryable or terminal failure occurs during LLM invocation.
    """


class ToolExecutionError(NanobotError):
    """Tool execution failed (permission denied / sandbox blocked / runtime error).

    Raised by Tool implementations when the underlying operation cannot be
    completed. The message is safe to surface to the agent loop for LLM
    awareness.
    """


class ToolValidationFailure(ToolExecutionError):
    """
    Raised by a Skill's validator.py before execution begins.
    The message is safe to surface directly to the LLM message queue.
    """
    def __init__(self, reason: str, skill_name: str):
        super().__init__(f"[{skill_name}] Pre-flight validation blocked: {reason}")
        self.skill_name = skill_name
        self.reason = reason


class SkillLoadError(NanobotError):
    """Raised when a skill fails to load (e.g. validator AST block)."""


class SessionPersistenceError(NanobotError):
    """Session persistence failed (disk write error / serialization failure).

    Raised by SessionManager when a session cannot be saved to disk, allowing
    the agent loop to degrade gracefully rather than silently losing state.
    """


class AzureContentFilterException(ProviderExecutionError):
    """Azure OpenAI content filter blocking exception (HTTP 400 content_filter).

    Raised when the API returns a 400 error due to content filtering, ensuring
    it is not retried and can trigger graceful pause.
    """
