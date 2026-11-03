# TAURIC — Universal Add API UX & Bitget Authentication Repair Report
**Staging Host:** Germany VPS (`169.58.218.168`)  
**Staging Path:** `/opt/tauric-platform-staging/`  
**Production Status:** FROZEN & UNMODIFIED (`/opt/tauric-platform/`)  
**Date:** October 24, 2026  
**Safety Invariant:** `live_trading_locked=true`, `read_only_mode=true`, HTTP 403 on live order submission  

---

## 1. Executive Summary & Safety Invariants

This report documents the architectural repair and verification of Tauric's Universal Add API UX, Bitget authentication lifecycle, profile management, and actionable diagnostics on the isolated staging environment (`/opt/tauric-platform-staging/`).

### Mandatory Safety Boundary Compliance
- **Production Isolation:** Production codebase at `/opt/tauric-platform/` remained strictly untouched. PM2 process 0 (`tauric-backend`) and process 1 (`tauric-dashboard`) have maintained 13h+ uninterrupted uptime with zero restarts or modifications.
- **Safety Invariant Enforcement:** `live_trading_locked=true` and `read_only_mode=true` are strictly enforced at the config and route layers. Any attempt to submit a live order via `POST /api/v1/orders/live/submit` deterministically returns **HTTP 403 Forbidden** with detail:
  `"Live trading is hard-locked (\`live_trading_locked=true\`). Real exchange order submission is strictly blocked."`
- **Zero Real Order Placements:** No orders were placed, amended, canceled, or executed against any exchange or live broker. No real funds were moved or exposed.
- **Zero Withdrawal Permissions:** No withdrawal capabilities or API scopes were requested, granted, or handled.
- **Zero Credential Exposure:** Plaintext API secrets, passphrases, and HMAC signatures are never logged, printed, or returned in API responses.

---

## 2. Add API Screen Specification & Implementation

### A. The 5-Field Provider-Driven Form
The previous 8-step guided modal has been completely refactored into a universal, provider-driven form displaying **only the 5 necessary fields**:

1. **Exchange Provider Selector:**
   - Dropdown with supported providers: Bitget (default), Binance, Bybit, OKX, Coinbase, Kraken, MetaTrader 5 (MT5), Custom Forex REST Broker.
   - Defaults to `BITGET` upon opening.
2. **Profile Label (Optional):**
   - Text input with placeholder: `e.g. Bitget API 1 (Optional)`.
   - Optional: If left blank by the user, the backend automatically assigns a default label (e.g., `Bitget API Profile`).
3. **API Key (\* Required):**
   - Text input marked with `* Required`.
   - In edit mode, kept completely blank with placeholder `(Leave blank to keep existing)`.
4. **Secret Key (\* Required):**
   - Password input marked with `* Required`.
   - In edit mode, kept completely blank with placeholder `(Leave blank to keep existing)`.
5. **API Passphrase (Provider-Driven):**
   - **For Bitget:** Field is displayed and clearly marked `* Required for Bitget`.
   - **For Binance:** Passphrase field is hidden/omitted with an informational banner: `✓ No Passphrase Required for Binance. Binance authenticates using API Key and Secret HMAC-SHA256 signature.`
   - **For OKX / MT5:** Displays appropriate passphrase or broker server name field.

### B. Prohibited Questions Excluded
As explicitly mandated, the Add API form **does not ask any of the following during API creation**:
- Spot or Futures
- Demo or Live
- Coin or trading pair
- Trading strategy
- Investment amount
- Trading purpose

Execution configuration (Spot vs. Futures, Demo vs. Live) is decoupled from credential storage and configured post-save via the **Permissions & Environments** panel or the Universal Strategy Launch Wizard.

### C. Client & Server Validation
- Before submission, client-side validation checks that all required fields for the selected provider are populated.
- Inline validation errors (e.g., `API Key is required`, `Secret Key is required`, `Bitget requires an API Passphrase`) appear directly below the empty field.
- Server-side validation enforces provider schema rules, returning **HTTP 422 Unprocessable Content** if any provider-required field is omitted or submitted as empty/None.

---

## 3. API Profile List & Independent Lifecycle Controls

Every saved connection profile is rendered in the Connection Profiles list with:
- Provider name, environment badge (`DEMO` / `LIVE`), and market type (`CRYPTO` / `FOREX`).
- Profile label (user-defined or default).
- Masked API key (`bg_t••••••••7890` or `1234••••••••cdef`).
- Real-time connection status badge (`CONNECTED`, `AUTHENTICATION_FAILED`, `UNTESTED`, `DISCONNECTED`).
- Actionable error badge if probe failed (e.g. `[MISSING_PASSPHRASE]`, `[PROVIDER_AUTHENTICATION_REJECTED]`).
- Account balance/equity summary (if verified read-only probe succeeded).

### Lifecycle Controls
- **Independent ON/OFF Toggle:**
  - Dedicated switch per profile card.
  - Toggling one profile ON or OFF updates only that profile's `is_active` state in the vault and has zero side-effects on other profiles.
  - Disabled (`is_active=false`) profiles are excluded from strategy preflight eligibility.
- **Test API Connection Button:**
  - Probes live public and authenticated read endpoints without placing orders.
  - Updates profile verification label and actionable error codes atomically.
- **Permissions & Environments Button:**
  - Opens the dedicated configuration and capability panel for the selected profile.
- **Edit Button:**
  - Transitions profile into edit mode without populating masked keys.
- **Safe Disconnect / Deletion (Active Runs Check):**
  - Before deletion, the backend checks `strategy_orchestrator.list_strategy_runs()`.
  - If any active runs (`RUNNING`, `INITIALIZING`, `PAUSED`) depend on the profile, deletion is rejected with **HTTP 409 Conflict**:
    `"Cannot delete profile 'prof_xxx': active strategy runs depend on it."`
  - If no active runs depend on it, credentials are purged permanently from the AES-256-GCM vault.

---

## 4. Edit Profile Behavior & Secret Protection

### The Masked Key Prevention Invariant
In earlier builds, clicking "Edit" populated the form state with the masked display string (`p.api_key_masked`), causing subsequent saves to send masked bullets (`••••••••`) or truncated tokens (`bg_b...4881`) to the backend.

### Implemented Fix
1. **Frontend Edit State:**
   - When `handleEditConnection(p)` is triggered, `apiKey`, `apiSecret`, and `passphrase` are set to empty strings `""`.
   - Input placeholders display `(Leave blank to keep existing)`.
   - On submission, if a credential field is empty or whitespace-only, it is passed as `undefined` (omitted from the payload).
2. **Server-Side Rejection of Masked Strings:**
   - Backend `is_masked_credential()` checks `••••`, `...`, `***`, or regex `^[a-zA-Z0-9_-]{2,6}(\.{3,}|\*{3,}|•{3,})[a-zA-Z0-9_-]{2,6}$`.
   - If detected in `api_key`, `api_secret`, or `passphrase`, the backend immediately rejects the request with **HTTP 400 Bad Request**.
3. **Byte-for-Byte Preservation on Label/Metadata Edits:**
   - If credentials are not provided during edit, `credential_vault.update_profile()` preserves the existing AES-256-GCM encrypted payload (`_credentials_enc`) byte-for-byte.
   - Verified by automated regression test `Test 5`: `orig_enc == new_enc` holds true across label updates.

---

## 5. Permissions & Environments Panel

Clicking **Permissions & Environments** on any profile card opens a dedicated modal panel:

1. **Active Environment Switcher:**
   - Dropdown allows selecting `DEMO` (Testnet / Paper Matcher) or `LIVE` (Read-Only Balanced).
   - Changing the environment issues a `PUT /api/v1/connections/profiles/{id}` request, updating `environment` and `environment_preference` in the vault.
   - The cryptographic AAD tag (`profile_id:exchange:new_environment`) is rebound to preserve AES-256-GCM vault integrity.
2. **Supported Environments Display:**
   - Clear badges showing supported provider environments (e.g. `DEMO`, `LIVE` for Bitget Futures / Binance; `LIVE Only` for Kraken).
3. **Separation of Read Capabilities vs. Trade Capabilities:**
   - **Read Capabilities:** Market Data, Public Ticker, Account Info, Balances, Open Orders, Position Read.
   - **Trade Capabilities:** Order Placement, Order Cancellation, Order Amendment, Margin/Leverage.
   - Each capability displays exact state: `VERIFIED_SUPPORTED`, `UNSUPPORTED`, `PERMISSION_DENIED`, `NOT_TESTED (Safe)`.
4. **Exchange-Reported Permissions:**
   - Displays exchange-provided API key permissions (e.g., Spot Read, Futures Read, Spot Trade, Withdraw: Disabled).
5. **Connection Test Status:**
   - Real-time badge (`UNTESTED`, `CONNECTED`, `AUTHENTICATION_FAILED`, `DISCONNECTED`).
   - If failed, displays the actionable error banner with the exact error code and guidance.
6. **Explicit Legal / Safety Disclaimer:**
   > ⚠️ **Exchange Permission Policy:** Setting a local toggle or environment in Tauric does **NOT** grant permissions on the exchange. You must explicitly configure API permissions (Read, Trade, Futures) directly in your exchange account settings console.

---

## 6. Bitget Authentication Deep Dive & Root Cause Analysis

### Complete Request Trace
1. **Form Submission:** Provider `BITGET`, API Key, Secret Key, Passphrase entered by user.
2. **Vault Encryption:** AES-256-GCM encrypts `{api_key, api_secret, passphrase}` with AAD `profile_id:BITGET:DEMO`.
3. **Profile Retest Probe:** Calls `exchange_framework.detect_account_capabilities()`.
4. **Parameter Resolution:**
   - For `BITGET` in `DEMO`, routes to `https://api.bitget.com/api/v2/mix/account/accounts?productType=USDT-FUTURES` with header `paptrading: 1`.
   - Symbol parameter is resolved to `SBTCSUSDT` for simulated contract matching.
5. **Request Signing:**
   - Header `ACCESS-KEY`: User's Bitget API key.
   - Header `ACCESS-TIMESTAMP`: Current timestamp in milliseconds (`str(int(time.time() * 1000))`).
   - Header `ACCESS-PASSPHRASE`: User's custom API passphrase.
   - Header `ACCESS-SIGN`: Base64-encoded HMAC-SHA256 of `timestamp + method + request_path + query_or_body` using `api_secret`.

### Root Cause of Prior Bitget Failure
In prior testing, profile `prof_bitget_demo_a2bb3478` had an empty passphrase stored (`passphrase=""`).
- For public market endpoints (`/api/v2/public/time`, `/api/v2/mix/market/contracts`), Bitget does not require credentials, so connectivity tests reported `PASS`.
- For private endpoints (`/api/v2/mix/account/accounts`), Bitget requires `ACCESS-PASSPHRASE`.
- When the passphrase was empty, the previous adapter converted `None` to the string `"None"`, which Bitget rejected with HTTP 401 code `40014` (`invalid sign`) or `40003`.
- **The Implemented Fix:** If passphrase is missing or empty for Bitget, the backend raises `ValueError` before making any network request:
  `"Bitget requires a non-empty API passphrase. Preflight failed: no network request performed."`
  The system immediately maps this to actionable error code `MISSING_PASSPHRASE`.

---

## 7. Standardized Actionable Diagnostics Matrix

The generic `"CONNECTED TO PROVIDER — AUTHENTICATION FAILED"` message has been replaced across the backend and frontend by **9 standardized actionable diagnostic categories**:

| Actionable Error Code | Condition / Trigger | Guidance Displayed to User |
| :--- | :--- | :--- |
| `MISSING_API_KEY` | API key field omitted or empty | API key was not provided. Please enter a valid API key. |
| `MISSING_API_SECRET` | API secret field omitted or empty | API secret was not provided. Please enter a valid API secret. |
| `MISSING_PASSPHRASE` | Bitget, OKX, or MT5 missing passphrase | API passphrase is required for Bitget. Configure your custom passphrase set during API key generation. |
| `ENVIRONMENT_MISMATCH` | Code `40099`, Bitget Spot Demo request, or testnet key on live endpoint | The API key was created for a different environment (e.g. Live key used in Demo, or Demo key in Live). |
| `SIGNATURE_VALIDATION_FAILED` | Code `40014`, `40003`, `-1022`, or invalid sign | Request signature could not be verified by the exchange. Check secret key and passphrase. |
| `TIMESTAMP_OR_RECV_WINDOW_ERROR` | Code `-1021`, `40005`, `40006`, or recvWindow error | Server timestamp differs from exchange time. Check system clock synchronization. |
| `PROVIDER_AUTHENTICATION_REJECTED` | Code `-2014`, `-2015`, `40037`, `40001`, or HTTP 401 | Exchange rejected credentials. Verify API key, secret, and IP whitelist permissions. |
| `PROVIDER_REQUEST_ERROR` | HTTP 400, 404, 500, 502, 503, 504 | Provider returned an unexpected response format or HTTP status code. |
| `AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE` | Network timeout, DNS failure, or unmapped exception | Authentication could not be verified. Inspect network logs and response payload. |

---

## 8. Test Execution Matrix & Verification Evidence

All test suites were executed directly on the Germany VPS staging environment using the staging virtual environment (`/opt/tauric-platform-staging/backend/.venv/bin/python3`):

### Suite 1: Claude Audit 12-Point Regression Suite (`test_claude_audit_repairs.py`)
- **Command:** `/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/test_claude_audit_repairs.py`
- **Result:** **12/12 PASSED (100%)**
  - Test 1: None and empty passphrases never generate a 'None' header — **PASS**
  - Test 2: Bitget preflight fails on missing passphrase with no network request — **PASS**
  - Test 3: Bitget Demo versus Live parameter resolution (`SUSDT-FUTURES` / `1`) — **PASS**
  - Test 4: Masked key submissions rejected server-side — **PASS**
  - Test 5: Label-only profile edit preserves original key byte-for-byte — **PASS**
  - Test 6: Retesting cannot override saved profile environment or product — **PASS**
  - Test 7: Missing required credentials rejected server-side (HTTP 422) — **PASS**
  - Test 8: Binance signing and transmitted query strings match exactly — **PASS**
  - Test 9: Permission discovery does not infer key trade from account canTrade — **PASS**
  - Test 10: Profile IDs are unique and deletion does not affect other profiles — **PASS**
  - Test 11: Deletion rejected when active strategy runs depend on profile (HTTP 409) — **PASS**
  - Test 12: No secret values appear in logs or public responses — **PASS**

### Suite 2: Add API UX & Bitget Authentication Suite (`test_add_api_ux_and_bitget_auth.py`)
- **Command:** `/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/test_add_api_ux_and_bitget_auth.py`
- **Result:** **7/7 PASSED (100%)**
  - Test 1: Universal Add API Schema Verification (5 fields only, no prohibited questions) — **PASS**
  - Test 2: Bitget MISSING_PASSPHRASE Resolution (preflight blocked) — **PASS**
  - Test 3: All 9 Standardized Actionable Diagnostic Codes — **PASS**
  - Test 4: Edit Profile Preserves Credentials Byte-for-Byte — **PASS**
  - Test 5: Permissions & Environments Active Environment Switcher (DEMO <-> LIVE) — **PASS**
  - Test 6: Safe Deletion Blocks on Active Runs (HTTP 409) — **PASS**
  - Test 7: Live Trading Hard Lock Safety Invariant (HTTP 403) — **PASS**

### Suite 3: 13-Point Universal API Management Suite (`run_api_management_13_point_tests.py`)
- **Command:** `/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/run_api_management_13_point_tests.py`
- **Result:** **13/13 PASSED (100%)**
  - Live public market data queries (Binance BTC: \$80,944.97, Bitget BTC: \$80,909.80).
  - Toggling ON/OFF persistence & independence.
  - Safe profile deletion.
  - Compact macroeconomic calendar preview (3 items with See more / Show less).
  - Live trading lock enforced (HTTP 403).

### Suite 4: 14-Point Universal Strategy Orchestration Suite (`test_universal_strategy_orchestration.py`)
- **Command:** `/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/test_universal_strategy_orchestration.py`
- **Result:** **14/14 PASSED (100%)**
  - Dynamic discovery of arbitrary providers in wizard.
  - Multi-profile coexistence for same exchange.
  - Zero cross-profile or cross-environment data leakage.
  - Idempotent strategy execution.
  - Account balance preflight checks.

---

## 9. Deployment Verification & Process Status

### Staging PM2 Process Status
```
┌────┬─────────────────────────────┬─────────────┬─────────┬─────────┬──────────┬────────┬──────┬───────────┬──────────┬──────────┐
│ id │ name                        │ namespace   │ version │ mode    │ pid      │ uptime │ ↺    │ status    │ cpu      │ mem      │
├────┼─────────────────────────────┼─────────────┼─────────┼─────────┼──────────┼────────┼──────┼───────────┼──────────┼──────────┤
│ 0  │ tauric-backend              │ default     │ N/A     │ fork    │ 330429   │ 13h    │ 16   │ online    │ 0%       │ 296.7mb  │ [PROD - UNTOUCHED]
│ 3  │ tauric-backend-staging      │ default     │ N/A     │ fork    │ 375766   │ online │ 226  │ online    │ 0%       │ 169.0mb  │ [STAGING - UPDATED]
│ 1  │ tauric-dashboard            │ default     │ N/A     │ fork    │ 330438   │ 13h    │ 17   │ online    │ 0%       │ 60.4mb   │ [PROD - UNTOUCHED]
│ 5  │ tauric-dashboard-staging    │ default     │ 1.0.0   │ fork    │ 374469   │ online │ 17   │ online    │ 0%       │ 97.8mb   │ [STAGING - UPDATED]
└────┴─────────────────────────────┴─────────────┴─────────┴─────────┴──────────┴────────┴──────┴───────────┴──────────┴──────────┘
```

### Next.js Dashboard Build Status
```
> tauric-portal@1.0.0 build
> next build
  ▲ Next.js 14.2.13
  ✓ Compiled successfully
  ✓ Generating static pages (4/4)
  ✓ Finalizing page optimization
```

### Deliverable File Locations on Remote Staging Host
- **Report:** `/opt/tauric-platform-staging/tauric_bitget_auth_root_cause_and_api_ux_report.md`
- **Test Suite 1:** `/opt/tauric-platform-staging/test_claude_audit_repairs.py` (12/12 PASS)
- **Test Suite 2:** `/opt/tauric-platform-staging/test_add_api_ux_and_bitget_auth.py` (7/7 PASS)
- **Test Suite 3:** `/opt/tauric-platform-staging/run_api_management_13_point_tests.py` (13/13 PASS)
- **Test Suite 4:** `/opt/tauric-platform-staging/test_universal_strategy_orchestration.py` (14/14 PASS)
- **Backend Service:** `/opt/tauric-platform-staging/backend/app/services/exchange_framework.py`
- **Backend Route:** `/opt/tauric-platform-staging/backend/app/routes/connections.py`
- **Frontend Component:** `/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx`

---
*End of Report. Staging repair completed and verified with 100% test pass rate across 46 automated checks.*
