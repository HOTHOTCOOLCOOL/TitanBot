"""LiteLLM provider implementation for multi-provider support."""

import json
import json_repair
import os
from typing import Any

import litellm
from litellm import acompletion

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest, StreamChunk
from nanobot.providers.registry import find_by_model, find_gateway


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.
    
    Supports OpenRouter, Anthropic, OpenAI, Gemini, MiniMax, and many other providers through
    a unified interface.  Provider-specific logic is driven by the registry
    (see providers/registry.py) — no if-elif chains needed here.
    """
    
    def __init__(
        self, 
        api_key: str | None = None, 
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        
        # Detect gateway / local deployment.
        # provider_name (from config key) is the primary signal;
        # api_key / api_base are fallback for auto-detection.
        self._gateway = find_gateway(provider_name, api_key, api_base)
        
        # Configure environment variables
        if api_key:
            self._setup_env(api_key, api_base, default_model)
        
        if api_base:
            litellm.api_base = api_base
        
        # Disable LiteLLM logging noise
        litellm.suppress_debug_info = True
        # Drop unsupported parameters for providers (e.g., gpt-5 rejects some params)
        litellm.drop_params = True
    
    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """Set environment variables based on detected provider."""
        spec = self._gateway or find_by_model(model)
        if not spec:
            return
        if not spec.env_key:
            # OAuth/provider-only specs (for example: openai_codex)
            return

        # Gateway/local overrides existing env; standard provider doesn't
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

        # Resolve env_extras placeholders:
        #   {api_key}  → user's API key
        #   {api_base} → user's api_base, falling back to spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)
    
    def _resolve_model(self, model: str) -> str:
        """Resolve model name by applying provider/gateway prefixes."""
        if self._gateway:
            # Gateway mode: apply gateway prefix, skip provider-specific prefixes
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model
        
        # Standard mode: auto-prefix for known providers
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"
        
        return model
    
    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """Apply model-specific parameter overrides from the registry."""
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return
    
    # Maximum number of retries for transient errors
    _MAX_RETRIES = 2
    _RETRY_BASE_DELAY = 1.0  # seconds

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Determine if an error is transient and worth retrying.

        Retries: timeouts, connection errors, 5xx server errors.
        Does NOT retry: 4xx (auth/bad request), parsing errors.
        """
        import httpx

        err_str = str(error).lower()
        # Timeout / connection errors
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True
        if isinstance(error, httpx.TimeoutException):
            return True
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500:
            return True
        # LiteLLM wraps HTTP errors with status in the message
        if "timeout" in err_str or "timed out" in err_str:
            return True
        if "connection" in err_str and "refused" in err_str:
            return True
        if any(f"{code}" in err_str for code in (500, 502, 503, 504, 529)):
            return True
        return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        model = self._resolve_model(model or self.default_model)
        
        # If this is different from the default model (e.g. dynamic VLM route), 
        # ensure its provider API key is loaded into the environment
        if model != self.default_model:
            # I1: Use process-level singleton instead of new Config()
            from nanobot.config.loader import get_config
            config = get_config()
            vlm_provider_config = config.get_provider(model)
            if vlm_provider_config and vlm_provider_config.api_key:
                from nanobot.providers.registry import find_by_model
                spec = find_by_model(model)
                if spec and spec.env_key:
                    # R14: Direct assignment — VLM route must override main provider's key
                    os.environ[spec.env_key] = vlm_provider_config.api_key
                    if vlm_provider_config.api_base:
                        effective_base = vlm_provider_config.api_base
                        for env_name, env_val in spec.env_extras:
                            resolved = env_val.replace("{api_key}", vlm_provider_config.api_key)
                            resolved = resolved.replace("{api_base}", effective_base)
                            os.environ.setdefault(env_name, resolved)
        
        # Clamp max_tokens to at least 1 — negative or zero values cause
        # LiteLLM to reject the request with "max_tokens must be at least 1".
        max_tokens = max(1, max_tokens)
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Apply model-specific overrides (e.g. kimi-k2.5 temperature)
        self._apply_model_overrides(model, kwargs)
        
        # Pass api_key directly — more reliable than env vars alone
        if self.api_key:
            kwargs["api_key"] = self.api_key
        
        # Pass api_base for custom endpoints
        if self.api_base:
            kwargs["api_base"] = self.api_base
        
        # Pass extra headers (e.g. APP-Code for AiHubMix)
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        import asyncio
        import time as _time
        last_error: Exception | None = None
        for attempt in range(1 + self._MAX_RETRIES):
            _start = _time.monotonic()
            try:
                response = await acompletion(**kwargs)
                _elapsed = _time.monotonic() - _start
                parsed = self._parse_response(response)
                _tokens = parsed.usage.get("total_tokens", "?") if parsed.usage else "?"
                if attempt > 0:
                    logger.info(f"LLM call succeeded on retry {attempt}: model={model}, duration={_elapsed:.1f}s, tokens={_tokens}")
                else:
                    logger.info(f"LLM call: model={model}, duration={_elapsed:.1f}s, tokens={_tokens}")
                return parsed
            except Exception as e:
                _elapsed = _time.monotonic() - _start
                last_error = e
                if attempt < self._MAX_RETRIES and self._is_retryable(e):
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"LLM call failed (attempt {attempt+1}/{1+self._MAX_RETRIES}): "
                        f"model={model}, duration={_elapsed:.1f}s, error={e}. "
                        f"Retrying in {delay:.0f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                # Non-retryable or max retries exhausted
                logger.error(f"LLM call failed: model={model}, duration={_elapsed:.1f}s, error={e}")
                return LLMResponse(
                    content=f"Error calling LLM: {str(e)}",
                    finish_reason="error",
                )
        # Should not reach here, but just in case
        return LLMResponse(
            content=f"Error calling LLM: {str(last_error)}",
            finish_reason="error",
        )
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # Parse arguments from JSON string if needed
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json_repair.loads(args)
                
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        reasoning_content = getattr(message, "reasoning_content", None)
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model

    # ── Phase 21E: Streaming response delivery ──────────────────

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """Stream a chat completion, yielding StreamChunk objects.

        Uses LiteLLM's ``acompletion(stream=True)`` under the hood.
        On error, falls back to non-streaming ``chat()`` for robustness.
        """
        from collections.abc import AsyncIterator
        import time as _time

        model = self._resolve_model(model or self.default_model)
        max_tokens = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        self._apply_model_overrides(model, kwargs)

        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            _start = _time.monotonic()
            response = await acompletion(**kwargs)

            # Accumulate tool-call deltas across chunks
            _tool_call_acc: dict[int, dict] = {}        # index → {id, name, args_str}
            _reasoning_parts: list[str] = []
            _content_parts: list[str] = []
            _usage: dict[str, int] = {}

            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # --- text delta ---
                text = getattr(delta, "content", None) or ""

                # --- reasoning delta ---
                reason = getattr(delta, "reasoning_content", None)
                if reason:
                    _reasoning_parts.append(reason)

                # --- tool call deltas ---
                tc_deltas = getattr(delta, "tool_calls", None )
                if tc_deltas:
                    for tcd in tc_deltas:
                        idx = tcd.index if hasattr(tcd, "index") else 0
                        if idx not in _tool_call_acc:
                            _tool_call_acc[idx] = {"id": "", "name": "", "args": ""}
                        if tcd.id:
                            _tool_call_acc[idx]["id"] = tcd.id
                        if hasattr(tcd, "function") and tcd.function:
                            if tcd.function.name:
                                _tool_call_acc[idx]["name"] = tcd.function.name
                            if tcd.function.arguments:
                                _tool_call_acc[idx]["args"] += tcd.function.arguments

                # --- usage (some providers send on last chunk) ---
                if hasattr(chunk, "usage") and chunk.usage:
                    _usage = {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                    }

                finish = chunk.choices[0].finish_reason

                if text:
                    _content_parts.append(text)
                    yield StreamChunk(delta=text, finish_reason=None)

                # On finish, emit final chunk with accumulated metadata
                if finish:
                    parsed_tool_calls = []
                    for _idx in sorted(_tool_call_acc.keys()):
                        acc = _tool_call_acc[_idx]
                        args = acc["args"]
                        try:
                            args_dict = json_repair.loads(args) if args else {}
                        except Exception:
                            args_dict = {}
                        parsed_tool_calls.append(ToolCallRequest(
                            id=acc["id"],
                            name=acc["name"],
                            arguments=args_dict,
                        ))

                    _elapsed = _time.monotonic() - _start
                    _total = _usage.get("total_tokens", "?")
                    logger.info(f"LLM stream: model={model}, duration={_elapsed:.1f}s, tokens={_total}")

                    yield StreamChunk(
                        delta="",
                        finish_reason=finish,
                        usage=_usage,
                        tool_calls=parsed_tool_calls,
                        reasoning_content="".join(_reasoning_parts) if _reasoning_parts else None,
                    )
                    return

        except Exception as e:
            logger.warning(f"Streaming failed, falling back to non-streaming: {e}")
            # Fallback: use the base-class default (non-streaming chat)
            async for chunk in super().stream_chat(
                messages=messages, tools=tools, model=model,
                max_tokens=max_tokens, temperature=temperature,
            ):
                yield chunk
