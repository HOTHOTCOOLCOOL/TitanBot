"""Web Dashboard for Nanobot.

Provides a FastAPI based interface for monitoring Agent status, managing knowledge
and memory, and viewing logs in real-time.

Phase 18A: Added Bearer Token authentication for all endpoints (except /api/status).
"""

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from nanobot.config.loader import load_config
from nanobot.bus.queue import MessageBus
from nanobot.bus.events import OutboundMessage, InboundMessage

try:
    from nanobot.utils.metrics import get_metrics
except ImportError:
    get_metrics = lambda: {"status": "Metrics tracking unavailable"}


app = FastAPI(title="Nanobot Command Center")

# Basic local file serving
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global dependencies
_bus: MessageBus | None = None
_workspace: Path | None = None
_active_websockets: list[WebSocket] = []
_dashboard_token: str | None = None


def init_dashboard(bus: MessageBus, workspace: Path, token: str = ""):
    """Initialize global references for the dashboard.
    
    Token priority: explicit token arg > env var NANOBOT_DASHBOARD_TOKEN > auto-generate.
    """
    global _bus, _workspace, _dashboard_token
    _bus = bus
    _workspace = workspace

    resolved = token or os.environ.get("NANOBOT_DASHBOARD_TOKEN", "")
    if not resolved:
        resolved = secrets.token_hex(16)
        logger.info(f"Dashboard auth token (auto-generated): {resolved}")
    _dashboard_token = resolved


# ====================================================================
# Rate Limiting
# ====================================================================
import time

class RateLimiter:
    """Token bucket rate limiter for the dashboard API."""
    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            
            # Refill tokens
            new_tokens = int(elapsed * self.refill_rate)
            if new_tokens > 0:
                self.tokens = min(self.capacity, self.tokens + new_tokens)
                self.last_refill = now
                
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

_rate_limiter = RateLimiter(capacity=50, refill_rate=5.0)

async def check_rate_limit():
    """FastAPI dependency for rate limiting."""
    if not await _rate_limiter.consume(1):
        raise HTTPException(status_code=429, detail="Too Many Requests")



# ====================================================================
# Authentication
# ====================================================================

async def verify_token(request: Request) -> None:
    """FastAPI dependency: verify Bearer token on protected endpoints."""
    if not _dashboard_token:
        return  # Auth disabled (should not happen in production)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    if auth[7:] != _dashboard_token:
        raise HTTPException(status_code=401, detail="Invalid token")


# ====================================================================
# Routes
# ====================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main dashboard interface."""
    return templates.TemplateResponse("index.html", {"request": request})

# S3: WebSocket per-connection constants
_WS_MAX_MESSAGE_SIZE = 10_240      # 10 KB max per message
_WS_RATE_LIMIT_WINDOW = 60         # seconds
_WS_RATE_LIMIT_MAX_MSGS = 30       # max messages per window

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time log tailing and bus monitoring.
    
    Requires ?token=<dashboard_token> query parameter.
    S3: Enforces per-message size limit and per-connection rate limit.
    """
    # Verify token before accepting
    if _dashboard_token:
        ws_token = websocket.query_params.get("token", "")
        if ws_token != _dashboard_token:
            await websocket.close(code=1008)  # Policy Violation
            return

    await websocket.accept()
    _active_websockets.append(websocket)

    # S3: per-connection rate limiting state
    _ws_msg_timestamps: list[float] = []

    try:
        while True:
            data = await websocket.receive_text()

            # S3: reject oversized messages
            if len(data) > _WS_MAX_MESSAGE_SIZE:
                await websocket.send_text('{"error":"Message too large (max 10KB)"}')
                continue

            # S3: per-connection rate limit (sliding window)
            now = time.time()
            _ws_msg_timestamps = [t for t in _ws_msg_timestamps if now - t < _WS_RATE_LIMIT_WINDOW]
            if len(_ws_msg_timestamps) >= _WS_RATE_LIMIT_MAX_MSGS:
                await websocket.send_text('{"error":"Rate limit exceeded (max 30 msgs/min)"}')
                continue
            _ws_msg_timestamps.append(now)

            if _bus and data:
                try:
                    payload = json.loads(data)
                    msg_text = payload.get("message")
                    if msg_text:
                        inbound = InboundMessage(
                            channel="dashboard",
                            sender_id="web",
                            chat_id="direct",
                            content=msg_text
                        )
                        await _bus.publish_inbound(inbound)
                except Exception:
                    pass
    except WebSocketDisconnect:
        if websocket in _active_websockets:
            _active_websockets.remove(websocket)

async def broadcast_ws_message(msg_type: str, data: Any):
    """Broadcast an event to all connected dashboard websockets."""
    if not _active_websockets:
        return
        
    payload = json.dumps({"type": msg_type, "data": data}, ensure_ascii=False)
    for ws in _active_websockets.copy():  # Phase 18A: iterate over copy for safety
        try:
            await ws.send_text(payload)
        except Exception:
            pass

# ====================================================================
# API Endpoints for Knowledge & Memory
# ====================================================================

@app.get("/api/status", dependencies=[Depends(check_rate_limit)])
async def get_status():
    """Get high-level agent status. No auth required (health check)."""
    return {"status": "online"}

@app.get("/api/memory", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def get_memory():
    """Read MEMORY.md."""
    if not _workspace:
        return {"content": "Workspace not configured."}
    
    mem_file = _workspace / "memory" / "MEMORY.md"
    content = mem_file.read_text(encoding="utf-8") if mem_file.exists() else ""
    return {"content": content}

@app.post("/api/memory", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def update_memory(request: Request):
    """Update MEMORY.md."""
    if not _workspace:
        return {"success": False, "error": "Workspace not configured."}
    
    data = await request.json()
    content = data.get("content", "")
    
    mem_file = _workspace / "memory" / "MEMORY.md"
    mem_file.write_text(content, encoding="utf-8")
    return {"success": True}

@app.get("/api/tasks", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def get_tasks():
    """Read tasks.json."""
    if not _workspace:
        return {"tasks": {}}
        
    tasks_file = _workspace / "memory" / "tasks.json"
    if tasks_file.exists():
        try:
            return {"tasks": json.loads(tasks_file.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return {"tasks": {}}

@app.post("/api/tasks", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def update_tasks(request: Request):
    """Save tasks.json entirely."""
    if not _workspace:
        return {"success": False, "error": "Workspace not configured."}
        
    data = await request.json()
    tasks_dict = data.get("tasks", {})
    
    tasks_file = _workspace / "memory" / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"success": True}

@app.get("/api/preferences", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def get_preferences():
    """Read preferences.json."""
    if not _workspace:
        return {"preferences": {}}
        
    prefs_file = _workspace / "memory" / "preferences.json"
    if prefs_file.exists():
        try:
            return {"preferences": json.loads(prefs_file.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return {"preferences": {}}

@app.get("/api/stats", dependencies=[Depends(verify_token), Depends(check_rate_limit)])
async def get_stats():
    """Get system stats and metrics."""
    return get_metrics()
