"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WhatsAppConfig(Base):
    """WhatsApp channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""  # Shared token for bridge auth (optional, recommended)
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"


class FeishuConfig(Base):
    """Feishu/Lark channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids


class DingTalkConfig(Base):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: str = ""  # AppSecret
    allow_from: list[str] = Field(default_factory=list)  # Allowed staff_ids


class DiscordConfig(Base):
    """Discord channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class EmailConfig(Base):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    # Behavior
    auto_reply_enabled: bool = True  # If false, inbound email is read but no automatic reply is sent
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender email addresses


class MochatMentionConfig(Base):
    """Mochat mention behavior configuration."""

    require_in_groups: bool = False


class MochatGroupRule(Base):
    """Mochat per-group mention requirement."""

    require_mention: bool = False


class MochatConfig(Base):
    """Mochat channel configuration."""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0  # 0 means unlimited retries
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000


class SlackDMConfig(Base):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs


class SlackConfig(Base):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: str = ""  # xoxb-...
    app_token: str = ""  # xapp-...
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(Base):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""  # 机器人 ID (AppID) from q.qq.com
    secret: str = ""  # 机器人密钥 (AppSecret) from q.qq.com
    allow_from: list[str] = Field(default_factory=list)  # Allowed user openids (empty = public access)


class WecomConfig(Base):
    """WeCom (Enterprise WeChat / 企业微信) AI Bot channel configuration."""

    enabled: bool = False
    bot_id: str = ""      # Bot ID from WeCom AI Bot platform
    secret: str = ""      # App Secret
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs (empty = all)
    welcome_message: str = ""


class WeixinConfig(Base):
    """Personal WeChat (微信) channel configuration via HTTP long-poll."""

    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)  # Allowed WeChat user IDs
    base_url: str = "https://ilinkai.weixin.qq.com"
    cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    route_tag: str | int | None = None
    token: str = ""        # Bot token (obtained via QR code login or set manually)
    state_dir: str = ""    # State persistence dir (default: workspace/weixin/)
    poll_timeout: int = 35  # Long-poll timeout in seconds


class ChannelsConfig(Base):
    """Configuration for chat channels.

    Active channels (China-first set):
        wecom   — 企业微信 (WeCom Enterprise WeChat) via WebSocket SDK
        weixin  — 个人微信 (Personal WeChat) via HTTP long-poll
        feishu  — 飞书/Lark
        dingtalk — 钉钉
        qq      — QQ 频道机器人
        whatsapp — WhatsApp (Bridge)
        email   — IMAP/SMTP

    Removed (low China adoption):
        discord, slack, telegram, mochat
        (files kept on disk for potential future re-enable via config)
    """

    # ── Active channels ───────────────────────────────────────────────
    wecom: WecomConfig = Field(default_factory=WecomConfig)
    weixin: WeixinConfig = Field(default_factory=WeixinConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)

    # ── Legacy / inactive (kept for config backward compat) ───────────
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20
    memory_window: int = 50
    session_expiry_hours: int = 24  # Sessions older than this many hours will be expired
    language: str = "en"  # User-facing language: "en" or "zh"
    embedding_model: str = ""  # Local path to sentence-transformers model. Empty = default (BAAI/bge-m3).


class VLMConfig(Base):
    """Vision Language Model configuration for Multi-Modal tasks."""

    enabled: bool = True
    model: str | None = None  # E.g. "dashscope/qwen-vl-max". If none, falls back to default agent model.


class VisionConfig(Base):
    """Vision system configuration for RPA screen perception."""

    ocr_enabled: bool = True           # Enable PaddleOCR fallback when UIAutomation finds too few elements
    ocr_min_confidence: float = 0.7    # Minimum OCR confidence threshold (0-1)
    uia_fallback_threshold: int = 3    # Trigger OCR when UIAutomation finds fewer elements than this
    yolo_enabled: bool = False         # Enable YOLO UI element detection (requires: pip install ultralytics)
    yolo_model: str = "gpa-gui-detector"  # Model name or absolute path to a .pt file
    yolo_confidence: float = 0.3       # Minimum YOLO detection confidence (0-1)


class MemoryFeaturesConfig(Base):
    """Per-feature on/off switches for memory subsystems (Phase 21A D1)."""

    reflection_enabled: bool = True       # Metacognitive Reflection Memory (20D)
    knowledge_graph_enabled: bool = True  # Lightweight Entity-Relation Graph (20E)
    visual_memory_enabled: bool = True    # Visual Memory Text Persistence (20G)
    experience_enabled: bool = True       # Experience Bank tactical hints (Phase 12)


class StreamingConfig(Base):
    """Streaming response delivery configuration (Phase 21E)."""

    enabled: bool = True  # Forward LLM tokens in real-time via WebSocket


class VLMFeedbackConfig(Base):
    """Vision-Language feedback loop for self-correcting RPA (Phase 21E)."""

    enabled: bool = False                # Off by default — requires VLM config
    max_retries: int = 3                 # Max verification+retry attempts per action
    verification_delay: float = 1.0      # Seconds to wait before verification capture
    auto_verify_actions: list[str] = Field(
        default_factory=lambda: ["click", "double_click", "type"]
    )


class BrowserConfig(Base):
    """Headless browser automation configuration (Phase 26)."""

    enabled: bool = True                # Master switch
    headless: bool = False              # Headless by default; use browser(action='ensure_visible') for RPA
    executable_path: str = ""           # Path to Chrome/Chromium binary. Empty = Playwright default.
    default_timeout_ms: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080
    max_pages: int = 5                  # Concurrent page limit
    session_ttl_hours: int = 24         # Cookie/session expiry
    trusted_domains: list[str] = Field(default_factory=list)  # Pre-trusted domains (supports wildcards)
    block_internal_ips: bool = True     # SSRF protection


class SandboxConfig(Base):
    """Execution sandbox configuration (Phase 28B)."""

    python_timeout_seconds: int = Field(default=300, description="Max execution time for Python scripts securely evaluated.")
    shell_timeout_seconds: int = Field(default=60, description="Max execution time for terminal shell commands.")
    tool_timeout_seconds: int = Field(default=120, description="Default timeout for all tool executions (BP-3).")
    allow_network: bool = Field(default=False, description="Whether to allow network requests during sandboxed execution.")
    restrict_workspace: bool = Field(default=True, description="Constrain file system IO to the defined workspace path.")
    capability_overrides: dict[str, int] = Field(default_factory=dict, description="Phase 45C: Bitmask mapping for high-risk Sandbox Tool Tags.")


class VerificationConfig(Base):
    """Phase 31→32: Verification Layer configuration.

    Funnel-shaped verification pipeline (L0→L1→L3).
    L2 (small-model introspection) removed in Phase 32.
    Each layer can be independently disabled as base models improve.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True,
        extra="ignore",  # Gracefully ignore old l2Enabled/l2Model fields in existing configs
    )

    l0_enabled: bool = True         # Experience + reflection context enrichment
    l1_enabled: bool = True         # Rigid rule interception (pre-execution)
    l3_enabled: bool = True         # Post-reflection & knowledge extraction
    l3_success_pattern_min_tools: int = 3  # Min tools used to trigger success pattern extraction

    # Phase 35v2: Configurable path deny patterns (Glob syntax via fnmatch).
    # These supplement the hardcoded _SENSITIVE_PATHS in verification.py.
    # Users can add project-specific deny rules in config.json.
    # Example: ["*.env", "**/.git/*", "/secrets/*"]
    path_deny_patterns: list[str] = Field(default_factory=list)

    # Phase 37: Execution Trace Archive — enriched post-mortem extraction
    # on circuit breaker / loop detection.  When enabled, failed complex
    # tasks get LLM-analyzed post-mortems stored in Experience Bank,
    # plus optional raw debug traces saved to memory/traces/.
    trace_archive_enabled: bool = True


class ContextConfig(Base):
    """Context and truncation configuration (Phase 40A)."""

    max_tool_result_chars: int = 16_000
    context_window_tokens: int | None = None  # None = auto-infer
    snip_safety_buffer: int = 1024


class ReliabilityConfig(Base):
    """Phase 40B: Reliability enhancement configuration."""

    checkpoint_enabled: bool = True       # Write checkpoint before tool execution for crash recovery
    memory_backup_count: int = 5          # Max rolling MEMORY.md .bak files (0 = disabled)


class ExperimentalConfig(Base):
    """Phase 41: Experimental feature flags for grey deployment."""

    middleware_enabled: bool = True  # Enable onion middleware pipeline (Phase 41)
    xml_fallback_enabled: bool = True   # Settings to control fallback xml-tool parsing


class FastModelConfig(Base):
    """Fast model configuration for low-latency tasks (e.g. conversational routing)."""

    enabled: bool = False
    model: str | None = None


class CoordinatorConfig(Base):
    """Phase 38: Coordinator Mode Configuration."""

    enabled: bool = False
    max_workers: int = 4
    worker_timeout: int = 300
    heartbeat_interval: int = 10
    sandbox_root: str = "workspace/workers"
    ipc_mode: str = "http"


class ValidatorConfig(Base):
    """Phase 56: Pre-flight Skill Verifier configuration."""

    enabled: bool = True
    timeout_ms: int = Field(default=200, ge=50, le=5000)


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    context: ContextConfig = Field(default_factory=ContextConfig)
    workflow_models: dict[str, str] = Field(default_factory=dict)  # Phase 29: Per-Workflow Model Routing (e.g. {"key_extraction": "gpt-4o-mini"})
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    memory_features: MemoryFeaturesConfig = Field(default_factory=MemoryFeaturesConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    vlm_feedback: VLMFeedbackConfig = Field(default_factory=VLMFeedbackConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    reliability: ReliabilityConfig = Field(default_factory=ReliabilityConfig)
    experimental: ExperimentalConfig = Field(default_factory=ExperimentalConfig)
    fast_model: FastModelConfig = Field(default_factory=FastModelConfig)
    coordinator: CoordinatorConfig = Field(default_factory=CoordinatorConfig)
    validator: ValidatorConfig = Field(default_factory=ValidatorConfig)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)  # 阿里云通义千问
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    volcengine: ProviderConfig = Field(default_factory=ProviderConfig)  # 火山引擎 (Doubao)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)  # SiliconFlow (硅基流动) API gateway
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig)  # OpenAI Codex (OAuth)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig)  # Github Copilot (OAuth)


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "127.0.0.1"
    port: int = 18790
    token: str = ""  # Dashboard auth token. Empty = auto-generate at startup.


class WebSearchConfig(Base):
    """Web search tool configuration."""

    api_key: str = ""  # Brave Search API key
    max_results: int = 5


class WebToolsConfig(Base):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP: streamable HTTP endpoint URL


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(Base):
    """Root configuration for nanobot."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    master_identities: dict[str, str] = Field(default_factory=dict)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(self, model: str | None = None) -> tuple["ProviderConfig | None", str | None]:
        from nanobot.providers.registry import PROVIDERS

        model_str = (model or self.agents.defaults.model).lower()
        
        # If the model explicitly specifies a provider prefix (e.g. "dashscope/qwen-vl-max")
        # we should respect that over the custom fallback.
        if "/" in model_str:
            prefix = model_str.split("/")[0]
            for spec in PROVIDERS:
                if prefix == spec.name or prefix == spec.litellm_prefix:
                    p = getattr(self.providers, spec.name, None)
                    if p and (spec.is_oauth or getattr(p, "api_key", None)):
                        return p, spec.name

        # Custom provider takes priority when explicitly configured (has api_base).
        # This ensures local endpoints (e.g. OpenCode at 127.0.0.1:4096) are used
        # even when the model name contains a known provider keyword like "minimax".
        if self.providers.custom.api_base:
            return self.providers.custom, "custom"

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(kw in model_str for kw in spec.keywords):
                if spec.is_oauth or getattr(p, "api_key", None):
                    return p, spec.name

        # Fallback: gateways first, then others (follows registry order)
        # OAuth providers are NOT valid fallbacks — they require explicit model selection
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            p = getattr(self.providers, spec.name, None)
            if p and getattr(p, "api_key", None):
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model. Applies default URLs for known gateways."""
        from nanobot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        # Only gateways get a default api_base here. Standard providers
        # (like Moonshot) set their base URL via env vars in _setup_env
        # to avoid polluting the global litellm.api_base.
        if name:
            spec = find_by_name(name)
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(
        extra="ignore",
    )
