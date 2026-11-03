# TAURIC — Audit Remediation Phase 1 Report (Staging Only)
**Security Boundary, Provider-Aware Passphrase Diagnostics, Strategy Wizard Eligibility & Balance Unification, and Missing `Master` Profile Investigation**

- **Date (UTC):** `2026-10-24T10:41:00Z`
- **Target Environment:** Staging Only (`/opt/tauric-platform-staging/`)
- **Production Status (`/opt/tauric-platform/`):** **UNTOUCHED** (`0` files modified, vault SHA-256 unchanged, PM2 processes `tauric-backend` and `tauric-dashboard` untouched)
- **Safety Locks:** `live_trading_locked=true`, `read_only_mode=true`, `POST /api/v1/orders/live/submit` returns `HTTP 403`

---

## 1. Security Investigation & Staging Remediation (P0)

### 1.1 Architectural Audit Findings
| Area Inspected | Pre-Remediation State | Risk / Finding | Staging Remediation Applied |
| :--- | :--- | :--- | :--- |
| **API Caller Authentication (`/api/v1/*`)** | FastAPI routers (`/api/v1/connections/*`, `/api/v1/orchestration/*`, `/api/v1/orders/*`) had no caller authentication middleware. | Any local process or exposed upstream route could query or mutate profiles without an authenticated token. | Implemented `TauricSecurityMiddleware` in `/opt/tauric-platform-staging/backend/app/security.py` requiring `X-Tauric-Api-Key` or `Authorization: Bearer <token>` (constant-time `hmac.compare_digest` against HMAC-SHA256 derived token) on all `/api/v1/*` routes except `/api/v1/health`. Unauthenticated calls return `HTTP 401 UNAUTHORIZED_API_REQUEST`. |
| **Staging Next.js Proxy Target (`route.ts`)** | `/opt/tauric-platform-staging/dashboard/src/app/api/backend/[...slug]/route.ts` line 3 had `const BACKEND_INTERNAL_URL = process.env.INTERNAL_BACKEND_URL \|\| "http://127.0.0.1:8001";` and `INTERNAL_BACKEND_URL` was unset in PM2 `tauric-dashboard-staging`. | **Critical Cross-Wiring Bug:** Requests to the staging dashboard (`:33900`) were silently proxying to the **production** backend (`127.0.0.1:8001`) instead of the staging backend (`127.0.0.1:8002`). | Hard-pinned staging `route.ts` to `http://127.0.0.1:8002`, added an explicit runtime guard forbidding port `8001`, and injected server-side `X-Tauric-Api-Key` on internal hops to `127.0.0.1:8002`. |
| **Transport Security Gate (Credential Submissions)** | No check on `X-Forwarded-Proto` when receiving API keys/secrets/passphrases. | If an edge proxy forwarded a non-HTTPS request over an unencrypted hop, credentials could traverse plaintext HTTP. | Enforced Transport Security Gate in both Next.js (`route.ts`) and FastAPI (`security.py`): any `POST`/`PUT` carrying credentials (`universal`, `profiles`, `test`, `retest`) over non-loopback plaintext HTTP (`X-Forwarded-Proto: http`) is rejected with `HTTP 403 INSECURE_TRANSPORT_BLOCKED`. |
| **CORS Policy (`main.py`)** | `allow_origins=["*"]` combined with `allow_credentials=True`. | Permitted arbitrary cross-origin callers with credentials. | Restricted `CORSMiddleware` to explicit `settings.allowed_origins` (`https://sheltr.agency`, `https://www.sheltr.agency`, `https://bybit-gateway.sheltr.agency:33900`, `http://127.0.0.1:33900`, `http://localhost:33900`). |
| **OpenAPI / Swagger Docs Exposure** | `/docs`, `/redoc`, and `/openapi.json` were publicly enabled by default. | Exposed internal API schema and route surface. | Disabled `/docs`, `/redoc`, and `/openapi.json` by default (`settings.enable_api_docs = False`), returning `HTTP 404`. |
| **Edge-to-VPS Hop (`185.143.172.248` -> `169.58.218.168`)** | Namecheap cPanel edge Apache (`185.143.172.248`) proxies `https://sheltr.agency/` to `http://169.58.218.168:8080/` over port `8080`. | Traffic between browser and `sheltr.agency` is TLS-encrypted, but the edge-to-VPS hop over port `8080` is plaintext HTTP. | Prepared safe production cutover plan (without touching production Nginx/edge in Phase 1): enable `SSLProxyEngine on` in Namecheap Apache `/home/sheldkbe/revproxy/proxy_pass.conf` targeting `https://bybit-gateway.sheltr.agency:8443/` (using the existing valid Let's Encrypt certificate `/etc/letsencrypt/live/bybit-gateway.sheltr.agency/fullchain.pem` on the Germany VPS). |

---

## 2. Passphrase Error Classification & Stale State Fixes (P1)

### 2.1 Root Causes Identified
1. **Misleading Wrapper String Matched Before `provider_error_code`:**
   - In `exchange_framework.py` line 4504 (`CustomExchangeAdapter.run_capability_verification`), any HTTP 400/401/403 authentication failure constructed:
     ```python
     error_detail = f"Authentication rejected by exchange (HTTP {resp.status_code}): Invalid API Key, Passphrase, or Signature."
     ```
   - `resolve_actionable_error_code()` (formerly line 1091) checked `if "passphrase" in err_lower:` **before** checking `provider_code` (`-2015`, `-2014`, `40099`) or checking whether the provider schema even uses a passphrase (`requires_passphrase`). Because `"Passphrase"` was present in `error_detail`, every HTTP 400/401 rejection—including Binance `-2015` and Bitget `40099`—was misclassified as `MISSING_PASSPHRASE`!
2. **Hardcoded Bitget Guidance in `connections.py` and `UnifiedSignalDashboard.tsx`:**
   - `connections.py` (lines 818 and 1097) and `UnifiedSignalDashboard.tsx` (line 139) hardcoded `"API passphrase is required for Bitget..."` whenever `MISSING_PASSPHRASE` was returned.
3. **Silent Passphrase Deletion During Provider Identification:**
   - `CredentialVault.identify_profile()` called `self._rebind_profile(p, prov, "UNSET", {}, keep_passphrase=bool(schema.get("requires_passphrase")))`, which overwrote a saved passphrase with `""` if a user initially selected `BINANCE`, and blocked re-identification even when no strategy run used the profile.
4. **Stale Error Banner Persistence After Editing:**
   - `CredentialVault.update_profile()` set `connection_status = "UNTESTED"`, but left `actionable_error_code`, `provider_error_code`, `endpoint_results`, `capability_matrix`, and `permission_matrix` populated, causing the UI card and modal to keep displaying the old failure banner.

### 2.2 Staging Fixes Implemented
- **Provider-Code-First Error Resolution (`resolve_actionable_error_code` in `exchange_framework.py`):**
  - Removed `"Passphrase"` from generic HTTP 400/401/403 wrapper text and stripped wrapper phrases before text matching.
  - Examines `provider_code` **first**:
    - `40014`, `40004`, `40037`, `-2014` $\rightarrow$ `INVALID_API_KEY`
    - `-2015` (Binance) $\rightarrow$ `INVALID_API_KEY` (or `IP_NOT_WHITELISTED` if IP-specific), preserving `provider_error_code = "-2015"`
    - `40099` (Bitget) $\rightarrow$ `ENVIRONMENT_KEY_MISMATCH`, preserving `provider_error_code = "40099"`
    - `40034`, `40009`, `-1022` $\rightarrow$ `SIGNATURE_MISMATCH`
    - `40005`, `40007`, `-1021` $\rightarrow$ `TIMESTAMP_SKEW`
    - `40006`, `50110` $\rightarrow$ `IP_NOT_WHITELISTED`
    - `40017`, `40018`, `40012` $\rightarrow$ `MISSING_PASSPHRASE` (only if passphrase is absent) or `PASSPHRASE_MISMATCH` (if passphrase is present)
  - Enforced the strict invariant: `MISSING_PASSPHRASE` is returned **only** when `provider_requires_passphrase(exchange) is True` **and** `has_passphrase is False`.
  - Pre-test configuration gate (`_config_block` in `connections.py`) checks `provider_requires_passphrase(exch) and not creds.get("passphrase")` and returns `MISSING_PASSPHRASE` with `network_request_made: False` and `provider_error_code: None`.
- **Provider-Schema-Driven Error Guidance (`get_provider_error_guidance`):**
  - Generates error remediation text dynamically from `PROVIDER_SCHEMAS[exchange]` and attaches `error_guidance`, `provider_error_code`, and `provider_error_message` to both the profile public representation and `/capability-report`.
- **Stale State Clearing & Passphrase Preservation:**
  - Added `_clear_stale_verification_state(p)` and invoked it in `_rebind_profile`, `identify_profile`, `configure_profile`, and `update_profile`.
  - Updated `identify_profile()` to always preserve any saved passphrase (`keep_passphrase=True`) and allow safe re-identification whenever no active strategy run (`RUNNING`, `INITIALIZING`, `PAUSED`) depends on the profile.

---

## 3. Strategy Wizard Balance, Server-Side Eligibility & Multi-Profile Fixes (P2)

### 3.1 Unified Balance Schema & Truthful Unverified State
- **Root Cause:** `exchange_framework.py` wrote `total_equity_usd`, `available_balance_usd`, and `asset_balances` (`available`), whereas `strategy_orchestrator.py` (`get_profile_available_capital`) read `total_valuation_usd` and `assets` (`free`), defaulting to `0.0` (`$0.00`) for every profile.
- **Fix:**
  - Unified the schema across `exchange_framework.py` and `strategy_orchestrator.py` (`available_balance_usd`, `total_equity_usd`, `asset_balances` with both `"available"` and `"free"`, plus `balance_verified: True`).
  - When a profile's private authentication is not verified (`UNTESTED`, `AUTHENTICATION_FAILED`, `DISCONNECTED`) or has no verified balance payload, `get_profile_available_capital()` now returns `available_capital: None`, `total_equity: None`, `verified: False`, and `balance_display: "NOT TESTED"` or `"NOT VERIFIED"` — **never** inventing `$0.00`.

### 3.2 Single Authoritative Provider Registry & 7-Point Server-Side Eligibility
- Replaced the duplicate `PROVIDER_IMPLEMENTATION_STATUS` dictionary in `strategy_orchestrator.py` (which previously marked `BYBIT`, `COINBASE`, and `OKX` as `IMPLEMENTED_TESTED`) with `get_authoritative_provider_status_map()` derived strictly from `PROVIDER_SCHEMAS` and `implemented_provider_ids()` in `exchange_framework.py` (only `BINANCE` and `BITGET` are `IMPLEMENTED_TESTED`, plus `PAPER` simulator; `BYBIT`, `COINBASE`, `OKX`, `KRAKEN`, `DERIBIT`, `INTERACTIVE_BROKERS` are `PLANNED`; `MT5`, `CUSTOM_FOREX` are `BRIDGE_DEPENDENT`).
- Updated `GET /api/v1/orchestration/profiles/eligible` (`evaluate_profile_eligibility`) to enforce all 7 server-side gates:
  1. Excludes synthetic automated test fixture profiles (`is_automated_test_fixture_profile`, excluding all 39 synthetic test profiles in staging without deleting them).
  2. Provider is identified (`PROVIDER_NOT_IDENTIFIED`).
  3. Provider adapter is `IMPLEMENTED_TESTED` (`ADAPTER_NOT_IMPLEMENTED`).
  4. Environment (`DEMO`/`LIVE`) and product type are configured and supported by `PROVIDER_SCHEMAS` (`CONFIGURATION_INCOMPLETE` / `UNSUPPORTED_ENVIRONMENT`).
  5. Profile is enabled (`is_active == True`, `PROFILE_DISABLED`).
  6. Required credentials (including passphrase when `requires_passphrase == True`) are present and private authentication is verified (`MISSING_PASSPHRASE` / `PRIVATE_AUTH_NOT_VERIFIED`).
  7. Environment is not blocked by `live_trading_locked=true` (`LIVE_TRADING_LOCKED`).
- Updated Strategy Wizard Step B & Step D in `UnifiedSignalDashboard.tsx` to consume `/trading/api/backend/orchestration/profiles/eligible/`, allow selecting **one or multiple** eligible profiles (`profile_ids`) with full per-profile run/balance/environment isolation, and display ineligible user profiles as disabled with their explicit `[eligibility_code]` reason and `NOT VERIFIED` / `NOT TESTED` balance badge.

---

## 4. Read-Only Investigation of the Missing `Master` Profile (Section 5)

A strictly read-only forensic inspection of the production vault, pre-migration backup vault, staging vault, and Nginx access logs established the exact timeline and cause:

1. **Pre-Migration Backup Vault (`/opt/tauric-platform/backups/canonical_cutover_20261024T001200Z/backend_data/credential_vault.json`):**
   - Contains **2 profiles**, including the `Master` profile intact:
     - `prof_bitget_demo_a2bb3478`: `label="Master"`, `exchange="BITGET"`, `environment="DEMO"`, `product_type="FUTURES_USDT"`, `created_at_utc="2026-10-23T08:13:01Z"`, `api_key_masked="bg_c••••692a"`, `has_passphrase=False`.
     - `prof_binance_demo_b4ac8f0c`: `label="Binance Demo"`, `exchange="BINANCE"`, `environment="DEMO"`, `product_type="SPOT"`, `created_at_utc="2026-10-23T11:36:39Z"`.
2. **Staging Vault (`/opt/tauric-platform-staging/backend/data/credential_vault.json`):**
   - Also still contains `prof_bitget_demo_a2bb3478` (`label="Master"`, `exchange="BITGET"`, `environment="DEMO"`, `product_type="FUTURES_USDT"`, `api_key_masked="bg_c••••692a"`).
3. **Why `Master` Disappeared from Current Production (`/opt/tauric-platform/backend/data/credential_vault.json`):**
   - Inspection of `/var/log/nginx/access.log` showed that at **`2026-10-24T00:33:19Z`** (`24/Oct/2026:02:33:19 +0200`), an explicit HTTP `DELETE` request was sent from a user browser session (`Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ... Chrome/141.0.0.0 Safari/537.36`) on `https://sheltr.agency/`:
     ```text
     185.143.172.248 - - [24/Oct/2026:02:33:19 +0200] "DELETE /api/backend/connections/profiles/prof_bitget_demo_a2bb3478/ HTTP/1.1" 200 107 "https://sheltr.agency/"
     185.143.172.248 - - [24/Oct/2026:02:33:30 +0200] "DELETE /api/backend/connections/profiles/prof_binance_demo_b4ac8f0c/ HTTP/1.1" 200 112 "https://sheltr.agency/"
     185.143.172.248 - - [24/Oct/2026:02:34:06 +0200] "POST /api/backend/connections/universal/ HTTP/1.1" 200 949 "https://sheltr.agency/"
     ```
   - Additionally, prior to our Phase 1 fix in staging `route.ts`, the staging dashboard on port `33900` had `BACKEND_INTERNAL_URL` defaulting to `http://127.0.0.1:8001` (production), meaning any action taken in the staging UI was also mutating the production backend on port `8001`.
   - Because `prof_bitget_demo_a2bb3478` (`Master`) is preserved intact in both `/opt/tauric-platform/backups/canonical_cutover_20261024T001200Z/backend_data/credential_vault.json` and `/opt/tauric-platform-staging/backend/data/credential_vault.json`, its encrypted record was **not** lost and can be restored to production at any time if desired, while keeping the two newer profiles (`prof_conn_a1a44343` and `prof_conn_3e0d914e`) created on Oct 24.

---

## 5. Backups & Modified Files in Staging Only

### 5.1 Pre-Modification Staging Backups
All modified staging files were backed up prior to editing at:
- `/opt/tauric-platform-staging/backups/phase1_audit_remediation_20261024/`

### 5.2 Staging Files Created / Modified
1. [`/opt/tauric-platform-staging/backend/app/security.py`](file:///opt/tauric-platform-staging/backend/app/security.py) *(Created)* — `TauricSecurityMiddleware`, `get_api_auth_token()`, caller authentication enforcement on `/api/v1/*`, and Transport Security Gate blocking plaintext HTTP credential submissions.
2. [`/opt/tauric-platform-staging/backend/app/config.py`](file:///opt/tauric-platform-staging/backend/app/config.py) *(Modified)* — Added `api_auth_required`, `enforce_transport_security`, `enable_api_docs = False`, and explicit `allowed_origins`.
3. [`/opt/tauric-platform-staging/backend/app/main.py`](file:///opt/tauric-platform-staging/backend/app/main.py) *(Modified)* — Mounted `TauricSecurityMiddleware`, restricted `CORSMiddleware` to `settings.allowed_origins`, and disabled `/docs`, `/redoc`, and `/openapi.json` by default.
4. [`/opt/tauric-platform-staging/dashboard/src/app/api/backend/[...slug]/route.ts`](file:///opt/tauric-platform-staging/dashboard/src/app/api/backend/[...slug]/route.ts) *(Modified)* — Hard-pinned staging proxy to `http://127.0.0.1:8002` (forbidding port `8001`), enforced Transport Security Gate, and attached server-side `X-Tauric-Api-Key`.
5. [`/opt/tauric-platform-staging/backend/app/services/exchange_framework.py`](file:///opt/tauric-platform-staging/backend/app/services/exchange_framework.py) *(Modified)* — Added `provider_requires_passphrase()`, `get_provider_error_guidance()`, `is_automated_test_fixture_profile()`, `_clear_stale_verification_state()`; rewrote `resolve_actionable_error_code()` to inspect `provider_code` first and never infer `MISSING_PASSPHRASE` from generic wrapper text or non-passphrase providers; preserved passphrases during `identify_profile()`; unified `account_data` balance schema.
6. [`/opt/tauric-platform-staging/backend/app/routes/connections.py`](file:///opt/tauric-platform-staging/backend/app/routes/connections.py) *(Modified)* — Updated `_config_block()` to catch missing required passphrases pre-network (`network_request_made: False`), removed hardcoded Bitget strings from `retest_profile()` and `test_connection()`, and enriched `/capability-report` with `provider_error_code`, `provider_error_message`, `error_guidance`, and `requires_passphrase`.
7. [`/opt/tauric-platform-staging/backend/app/services/strategy_orchestrator.py`](file:///opt/tauric-platform-staging/backend/app/services/strategy_orchestrator.py) *(Modified)* — Connected provider implementation status to authoritative `PROVIDER_SCHEMAS`, updated `get_profile_available_capital()` to read unified balance fields and return `NOT TESTED` / `NOT VERIFIED` (`available_capital: None`) when unverified, and implemented 7-point `evaluate_profile_eligibility()`.
8. [`/opt/tauric-platform-staging/backend/app/routes/orchestration.py`](file:///opt/tauric-platform-staging/backend/app/routes/orchestration.py) *(Modified)* — Updated `GET /api/v1/orchestration/profiles/eligible` to return `eligible_profiles`, `ineligible_profiles` (with `eligibility_code` and `eligibility_reason`), and `excluded_test_fixtures_count`; updated `POST /api/v1/orchestration/runs/launch` to support isolated single or multi-profile (`profile_ids`) launches.
9. [`/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx) *(Modified)* — Updated error banner rendering (never showing stale banners when `UNTESTED`, displaying `provider_error_code` and provider-specific guidance), updated Strategy Wizard Step B to use server-side eligibility with multi-profile selection and disabled ineligible profile explanations, and updated Step D to display `NOT VERIFIED` / `NOT TESTED` instead of `$0.00`.
10. [`/opt/tauric-platform-staging/backend/test_phase1_audit_remediation.py`](file:///opt/tauric-platform-staging/backend/test_phase1_audit_remediation.py) *(Created)* — Isolated 14-test regression suite using `tempfile.TemporaryDirectory()`.

---

## 6. Verification Commands, Exit Codes & Test Results

### 6.1 Isolated 14-Test Phase 1 Regression Suite
- **Command:**
  ```bash
  cd /opt/tauric-platform-staging/backend && /opt/tauric-platform-staging/backend/.venv/bin/python3 test_phase1_audit_remediation.py
  ```
- **Exit Code:** `0` (`14/14 PASSED`)
- **Output:**
  ```text
  [PASS] T01: Staging API authentication boundary & OpenAPI docs disabled -> unauth=401 (UNAUTHORIZED_API_REQUEST), health=200, docs=404, openapi=404, auth=200
  [PASS] T02: Transport Security Gate blocks credential submission over plaintext HTTP -> http_status=403 (INSECURE_TRANSPORT_BLOCKED), https_status=200
  [PASS] T03: Binance profile with no passphrase never returns MISSING_PASSPHRASE -> requires_passphrase=False, resolved_code=INVALID_API_KEY
  [PASS] T04: Binance -2015 preserves provider_error_code='-2015' and returns Binance-specific INVALID_API_KEY guidance -> actionable=INVALID_API_KEY, provider_error_code=-2015, guidance=Binance rejected the API key, IP address, or permissions (code -2015). Verify the key matches the selected environment (Demo/Spot Testnet vs Live), has Read Info enabled, and allows this server IP.
  [PASS] T05: Bitget profile without passphrase returns MISSING_PASSPHRASE before making any network request -> status=BLOCKED, actionable=MISSING_PASSPHRASE, network_request_made=False
  [PASS] T06: Bitget profile with passphrase failing with 40099 returns ENVIRONMENT_KEY_MISMATCH (never MISSING_PASSPHRASE) -> resolved_code=ENVIRONMENT_KEY_MISMATCH
  [PASS] T07: Editing a profile clears all stale error codes, guidance, and endpoint_results and resets to UNTESTED -> status=UNTESTED, actionable=None, provider_code=None
  [PASS] T08: Identifying/re-identifying a profile preserves the saved passphrase in the vault -> exchange=BITGET, has_passphrase=True
  [PASS] T09: Strategy Wizard reads unified balance schema (available_balance_usd / asset_balances.available) -> available_capital=1825.5, total_equity=2450.75, display=$1,825.50 USDT
  [PASS] T10: Untested/unverified profiles return available_capital=None and NOT TESTED/NOT VERIFIED (never $0.00) -> verified=False, available_capital=None, display=NOT TESTED
  [PASS] T11: Server-side eligibility & authoritative provider registry reject unverified/unidentified/live-locked/unimplemented profiles with explicit reasons -> eligible=['PAPER', 'prof_conn_f245c0c2'], ineligible_codes={...}, bybit=PLANNED
  [PASS] T12: Multi-profile strategy launch creates independent, isolated runs per profile with separate balances & environments -> runs=[('strat_run_1792838442_16c22ad7', 'PAPER', 'PAPER', 'PAPER', 10000.0), ('strat_run_1792838442_b650121f', 'prof_conn_f245c0c2', 'BITGET', 'DEMO', 1825.5)]
  [PASS] T13: Live order submission endpoint remains hard-locked with HTTP 403 -> status_code=403
  [PASS] T14: Production and staging persistent vaults remain byte-for-byte untouched by isolated test suite -> prod_sha256_match=True, staging_sha256_match=True

  ALL 14/14 PHASE 1 REGRESSION TESTS PASSED!
  ```

### 6.2 Staging Next.js Production Build & Live Proxy Check
- **Build Command:** `cd /opt/tauric-platform-staging/dashboard && npm run build` $\rightarrow$ **Exit Code `0`** (`✓ Compiled successfully`, `✓ Generating static pages (4/4)`).
- **Live Proxy Eligibility Verification (`https://127.0.0.1:33900/trading/api/backend/orchestration/profiles/eligible/`):**
  - Status: `HTTP 200`
  - `excluded_test_fixtures_count`: `39` (all 39 synthetic test profiles in staging excluded without deleting any record)
  - `eligible_profiles`: `[('PAPER', 'Paper Trading Sandbox', '$10,000.00 USD')]`
  - `ineligible_profiles`: `[('prof_bitget_demo_a2bb3478', 'Master', 'BITGET', 'MISSING_PASSPHRASE', 'NOT VERIFIED')]`
