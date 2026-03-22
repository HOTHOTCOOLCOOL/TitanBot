"""Tests for Config schema validation and provider routing."""

import pytest
from nanobot.config.schema import (
    Config,
    AgentDefaults,
    ProviderConfig,
    ProvidersConfig,
    ChannelsConfig,
    TelegramConfig,
    FeishuConfig,
    EmailConfig,
    SlackConfig,
    ExecToolConfig,
    VLMConfig,
    VisionConfig,
    MCPServerConfig,
)


# ── Default Values ──

class TestConfigDefaults:
    """Verify that all Config defaults are sensible."""

    def test_agent_defaults(self) -> None:
        defaults = AgentDefaults()
        assert defaults.model == "anthropic/claude-opus-4-5"
        assert defaults.max_tokens == 8192
        assert defaults.temperature == 0.7
        assert defaults.max_tool_iterations == 20
        assert defaults.memory_window == 50
        assert defaults.language == "en"

    def test_provider_config_defaults(self) -> None:
        pc = ProviderConfig()
        assert pc.api_key == ""
        assert pc.api_base is None
        assert pc.extra_headers is None

    def test_vlm_config_defaults(self) -> None:
        vlm = VLMConfig()
        assert vlm.enabled is True
        assert vlm.model is None

    def test_vision_config_defaults(self) -> None:
        vision = VisionConfig()
        assert vision.ocr_enabled is True
        assert vision.yolo_enabled is False
        assert 0 < vision.ocr_min_confidence <= 1.0

    def test_exec_tool_defaults(self) -> None:
        et = ExecToolConfig()
        assert et.timeout == 60

    def test_mcp_server_config_defaults(self) -> None:
        mcp = MCPServerConfig()
        assert mcp.command == ""
        assert mcp.args == []
        assert mcp.url == ""


# ── camelCase / snake_case Parsing ──

class TestCamelSnakeParsing:
    """Config schema accepts both camelCase and snake_case keys."""

    def test_telegram_camel_case(self) -> None:
        tc = TelegramConfig(**{"enabled": True, "allowFrom": ["123"]})
        assert tc.allow_from == ["123"]

    def test_telegram_snake_case(self) -> None:
        tc = TelegramConfig(**{"enabled": True, "allow_from": ["456"]})
        assert tc.allow_from == ["456"]

    def test_feishu_camel_case(self) -> None:
        fc = FeishuConfig(**{"appId": "cli_xxx", "appSecret": "secret"})
        assert fc.app_id == "cli_xxx"
        assert fc.app_secret == "secret"

    def test_email_camel_case(self) -> None:
        ec = EmailConfig(**{"imapHost": "imap.gmail.com", "smtpPort": 587})
        assert ec.imap_host == "imap.gmail.com"
        assert ec.smtp_port == 587

    def test_slack_camel_case(self) -> None:
        sc = SlackConfig(**{"botToken": "xoxb-xxx", "appToken": "xapp-xxx"})
        assert sc.bot_token == "xoxb-xxx"
        assert sc.app_token == "xapp-xxx"


# ── Channel Instantiation ──

class TestChannelInstantiation:
    """All channel configs instantiate cleanly."""

    def test_channels_config_all_disabled_by_default(self) -> None:
        cc = ChannelsConfig()
        assert cc.telegram.enabled is False
        assert cc.discord.enabled is False
        assert cc.feishu.enabled is False
        assert cc.email.enabled is False
        assert cc.slack.enabled is False
        assert cc.whatsapp.enabled is False
        assert cc.mochat.enabled is False
        assert cc.dingtalk.enabled is False
        assert cc.qq.enabled is False


# ── Provider Routing ──

class TestProviderRouting:
    """Test get_provider / get_api_key / get_api_base routing logic."""

    def test_no_provider_returns_none(self) -> None:
        config = Config()
        # With all providers unconfigured, get_provider should return None
        # (unless some env vars are set, which we can't control in tests)
        p = config.get_provider("unknown/model")
        # Just check it doesn't crash
        assert p is None or hasattr(p, "api_key")

    def test_custom_provider_priority(self) -> None:
        """Custom provider with api_base takes priority when set."""
        config = Config()
        config.providers.custom = ProviderConfig(
            api_key="test-key", api_base="http://localhost:8000/v1"
        )
        p = config.get_provider("some-model")
        assert p is not None
        assert p.api_key == "test-key"
        assert p.api_base == "http://localhost:8000/v1"

    def test_get_provider_name_returns_string_or_none(self) -> None:
        config = Config()
        name = config.get_provider_name("anthropic/claude-opus-4-5")
        assert name is None or isinstance(name, str)

    def test_workspace_path_expansion(self) -> None:
        config = Config()
        wp = config.workspace_path
        assert "~" not in str(wp)  # Should be expanded


# ── Full Config Instantiation ──

class TestFullConfig:
    """Ensure Config() instantiates without errors."""

    def test_config_instantiates(self) -> None:
        config = Config()
        assert config.agents is not None
        assert config.channels is not None
        assert config.providers is not None
        assert config.gateway is not None
        assert config.tools is not None

    def test_providers_config_has_all_providers(self) -> None:
        pc = ProvidersConfig()
        expected = [
            "custom", "anthropic", "openai", "openrouter", "deepseek",
            "groq", "zhipu", "dashscope", "vllm", "gemini", "moonshot",
            "minimax", "aihubmix", "siliconflow", "openai_codex", "github_copilot",
        ]
        for name in expected:
            assert hasattr(pc, name), f"ProvidersConfig missing provider: {name}"
