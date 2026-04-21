"""
BFF Gateway - Configuration Loader

All BFF config is loaded from environment variables (via .env file).
Uses BFF_ prefix to avoid collision with Nanobot's own environment.
"""

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env from the bff/ directory (wherever this script runs from)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


@dataclass
class BFFConfig:
    # Server
    host: str = "127.0.0.1"
    port: int = 8099

    # Auth
    tokens_path: str = "./user_tokens.json"
    rate_limit_rpm: int = 60

    # Upstream provider
    upstream_provider: str = "azure"          # "azure" | "anthropic" | "openai" | "deepseek" etc.
    azure_api_key: str = ""
    azure_api_base: str = ""
    azure_api_version: str = "2024-08-01-preview"

    # For non-Azure providers (anthropic / openai / deepseek)
    generic_api_key: str = ""
    generic_api_base: str = ""

    # Model mapping: client model name -> upstream deployment/model id
    # Example: {"gpt-4o": "azure/gpt4o-prod", "claude-opus-4-5": "anthropic/claude-opus-4-5"}
    model_map: dict[str, str] = field(default_factory=dict)

    # Upstream timeout (seconds) - protects against upstream hangs
    upstream_timeout: int = 120


def load_config() -> BFFConfig:
    """Load BFF configuration from environment variables."""

    model_map_raw = os.getenv("BFF_MODEL_MAP", "{}")
    try:
        model_map = json.loads(model_map_raw)
    except json.JSONDecodeError:
        model_map = {}

    return BFFConfig(
        host=os.getenv("BFF_HOST", "127.0.0.1"),
        port=int(os.getenv("BFF_PORT", "8099")),
        tokens_path=os.getenv("BFF_TOKENS_PATH", "./user_tokens.json"),
        rate_limit_rpm=int(os.getenv("BFF_RATE_LIMIT_RPM", "60")),
        upstream_provider=os.getenv("BFF_UPSTREAM_PROVIDER", "azure"),
        azure_api_key=os.getenv("BFF_AZURE_API_KEY", ""),
        azure_api_base=os.getenv("BFF_AZURE_API_BASE", ""),
        azure_api_version=os.getenv("BFF_AZURE_API_VERSION", "2024-08-01-preview"),
        generic_api_key=os.getenv("BFF_GENERIC_API_KEY", ""),
        generic_api_base=os.getenv("BFF_GENERIC_API_BASE", ""),
        model_map=model_map,
        upstream_timeout=int(os.getenv("BFF_UPSTREAM_TIMEOUT", "120")),
    )
