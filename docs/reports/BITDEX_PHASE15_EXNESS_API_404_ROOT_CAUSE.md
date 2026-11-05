# BITDEX — PHASE 15: EXNESS API 404 ROOT CAUSE & ARCHITECTURAL REPAIR

**Authoritative System:** BITDEX Institutional Platform  
**Environment:** Linux Staging Server (`169.58.218.168`)  
**Domain:** `https://bitdex.ltd`  
**Git Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Timestamp:** 2026-11-05T12:45:00Z  

---

## 1. Problem Statement

During staging acceptance testing, clicking "Test Connection" for Exness Trader API repeatedly failed with the error:
```
Test Connection Error: Not Found
```
Previous reports erroneously assumed this was an external DNS issue or simply a client formatting error. A systematic audit of the entire request lifecycle—from browser network dispatch, Cloudflare edge, Nginx reverse proxy, FastAPI route handling, to upstream broker communication—revealed four interrelated defects that produced `Not Found`.

---

## 2. Exhaustive Root Cause Analysis

### Root Cause 1: Nginx Port 443 Hardcoding to Production
- **Discovery**: In `/etc/nginx/sites-available/tauric-portal.conf`, the `server { listen 80; }` block was configured with dynamic port mapping (`$backend_target_port = 8002`, `$frontend_target_port = 33900` for `bitdex.ltd`).
- **The Defect**: The `server { listen 443 ssl; }` block had **NOT** been updated. It contained:
  ```nginx
  server {
      listen 443 ssl http2 default_server;
      server_name sheltr.agency shelter.agency ...;
      location /api/v1/ {
          proxy_pass http://127.0.0.1:8001/api/v1/;
      }
      location / {
          proxy_pass http://127.0.0.1:8080;
      }
  }
  ```
- **Consequence**: When external browser clients connected to `https://bitdex.ltd/api/v1/hft/exness/real/connect` over HTTPS, Cloudflare or the browser connected to port 443. Nginx forwarded all `/api/v1/` traffic directly to **Port 8001 (Production Backend)**, where `exness_hft` was unmounted.
- FastAPI on port 8001 returned:
  ```json
  {"detail": "Not Found"}
  ```
- The frontend `ExchangeConnectionsView.tsx` caught this JSON detail and rendered `Test Connection Error: Not Found`.

### Root Cause 2: Nginx Variable Proxy_Pass URI Stripping
- **The Defect**: When Nginx `proxy_pass` uses a variable with a trailing URI (e.g. `proxy_pass http://127.0.0.1:$backend_target_port/api/v1/;`), Nginx does not perform normal prefix translation; instead, it literally passes `/api/v1/` as the downstream URI!
- **Consequence**: The FastAPI server on port 8002 received:
  ```
  INFO: 127.0.0.1:0 - "POST /api/v1/ HTTP/1.1" 404 Not Found
  ```
  The path suffix `/hft/exness/real/connect` was stripped entirely by Nginx before reaching FastAPI.

### Root Cause 3: Upstream Exness Documentation Portal Host Confusion
- **Discovery**: The frontend form defaulted `server_name` to `https://www.exness-api.com`.
- **The Defect**: `https://www.exness-api.com` is the **Docusaurus documentation website** (`x-router-node: open-api-docs-7977594976-b2npx`, `content-type: text/html`), **NOT** an operational REST API gateway.
- Querying `https://www.exness-api.com/v1/accounts/{id}` or `https://www.exness-api.com/v1/trading/access-point` returns either HTTP 404 HTML or HTTP 200 with `content-length: 0`.
- In `trader_api_adapter.py`, `res.json()` failed on empty/HTML responses with:
  ```
  json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  ```
  This threw an unhandled 500 or bubbled up a 404 to the client.

### Root Cause 4: Ed25519 Secret Key Parsing Flaw
- **The Defect**: In Exness Personal Area (Key Management), Exness generates 128-hex character private keys (a 64-byte keypair consisting of a 32-byte Ed25519 seed followed by a 32-byte public key).
- In `_initialize_private_key()`, the code only anticipated 64-char or 32-char strings:
  ```python
  elif len(self.api_secret) == 64:
      ...
  elif len(self.api_secret) == 32:
      ...
  else:
      derived_seed = hashlib.sha256(sec_bytes).digest() # BUG: SHA-256 hashed the 128-char string
  ```
- Because `len == 128`, it fell into the fallback `else:` branch and SHA-256 hashed the ASCII string, deriving an invalid cryptographic seed and producing rejected signatures.

---

## 3. Implemented Engineering Remediations

### 1. Unified Nginx Routing (`/etc/nginx/sites-available/tauric-portal.conf`)
- Configured both Port 80 and Port 443 blocks with identical dynamic routing maps for `bitdex.ltd`:
  - Added `bitdex.ltd www.bitdex.ltd` to `server_name` on Port 443.
  - Updated `/api/v1/` to `proxy_pass http://127.0.0.1:$backend_target_port;` (removed trailing URI to prevent path stripping).
  - Added `/api/backend/` location with rewrite to `/api/v1/` targeting `$backend_target_port`.
  - Updated root `/` location to `proxy_pass http://127.0.0.1:$frontend_target_port;`.

### 2. Ed25519 128-Character Hex Parsing (`trader_api_adapter.py`)
- Updated `_initialize_private_key()` to support official RFC 8410 / Exness Ed25519 key formats:
  ```python
  elif len(self.api_secret) == 128:
      # Exness official 128-hex character private key (32-byte seed + 32-byte pubkey)
      seed_bytes = bytes.fromhex(self.api_secret[:64])
      self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed_bytes)
  ```

### 3. Non-API / HTML Response Shield (`trader_api_adapter.py`)
- Added defensive validation in `discover_access_point()` and `connect()`:
  ```python
  ct = res.headers.get("content-type", "").lower()
  if "text/html" in ct or not isinstance(data, dict):
      return {
          "status": "RESOURCE_NOT_FOUND",
          "adapter_connected": False,
          "broker_authenticated": False,
          "reason": f"Target host '{target_api}' returned non-API response (content-type: {ct}). "
                    f"The Gateway Host must be the official Exness Gateway host obtained from "
                    f"your Exness Personal Area Key Management DNS widget."
      }
  ```

### 4. Session Validation URL Fix (`dashboard/src/app/page.tsx`)
- Changed `fetch("/trading/api/backend/saas/customer/me")` to `fetch("/api/backend/saas/customer/me")` to eliminate 404 session invalidation loops on reload.

---

## 4. Verification & Confirmation

Following the deployment, an end-to-end verification probe was executed:
```bash
POST /api/v1/hft/exness/real/connect
Headers: Authorization: Bearer <valid_admin_token>, Content-Type: application/json
Payload: {"connection_method": "TRADER_API", "account_login": "16000629657", ...}
```

**Result:**
- HTTP 404 is completely eliminated.
- The request reaches `connect_exness_real` on Port 8002 via HTTPS.
- The adapter returns a structured HTTP 400 with diagnostic explanation when unprovisioned or doc-portal keys are provided.
- Zero mock data or fabricated success returned.
