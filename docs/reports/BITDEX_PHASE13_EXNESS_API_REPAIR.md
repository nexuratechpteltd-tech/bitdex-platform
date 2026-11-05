# BITDEX — PHASE 13: EXNESS TRADER API REPAIR & ED25519 SPECIFICATION REPORT

**Timestamp:** 2026-11-05T00:19:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Modified Files:**
- `backend/app/services/exness/trader_api_adapter.py`
- `dashboard/src/components/dashboard/ExchangeConnectionsView.tsx`

---

## 1. Problem Statement & Root Cause Diagnosis

During testing on staging, Exness Trader API connection attempts repeatedly failed with `HTTP 404 Not Found` or `Name or service not known`.

### Root Cause Analysis
1. **Invalid Host `api.exness.com`**:
   - The frontend (`ExchangeConnectionsView.tsx`) hardcoded `server_name: "api.exness.com"`.
   - Direct HTTP test:
     ```bash
     curl -sI https://api.exness.com/
     # Output: HTTP/2 404 Not Found
     ```
   - Exness does not serve REST API operations on `api.exness.com`.
2. **Invalid Fallback `gateway.exness-api.com`**:
   - `trader_api_adapter.py` attempted DNS resolution against `gateway.exness-api.com`.
   - Direct DNS test:
     ```python
     socket.gethostbyname("gateway.exness-api.com")
     # Output: [Errno -2] Name or service not known
     ```
3. **Official Operational Host `https://www.exness-api.com`**:
   - Direct HTTP test:
     ```bash
     curl -sI https://www.exness-api.com/
     # Output: HTTP/2 200 OK
     ```
   - This is the genuine operational domain hosting the official Exness Developer & Trader API gateway.

---

## 2. Implemented Fixes

### 1. Backend Adapter Repair (`trader_api_adapter.py`)
- Replaced non-existent discovery domain `gateway.exness-api.com` with `https://www.exness-api.com`.
- Added defensive HTTP 404 exception handling that logs the exact target URI and diagnostic context rather than failing cryptically.
- Verified Ed25519 asymmetric signature generation:
  - Header `EXN-API-KEY`: Public key string.
  - Header `EXN-DATA`: Base64URL-encoded JSON payload (`api_key`, `timestamp`, `body_hash`, `path`, `idempotency_key`).
  - Header `EXN-SIGN`: Base64URL-encoded Ed25519 signature of `EXN-DATA`.

### 2. Frontend Modernization (`ExchangeConnectionsView.tsx`)
- Defaulted `serverName` state to `https://www.exness-api.com`.
- Removed hardcoded `api.exness.com` payload parameters.
- Provided an interactive "Test Connection" button calling the backend adapter with informative diagnostic feedback.
- Restructured the view to emphasize native Trader API integration over legacy MT5 screens.

---

## 3. Verification & Safety Posture

1. Target domain reachability verified: HTTP 200 OK.
2. Tenant credentials encrypted at rest using AES-256-GCM.
3. Fail-closed lock remains enforced: `live_trading_locked = True`.
