"""Consult a Copilot Studio agent via the Direct Line API."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from nanobot.agent.capability import CapabilityTag
from nanobot.agent.tools.base import Tool
from nanobot.config.loader import get_config

_DIRECT_LINE_BASE = "https://directline.botframework.com/v3/directline"
_USER_ID = "nanobot_consult_user"
_USER_NAME = "Nanobot"


class ConsultCopilotTool(Tool):
    """Ask a Copilot Studio agent for a second opinion or enterprise context."""

    name = "consult_copilot_studio"
    description = (
        "Consult an external Copilot Studio agent over Direct Line. "
        "Use this for a second opinion, enterprise knowledge questions, "
        "or large-text synthesis when Copilot Studio is configured."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Question or instructions to send to Copilot Studio.",
                "minLength": 1,
            }
        },
        "required": ["prompt"],
    }

    _HTTP_TIMEOUT_SECONDS = 30.0
    _RESPONSE_TIMEOUT_SECONDS = 45.0
    _POLL_INTERVAL_SECONDS = 1.0

    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.INFO_RETRIEVAL

    async def execute(self, prompt: str, **kwargs: Any) -> str:
        prompt = prompt.strip()
        if not prompt:
            return "Error: prompt parameter is required."

        config = getattr(get_config().tools, "copilot_studio", None)
        if config is None or not config.secret:
            return (
                "Error: Copilot Studio is not configured. "
                "Set tools.copilot_studio.secret in config.json."
            )
        if not getattr(config, "enabled", False):
            return (
                "Error: Copilot Studio tool is disabled. "
                "Set tools.copilot_studio.enabled=true in config.json."
            )

        timeout = httpx.Timeout(self._HTTP_TIMEOUT_SECONDS, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                token = await self._generate_token(client, config.secret)
                conversation_id, token = await self._start_conversation(client, token)
                await self._send_start_event(client, token, conversation_id)
                await self._send_message(client, token, conversation_id, prompt)
                reply = await self._poll_for_reply(client, token, conversation_id)
                if reply:
                    return reply
        except httpx.TimeoutException:
            return "Error: Copilot Studio request timed out."
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            detail = ""
            if exc.response is not None and exc.response.text:
                detail = exc.response.text.strip()
            elif str(exc):
                detail = str(exc)
            suffix = f": {detail}" if detail else ""
            return f"Error: Copilot Studio request failed ({status}){suffix}"
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            return f"Error: {exc}"

        return (
            "Error: Copilot Studio did not respond within "
            f"{int(self._RESPONSE_TIMEOUT_SECONDS)} seconds."
        )

    async def _generate_token(self, client: httpx.AsyncClient, secret: str) -> str:
        response = await client.post(
            f"{_DIRECT_LINE_BASE}/tokens/generate",
            headers={"Authorization": f"Bearer {secret}"},
        )
        response.raise_for_status()
        return response.json()["token"]

    async def _start_conversation(
        self, client: httpx.AsyncClient, token: str
    ) -> tuple[str, str]:
        response = await client.post(
            f"{_DIRECT_LINE_BASE}/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()
        return payload["conversationId"], payload.get("token", token)

    async def _send_start_event(
        self, client: httpx.AsyncClient, token: str, conversation_id: str
    ) -> None:
        response = await client.post(
            f"{_DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "type": "event",
                "name": "startConversation",
                "from": {"id": _USER_ID, "name": _USER_NAME},
            },
        )
        response.raise_for_status()

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        token: str,
        conversation_id: str,
        prompt: str,
    ) -> None:
        response = await client.post(
            f"{_DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "type": "message",
                "from": {"id": _USER_ID, "name": _USER_NAME},
                "text": prompt,
                "textFormat": "plain",
                "locale": "en-US",
            },
        )
        response.raise_for_status()

    async def _poll_for_reply(
        self,
        client: httpx.AsyncClient,
        token: str,
        conversation_id: str,
    ) -> str | None:
        start = time.monotonic()
        watermark: str | None = None

        while time.monotonic() - start < self._RESPONSE_TIMEOUT_SECONDS:
            params = {"watermark": watermark} if watermark else None
            response = await client.get(
                f"{_DIRECT_LINE_BASE}/conversations/{conversation_id}/activities",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            watermark = payload.get("watermark", watermark)

            replies = [
                activity.get("text", "").strip()
                for activity in payload.get("activities", [])
                if activity.get("type") == "message"
                and activity.get("from", {}).get("id") != _USER_ID
                and activity.get("text")
            ]
            if replies:
                return replies[-1]

            await asyncio.sleep(self._POLL_INTERVAL_SECONDS)

        return None
