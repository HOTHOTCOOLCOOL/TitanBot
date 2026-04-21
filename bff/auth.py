"""
BFF Gateway - Authentication Module (PoC / MockAuthenticator)

TODO(Prod Phase 2): Replace MockAuthenticator with JWTAuthenticator
  - Use JWT RS256 tokens signed by company OIDC provider (Azure Entra ID)
  - Validate using JWKS endpoint: https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys
  - Extract user_id from JWT 'sub' or 'preferred_username' claim
"""

import json
import os
from pathlib import Path

from loguru import logger


class MockAuthenticator:
    """
    PoC-grade authenticator: validates Bearer tokens against a local JSON file.

    user_tokens.json format:
        { "token_string": "user_id", ... }

    TODO(Prod Phase 2): Replace with JWTAuthenticator using Azure Entra ID OIDC.
    """

    def __init__(self, tokens_path: str | None = None):
        path = tokens_path or os.getenv("BFF_TOKENS_PATH", "./user_tokens.json")
        self._tokens: dict[str, str] = {}
        self._load(path)

    def _load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            logger.warning(f"[Auth] user_tokens.json not found at '{path}'. All requests will be rejected.")
            return
        try:
            with p.open(encoding="utf-8") as f:
                self._tokens = json.load(f)
            logger.info(f"[Auth] Loaded {len(self._tokens)} user token(s) from '{path}'")
        except Exception as e:
            logger.error(f"[Auth] Failed to load tokens from '{path}': {e}")

    def authenticate(self, token: str) -> str | None:
        """
        Validate token and return user_id if valid, else None.
        Strips 'Bearer ' prefix if present.
        """
        token = token.removeprefix("Bearer ").strip()
        return self._tokens.get(token)
