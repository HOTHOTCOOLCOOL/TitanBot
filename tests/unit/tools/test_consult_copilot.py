from __future__ import annotations

import httpx
import pytest

from nanobot.config.schema import Config, ToolsConfig


class _FakeResponse:
    def __init__(
        self,
        *,
        json_data: dict | None = None,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self._json_data = json_data or {}
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://directline.botframework.com/")
            response = httpx.Response(
                self.status_code,
                request=request,
                text=self.text or "request failed",
            )
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=response,
            )


class _FakeAsyncClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def _next(self, method: str, url: str, **kwargs) -> _FakeResponse:
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError(f"No fake response left for {method} {url}")
        return self._responses.pop(0)

    async def post(self, url: str, **kwargs) -> _FakeResponse:
        return self._next("POST", url, **kwargs)

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        return self._next("GET", url, **kwargs)


def test_copilot_studio_schema_exists():
    """Ensure ToolsConfig has copilot_studio field."""
    config = ToolsConfig()
    assert hasattr(config, "copilot_studio")
    assert config.copilot_studio.enabled is False
    assert hasattr(config.copilot_studio, "secret")
    assert config.copilot_studio.secret == ""


def test_copilot_tool_import():
    """Ensure ConsultCopilotTool exists and inherits correctly."""
    from nanobot.agent.tools.base import Tool
    from nanobot.agent.tools.consult_copilot import ConsultCopilotTool

    assert issubclass(ConsultCopilotTool, Tool)
    assert ConsultCopilotTool.name == "consult_copilot_studio"


async def test_execute_returns_error_when_secret_missing(monkeypatch: pytest.MonkeyPatch):
    from nanobot.agent.tools.consult_copilot import ConsultCopilotTool

    config = Config()
    monkeypatch.setattr("nanobot.agent.tools.consult_copilot.get_config", lambda: config)

    tool = ConsultCopilotTool()
    result = await tool.execute(prompt="hello")

    assert result.startswith("Error:")
    assert "tools.copilot_studio.secret" in result


async def test_execute_happy_path(monkeypatch: pytest.MonkeyPatch):
    from nanobot.agent.tools.consult_copilot import ConsultCopilotTool

    config = Config()
    config.tools.copilot_studio.enabled = True
    config.tools.copilot_studio.secret = "secret"

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(json_data={"token": "token-1"}),
            _FakeResponse(json_data={"conversationId": "conv-1", "token": "token-2"}),
            _FakeResponse(json_data={"id": "event-1"}),
            _FakeResponse(json_data={"id": "message-1"}),
            _FakeResponse(
                json_data={
                    "watermark": "1",
                    "activities": [
                        {
                            "type": "message",
                            "from": {"id": "copilot", "name": "Copilot Studio"},
                            "text": "Final answer",
                        }
                    ],
                }
            ),
        ]
    )

    monkeypatch.setattr("nanobot.agent.tools.consult_copilot.get_config", lambda: config)
    monkeypatch.setattr(
        "nanobot.agent.tools.consult_copilot.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    tool = ConsultCopilotTool()
    result = await tool.execute(prompt="Summarize this")

    assert result == "Final answer"
    assert len(fake_client.calls) == 5
    assert fake_client.calls[0][1].endswith("/tokens/generate")
    assert fake_client.calls[1][1].endswith("/conversations")
    assert fake_client.calls[3][1].endswith("/activities")


async def test_execute_returns_timeout_when_bot_never_replies(monkeypatch: pytest.MonkeyPatch):
    from nanobot.agent.tools.consult_copilot import ConsultCopilotTool

    config = Config()
    config.tools.copilot_studio.enabled = True
    config.tools.copilot_studio.secret = "secret"

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(json_data={"token": "token-1"}),
            _FakeResponse(json_data={"conversationId": "conv-1", "token": "token-2"}),
            _FakeResponse(json_data={"id": "event-1"}),
            _FakeResponse(json_data={"id": "message-1"}),
        ]
    )

    monkeypatch.setattr("nanobot.agent.tools.consult_copilot.get_config", lambda: config)
    monkeypatch.setattr(
        "nanobot.agent.tools.consult_copilot.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )
    monkeypatch.setattr(ConsultCopilotTool, "_RESPONSE_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setattr(ConsultCopilotTool, "_POLL_INTERVAL_SECONDS", 0.0)

    tool = ConsultCopilotTool()
    result = await tool.execute(prompt="hello")

    assert result.startswith("Error:")
    assert "did not respond" in result


async def test_execute_surfaces_http_errors(monkeypatch: pytest.MonkeyPatch):
    from nanobot.agent.tools.consult_copilot import ConsultCopilotTool

    config = Config()
    config.tools.copilot_studio.enabled = True
    config.tools.copilot_studio.secret = "secret"

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                status_code=403,
                text="IntegratedAuthenticationNotSupportedInChannel",
            ),
        ]
    )

    monkeypatch.setattr("nanobot.agent.tools.consult_copilot.get_config", lambda: config)
    monkeypatch.setattr(
        "nanobot.agent.tools.consult_copilot.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    tool = ConsultCopilotTool()
    result = await tool.execute(prompt="hello")

    assert result.startswith("Error: Copilot Studio request failed (403)")
    assert "IntegratedAuthenticationNotSupportedInChannel" in result
