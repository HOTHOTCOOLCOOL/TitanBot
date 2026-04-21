"""
BFF Gateway - Main Server (bff_server.py)

A FastAPI-based proxy gateway that:
  1. Accepts OpenAI-compatible requests from Nanobot clients (using dummy tokens)
  2. Authenticates the dummy token against user_tokens.json
  3. Rate-limits per user (token bucket, BFF_RATE_LIMIT_RPM per minute)
  4. Injects the real MASTER_API_KEY and routes to the actual upstream provider
  5. Streams the response back transparently via Server-Sent Events (SSE)

Core design principle:
  - The MASTER_API_KEY NEVER leaves this process or appears in any log
  - Client only ever sees/uses their own dummy token

Usage:
    cd bff/
    pip install fastapi uvicorn litellm python-dotenv loguru
    python bff_server.py

Nanobot config.json (client side):
    {
      "providers": {
        "custom": {
          "api_key": "user_zhangsan_tok_abc",
          "api_base": "http://127.0.0.1:8099/v1"
        }
      },
      "agents": { "defaults": { "model": "gpt-4o" } }
    }
"""

import json
import time
from typing import AsyncGenerator

import litellm
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from auth import MockAuthenticator
from config import BFFConfig, load_config
from rate_limiter import RateLimiter

# ── Silence LiteLLM verbose output ──────────────────────────────────────────
litellm.suppress_debug_info = True
litellm.drop_params = False  # Set to False so it doesn't strip tool_calls for custom models

# ── App bootstrap ─────────────────────────────────────────────────────────────
app = FastAPI(title="Nanobot BFF Gateway", version="0.1.0")
cfg: BFFConfig = load_config()
auth = MockAuthenticator(tokens_path=cfg.tokens_path)
limiter = RateLimiter(rpm=cfg.rate_limit_rpm)


# ── Error helpers ─────────────────────────────────────────────────────────────

def openai_error(message: str, error_type: str, status_code: int) -> JSONResponse:
    """Return an OpenAI-compatible error JSON so LiteLLM on the client parses it cleanly."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "code": status_code}},
    )


# ── Model resolution ──────────────────────────────────────────────────────────

def resolve_model(client_model: str) -> tuple[str, str, str, str | None]:
    """
    Map the client-facing model name to upstream credentials.

    Returns: (upstream_model, api_key, api_base, api_version_or_None)
    """
    # Check model_map first
    upstream_model = cfg.model_map.get(client_model, client_model)

    # 🟢 Smart Routing Bypass for LMStudio / Local models
    # If the model contains "qwen" or "deepseek", automatically route to LMStudio
    if "qwen" in upstream_model.lower() or "deepseek" in upstream_model.lower():
        # Using litellm's generic "openai/" prefix ensures it natively proxies unmodified
        if not upstream_model.startswith("openai/"):
            upstream_model = f"openai/{upstream_model}"
        # Hardcode fallback back to local LMStudio server
        return upstream_model, "empty", "http://10.18.34.60:5888/v1", None

    if cfg.upstream_provider == "azure":
        # Ensure model has azure/ prefix for LiteLLM
        if not upstream_model.startswith("azure/"):
            upstream_model = f"azure/{upstream_model}"
        return upstream_model, cfg.azure_api_key, cfg.azure_api_base, cfg.azure_api_version

    # Generic provider (anthropic, openai, deepseek, etc.)
    return upstream_model, cfg.generic_api_key, cfg.generic_api_base, None


# ── Request gating ─────────────────────────────────────────────────────────

async def gate_request(request: Request) -> tuple[str, dict] | JSONResponse:
    """
    Authenticate and rate-limit the incoming request.

    Returns (user_id, body_dict) on success, or a JSONResponse error.
    """
    # 1. Extract and validate token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return openai_error("Missing Authorization header.", "authentication_error", 401)

    user_id = auth.authenticate(auth_header)
    if not user_id:
        return openai_error(
            "Invalid or unrecognized BFF authentication token. "
            "Contact your administrator to obtain a valid token.",
            "authentication_error",
            401,
        )

    # 2. Rate limit
    allowed = await limiter.check(user_id)
    if not allowed:
        return openai_error(
            f"Rate limit exceeded. Maximum {cfg.rate_limit_rpm} requests per minute per user.",
            "rate_limit_error",
            429,
        )

    # 3. Parse body
    try:
        body = await request.json()
    except Exception:
        return openai_error("Invalid JSON request body.", "invalid_request_error", 400)

    return user_id, body


# ── SSE stream generator ───────────────────────────────────────────────────────

async def _stream_litellm(kwargs: dict, user_id: str) -> AsyncGenerator[bytes, None]:
    """
    Async generator that wraps litellm.acompletion (stream=True)
    and yields raw SSE bytes for FastAPI StreamingResponse.
    """
    start = time.monotonic()
    total_tokens = 0

    try:
        response = await litellm.acompletion(**kwargs, stream=True)

        async for chunk in response:
            # Relay usage from final chunk if present
            if hasattr(chunk, "usage") and chunk.usage:
                total_tokens = getattr(chunk.usage, "total_tokens", 0) or 0

            chunk_json = chunk.model_dump_json(exclude_none=True)
            yield f"data: {chunk_json}\n\n".encode()

        yield b"data: [DONE]\n\n"

    except Exception as e:
        elapsed = time.monotonic() - start
        # ⚠️  Do NOT log the api_key or full kwargs — only safe info
        logger.error(f"[Stream] user={user_id} upstream error after {elapsed:.1f}s: {type(e).__name__}: {e}")
        # Emit an SSE error event so client knows the stream terminated abnormally
        error_payload = json.dumps({
            "error": {"message": str(e), "type": "upstream_error", "code": 500}
        })
        yield f"data: {error_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"
    finally:
        elapsed = time.monotonic() - start
        logger.info(
            f"[Stream] user={user_id} model={kwargs.get('model', '?')} "
            f"tokens={total_tokens or '?'} duration={elapsed:.1f}s"
        )


async def _stream_text_completion(kwargs: dict, user_id: str) -> AsyncGenerator[bytes, None]:
    """
    Async generator that wraps litellm.atext_completion (stream=True)
    and yields raw SSE bytes for FastAPI StreamingResponse.
    """
    start = time.monotonic()
    total_tokens = 0

    try:
        response = await litellm.atext_completion(**kwargs, stream=True)

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                total_tokens = getattr(chunk.usage, "total_tokens", 0) or 0

            chunk_json = chunk.model_dump_json(exclude_none=True)
            yield f"data: {chunk_json}\n\n".encode()

        yield b"data: [DONE]\n\n"

    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(f"[Stream Completions] user={user_id} upstream error after {elapsed:.1f}s: {type(e).__name__}: {e}")
        error_payload = json.dumps({
            "error": {"message": str(e), "type": "upstream_error", "code": 500}
        })
        yield f"data: {error_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"
    finally:
        elapsed = time.monotonic() - start
        logger.info(
            f"[Stream Completions] user={user_id} model={kwargs.get('model', '?')} "
            f"tokens={total_tokens or '?'} duration={elapsed:.1f}s"
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "nanobot-bff-gateway", "version": "0.1.0"}


@app.get("/v1/models")
async def list_models() -> dict:
    """
    Return a minimal OpenAI-compatible models list.
    Required so LiteLLM's connectivity check on custom api_base succeeds.
    """
    model_ids = list(cfg.model_map.keys()) or ["gpt-4o"]
    return {
        "object": "list",
        "data": [
            {"id": mid, "object": "model", "owned_by": "company-bff"}
            for mid in model_ids
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    """
    Main proxy endpoint.

    Accepts OpenAI-format requests from Nanobot, validates the dummy token,
    then forwards to the upstream LLM via LiteLLM (with the real Master Key injected).
    """
    # ── Gate: auth + rate limit ──────────────────────────────────────────────
    result = await gate_request(request)
    if isinstance(result, JSONResponse):
        return result
    user_id, body = result

    # ── Resolve upstream ─────────────────────────────────────────────────────
    client_model: str = body.get("model", "gpt-4o")
    upstream_model, api_key, api_base, api_version = resolve_model(client_model)

    if not api_key:
        logger.error("[Config] Master API key is not configured. Set BFF_AZURE_API_KEY in .env.")
        return openai_error(
            "BFF gateway is not configured with an upstream API key. Contact administrator.",
            "server_error",
            500,
        )

    # ── Build litellm kwargs ──────────────────────────────────────────────────
    kwargs: dict = {
        "model": upstream_model,
        "messages": body.get("messages", []),
        "api_key": api_key,           # ← Real Master Key injected here, NEVER logged
        "timeout": cfg.upstream_timeout,
    }

    if api_base:
        kwargs["api_base"] = api_base
    if api_version:
        kwargs["api_version"] = api_version

    # Forward optional params from client
    for param in ("max_tokens", "temperature", "top_p", "tools", "tool_choice", "stream"):
        if param in body:
            kwargs[param] = body[param]
            
    # 🟢 Reasoning Exception Bypass
    # LiteLLM throws 'UnsupportedParamsError' if temperature != 1 is passed to gpt-5/o1
    if "gpt-5" in upstream_model or "o1" in upstream_model:
        kwargs.pop("temperature", None)
        kwargs.pop("top_p", None)

    is_streaming = bool(body.get("stream", False))

    logger.info(
        f"[Request] user={user_id} client_model={client_model} "
        f"upstream={upstream_model} stream={is_streaming}"
    )

    # ── Streaming path ────────────────────────────────────────────────────────
    if is_streaming:
        return StreamingResponse(
            _stream_litellm(kwargs, user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Non-streaming path ────────────────────────────────────────────────────
    start = time.monotonic()
    try:
        response = await litellm.acompletion(**kwargs)
        elapsed = time.monotonic() - start
        total_tokens = getattr(getattr(response, "usage", None), "total_tokens", "?")
        logger.info(
            f"[Response] user={user_id} model={upstream_model} "
            f"tokens={total_tokens} duration={elapsed:.1f}s"
        )
        return JSONResponse(content=response.model_dump(exclude_none=True))
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(
            f"[Response] user={user_id} upstream error after {elapsed:.1f}s: "
            f"{type(e).__name__}: {e}"
        )
        return openai_error(str(e), "upstream_error", 502)


@app.post("/v1/completions")
async def text_completions(request: Request) -> Response:
    """
    Legacy proxy endpoint for Completions API.
    """
    result = await gate_request(request)
    if isinstance(result, JSONResponse):
        return result
    user_id, body = result

    client_model: str = body.get("model", "gpt-4o")
    upstream_model, api_key, api_base, api_version = resolve_model(client_model)

    if not api_key:
        return openai_error(
            "BFF gateway is not configured with an upstream API key.", "server_error", 500
        )

    kwargs: dict = {
        "model": upstream_model,
        "prompt": body.get("prompt", ""),
        "api_key": api_key,
        "timeout": cfg.upstream_timeout,
    }

    if api_base:
        kwargs["api_base"] = api_base
    if api_version:
        kwargs["api_version"] = api_version

    for param in ("max_tokens", "temperature", "top_p", "stream", "stop", "seed"):
        if param in body:
            kwargs[param] = body[param]
            
    if "gpt-5" in upstream_model or "o1" in upstream_model:
        kwargs.pop("temperature", None)
        kwargs.pop("top_p", None)

    is_streaming = bool(body.get("stream", False))
    logger.info(f"[Request Completions] user={user_id} upstream={upstream_model} stream={is_streaming}")

    if is_streaming:
        return StreamingResponse(
            _stream_text_completion(kwargs, user_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    start = time.monotonic()
    try:
        response = await litellm.atext_completion(**kwargs)
        elapsed = time.monotonic() - start
        total_tokens = getattr(getattr(response, "usage", None), "total_tokens", "?")
        logger.info(f"[Response Completions] user={user_id} tokens={total_tokens} duration={elapsed:.1f}s")
        return JSONResponse(content=response.model_dump(exclude_none=True))
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(f"[Response Completions] user={user_id} upstream error: {e}")
        return openai_error(str(e), "upstream_error", 502)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import socket

    # Port conflict detection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((cfg.host, cfg.port)) == 0:
            logger.error(
                f"Port {cfg.port} is already in use. "
                f"Set BFF_PORT in .env to a different value."
            )
            raise SystemExit(1)

    logger.info(f"🚀 Nanobot BFF Gateway starting on http://{cfg.host}:{cfg.port}")
    logger.info(f"   Upstream provider : {cfg.upstream_provider}")
    logger.info(f"   Rate limit        : {cfg.rate_limit_rpm} RPM per user")
    logger.info(f"   Auth tokens file  : {cfg.tokens_path}")
    logger.info(f"   Model map         : {cfg.model_map or '(passthrough)'}")

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
