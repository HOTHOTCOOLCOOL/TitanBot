# Phase 54 Manual Test Guide: BFF Proxy Gateway

**Status**: ACTIVE
**Target Module**: `bff/`
**Related ADR**: `docs/adr/ADR-54-bff-proxy-gateway.md`
**Author**: Antigravity
**Date**: 2026-04-18

This guide outlines the manual verification steps for the Phase 54 BFF (Backend-For-Frontend) Proxy Gateway. The overarching goal is to verify that the gateway correctly intercepts LLM requests, securely injecting the actual master API key server-side while validating client authorization, enforcing rate limits, and ensuring the "zero-trust client" architecture is preserved.

---

## 🏗 Prerequisites

1. Active python virtual environment with `fastapi`, `uvicorn`, `litellm`, and `loguru` installed.
2. A valid Azure API key and base endpoint to test against.
3. Access to both the `bff/` gateway directory and the main `nanobot/` client directory.

---

## 🚦 Phase 1: Environment Initialization

### Step 1: Configure the BFF Environment
1. Navigate to the `bff` directory:
   ```powershell
   cd d:\Python\nanobot\bff
   ```
2. Create or verify the `.env` file exists and contains the Master Key configuration. **Do not use `.env.example` directly**:
   ```ini
   BFF_AZURE_API_KEY=your_actual_azure_master_key
   BFF_AZURE_API_BASE=https://your-company.openai.azure.com/
   ```

### Step 2: Start the BFF Gateway
Run the gateway server in a separate terminal:
```powershell
python bff_server.py
```
**Expected Output:**
- Server successfully binds to `http://127.0.0.1:8099`.
- Logs confirm loading of `azure` upstream provider, a rate limit of 60 RPM, and successful ingestion of `./user_tokens.json`.

---

## 🧪 Phase 2: Gateway Functionality & Security Tests

**Note:** The default tokens defined in `bff/user_tokens.json` for testing are:
- `user_zhangsan_tok_abc123def456`
- `user_lisi_tok_xyz789uvw012`

### Test Case 1: Health and Connectivity Diagnostics
Validate that the unauthenticated diagnostic endpoints are operational.

**Action:**
Via a new Powershell tab, send GET requests to the diagnostic endpoints:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8099/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8099/v1/models"
```
**Expected Result:**
- `/health` returns status `ok`.
- `/v1/models` successfully resolves available models supported by LiteLLM locally based on the Azure config.

### Test Case 2: Authentication Sandboxing
Verify the gateway correctly rejects unauthorized clients without exposing upstream error details.

**Action:**
Send a completion request using an invalid dummy token:
```powershell
$headers = @{
    "Authorization" = "Bearer invalid_malicious_token"
    "Content-Type"  = "application/json"
}
$body = @{
    model = "gpt-4o"
    messages = @( @{ role = "user"; content = "Ping" } )
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8099/v1/chat/completions" -Method POST -Headers $headers -Body $body
```
**Expected Result:**
- The server rejects the request with a **`401 Unauthorized`** response in standard OpenAI error JSON format.
- The BFF console logs an authentication failure (e.g., `user not found / token invalid`).
- **Critical:** The upstream Azure endpoints are NOT hit.

### Test Case 3: Rate Limit Enforcement
Verify the memory rate limiter properly throttles excessive traffic (60 RPM).

**Action:**
Using a valid test dummy token (`user_zhangsan_tok_abc123def456`), burst over 60 requests in quick succession.
```powershell
$headers = @{
    "Authorization" = "Bearer user_zhangsan_tok_abc123def456"
    "Content-Type"  = "application/json"
}
$body = @{
    model = "gpt-4o"
    messages = @( @{ role = "user"; content = "Ping" } )
} | ConvertTo-Json

for ($i=1; $i -le 65; $i++) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8099/v1/chat/completions" -Method POST -Headers $headers -Body $body | Out-Null
        Write-Host "Request ${i}: Success"
    } catch {
        Write-Host "Request ${i} Failed: $($_.Exception.Message)"
    }
}
```
**Expected Result:**
- Requests 1-60 should succeed / pass through.
- Requests 61+ must be rejected with a **`429 Too Many Requests`** status code.
- Wait 60 seconds. The bucket should replenish, and subsequent requests should succeed.

---

## 🔗 Phase 3: Client End-to-End Integration

### Test Case 4: Client Sandbox Configuration
Verify Nanobot can successfully leverage the BFF proxy dynamically.

**Action:**
1. Open the Nanobot client configuration file (`d:\Python\nanobot\config.json`).
2. Point the `custom` provider to the local gateway and specify the dummy token:
   ```json
   {
     "providers": {
       "custom": {
         "api_key": "user_zhangsan_tok_abc123def456",
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
3. Boot the Nanobot agent and run a basic query:
   ```powershell
   python main.py "Test the BFF connection, respond with Ping Acknowledged"
   ```

**Expected Result:**
- The agent effectively connects without network syntax errors.
- The agent outputs the correct response from upstream Azure via the BFF bridge.
- The server logs show the proxy routing the chat completion for `zhangsan`, indicating tokens consumed via LiteLLM audit.

---

## 🛡️ Phase 4: Structural Architecture Verification

**The following conditions must hold true for the test to pass completely:**

1. **Zero Knowledge Proof:** Open `d:\Python\nanobot\config.json` and ensure that `your_actual_azure_master_key` is nowhere to be found.
2. **Environment Variable Splitting:** Confirm `nanobot` runtime `.env` variables do not share or overlap with the BFF keys (BFF must strictly prefix `BFF_`).
3. **Log Scrubbing:** Check the `logs/` directory for Nanobot. There must be no accidental serialization or debugging prints that expose the Master Auth headers or `.env` parameters related to the proxy credentials.

## Validation Conclusion
If all 4 test stages succeed, the BFF Gateway successfully establishes the Zero-Trust Sandbox required for corporate deployment without modifying Nanobot's core HTTP engine, validating ADR-54 compliance.
