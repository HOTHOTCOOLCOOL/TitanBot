# Nanobot BFF Gateway

A lightweight Backend-For-Frontend (BFF) proxy gateway that protects the company's **Master Azure/LLM API Key** from being exposed in Nanobot client installations.

## Architecture Overview

```
Nanobot Client                 BFF Gateway              Azure / Upstream
(dummy token only)             (holds Master Key)
       │                              │                        │
       │── POST /v1/chat/completions ─►│                        │
       │   Bearer: user_tok_abc       │                        │
       │                              │ 1. Validate token      │
       │                              │ 2. Check rate limit    │
       │                              │ 3. Inject Master Key   │
       │                              │── POST (upstream) ────►│
       │◄────── SSE stream ───────────│◄──── SSE stream ───────│
```

**Security guarantee**: The Master API Key never appears in any Nanobot client config file, log, or memory dump.

---

## Quick Start (Local PoC)

### 1. Install dependencies
```bash
cd bff/
pip install fastapi uvicorn litellm python-dotenv loguru
```

### 2. Configure
```bash
copy .env.example .env
# Edit .env — fill in BFF_AZURE_API_KEY, BFF_AZURE_API_BASE, etc.
```

### 3. Add a user token
Edit `user_tokens.json`. Generate a secure token:
```python
import secrets
print(secrets.token_hex(32))
# e.g.: 3a7f9c2b1d8e4f6a0c5b2d9e7f1a3c8b...
```
Then add to `user_tokens.json`:
```json
{
  "3a7f9c2b1d8e4f6a0c5b2d9e7f1a3c8b...": "zhangsan"
}
```

### 4. Start the BFF server
```bash
python bff_server.py
```
Expected output:
```
🚀 Nanobot BFF Gateway starting on http://127.0.0.1:8099
   Upstream provider : azure
   Rate limit        : 60 RPM per user
   Auth tokens file  : ./user_tokens.json
```

### 5. Configure Nanobot client
Edit your Nanobot `config.json`:
```json
{
  "providers": {
    "custom": {
      "api_key": "3a7f9c2b1d8e4f6a0c5b2d9e7f1a3c8b...",
      "api_base": "http://127.0.0.1:8099/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "gpt-4o"
    }
  }
}
```

### 6. Test
```bash
# Health check
curl http://127.0.0.1:8099/health

# List models
curl http://127.0.0.1:8099/v1/models

# Test with invalid token (should return 401)
curl -X POST http://127.0.0.1:8099/v1/chat/completions \
  -H "Authorization: Bearer invalid_token" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]}'
```

---

## File Structure
```
bff/
├── bff_server.py      # Main FastAPI gateway server
├── auth.py            # MockAuthenticator (PoC) — replace in Phase 2
├── rate_limiter.py    # In-memory token bucket rate limiter
├── config.py          # Environment variable loader (BFF_ prefix)
├── user_tokens.json   # PoC user token registry
├── .env               # ⚠️ NEVER commit — contains Master API Key
├── .env.example       # Commit-safe template
└── README.md          # This file
```

---

## Security Notes

| Risk | Mitigation |
|:---|:---|
| `.env` readable on disk | Production: deploy on company cloud server, not user machines |
| Static dummy tokens | Production Phase 2: replace with JWT RS256 / Azure Entra ID |
| No HTTPS on localhost | Production Phase 1: Nginx reverse proxy + TLS certificate |
| No persistent rate limit | Production Phase 3: Redis-backed distributed rate limiter |

---

## Production Roadmap
- **Phase 1**: Deploy `bff/` to Azure VM with Nginx + HTTPS. Point Nanobot `api_base` to internal domain.
- **Phase 2**: Replace `MockAuthenticator` with JWT RS256 + Azure Entra ID OIDC.
- **Phase 3**: Integrate Azure APIM for quota management and audit log persistence.
