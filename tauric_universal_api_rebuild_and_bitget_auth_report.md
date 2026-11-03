# TAURIC — Universal API Connection Manager Rebuild & Bitget Authentication Report

**Environment:** Staging Only (`/opt/tauric-platform-staging/`)  
**Staging Dashboard URL:** `https://bybit-gateway.sheltr.agency:33900/trading/`  
**Staging Backend URL:** `http://127.0.0.1:8002`  
**Production Status:** Untouched (`/opt/tauric-platform/`, PM2 processes `0` and `1` unmodified, 13h+ continuous uptime)

---

## 1. Executive Summary & Root Cause: Why the Old Add-Connection Wizard Was Still Visible

Headless Chrome (`puppeteer-core`) and server routing inspection identified two distinct reasons why the old multi-step wizard appeared:

1. **Port 443 (Production) vs. Port 33900 (Staging) Routing:**
   - The default HTTPS domain `https://bybit-gateway.sheltr.agency/trading/` (port `443`) is proxied by Nginx (`/etc/nginx/sites-enabled/tauric-portal.conf`) to `127.0.0.1:8080`, which serves the **frozen production** dashboard (`/opt/tauric-platform/dashboard`, bundle `page-989a7757165383ee.js`) and production backend (`127.0.0.1:8001`). Because production is frozen by safety policy, port `443` continues to render the legacy 5-step wizard (`1 SELECT ASSET MARKET CATEGORY`, `2 SELECT CRYPTO PROVIDER / BROKER`, `P PRODUCT / ACCOUNT CATEGORY`, `3 ACCOUNT ENVIRONMENT`, `4 INTENDED API PERMISSIONS`, `5 ENTER CONNECTION CREDENTIALS`).
   - The **staging** HTTPS server runs on port `33900` (`https://bybit-gateway.sheltr.agency:33900/trading/`) via `/opt/tauric-platform-staging/dashboard/server.js`, proxying `/trading/api/backend/*` to `http://127.0.0.1:8002`.

2. **Residual Provider Selector & `newConn` Wizard State in Staging (`UnifiedSignalDashboard.tsx`):**
   - Even on staging port `33900`, the previous iteration had only partially simplified the form: it left `1. Exchange Provider * Required` (`<select>` with 8 hardcoded options including unimplemented brokers) on the initial Add API screen and retained the 25-field `newConn` wizard state (`marketType`, `productType`, `environment`, `intendedPermissions`, `buildCustomConfig`, `getEffectiveExchange`) inside `/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx`.

---

## 2. Files Backed Up & Modified (Staging Only)

All affected staging files were backed up prior to modification in `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/`:
- `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/credential_vault.json.bak`
- `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/exchange_framework.py.bak`
- `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/connections.py.bak`
- `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/UnifiedSignalDashboard.tsx.bak`

### Modified Staging Files
1. **`/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx`**
   - Removed the 25-field `newConn` wizard state, `getEffectiveExchange()`, and `buildCustomConfig()` completely (`0` references remaining).
   - Replaced the initial Add API form (`[data-testid="universal-add-api-form"]`) with a strict 4-field credential-first form:
     1. **Connection name** *(Optional, e.g. `Bitget API 1`)*
     2. **API Key** *(`* Required`)*
     3. **API Secret** *(`* Required`)*
     4. **API Passphrase** *(Shown when required by the connection type, e.g. Bitget)*
   - Zero `<select>` dropdowns on the initial Add API screen; no asset category, Spot/Futures, Demo/Live, coin, strategy, capital, or permission checkboxes.
   - Replaced the saved profile cards and built the dedicated post-save **Permissions & Capabilities** modal (`[data-testid="permissions-capabilities-modal"]`).

2. **`/opt/tauric-platform-staging/backend/app/services/exchange_framework.py`**
   - Added `implemented_provider_ids()` returning only providers with `implementation_status == "IMPLEMENTED_TESTED"` (`["BINANCE", "BITGET"]`).
   - Added `suggest_provider(api_key, passphrase)` for non-binding format hints (`bg_` prefix $\rightarrow$ `BITGET`, 64-char alphanumeric without passphrase $\rightarrow$ `BINANCE`).
   - Added `CredentialVault.save_unidentified_profile()`, `CredentialVault.identify_profile()`, and `CredentialVault.configure_profile()` with AES-256-GCM AAD rebinding (`{profile_id}:{exchange}:{environment}`).
   - Fixed capability evidence reporting via `_auth_cap(endpoints_results, auth_ok)` so preflight blocks (such as `MISSING_PASSPHRASE` where no HTTP call is sent) report `ACCOUNT_AUTH` as `NOT_TESTED` (`"Blocked before any network request: ..."`) instead of falsely reporting `"Exchange rejected signature, API key, or passphrase."`

3. **`/opt/tauric-platform-staging/backend/app/routes/connections.py`**
   - Added `GET /api/v1/connections/providers-implemented` (returns only `BITGET` and `BINANCE`).
   - Added `POST /api/v1/connections/universal` (credential-first profile creation).
   - Added `POST /api/v1/connections/profiles/{profile_id}/identify` (explicit post-save provider identification restricted to implemented & tested adapters).
   - Added `POST /api/v1/connections/profiles/{profile_id}/configure` (explicit post-save environment & product configuration with Bitget Spot Demo rejection).
   - Added `GET /api/v1/connections/profiles/{profile_id}/capability-report` (segregated Public Market Data vs. Private Account Authentication states and truthful capability indicators).

---

## 3. Real Browser Verification Evidence (`puppeteer-core` Headless Chrome)

After running `npm run build` in `/opt/tauric-platform-staging/dashboard` and restarting only `tauric-backend-staging` (PM2 id `3`) and `tauric-dashboard-staging` (PM2 id `5`), headless Chrome navigated to `https://bybit-gateway.sheltr.agency:33900/trading/`, opened the Universal API Connections modal, and audited the live rendered DOM:

```json
{
  "found": true,
  "labels": [
    "Connection name (Optional)",
    "API Key * Required",
    "API Secret * Required",
    "API Passphrase (When required by connection type, e.g. Bitget)"
  ],
  "inputs": [
    { "type": "text", "placeholder": "e.g. Bitget API 1" },
    { "type": "text", "placeholder": "Enter API Key" },
    { "type": "password", "placeholder": "Enter API Secret" },
    { "type": "password", "placeholder": "Enter API Passphrase (required for Bitget; leave blank for Binance)" }
  ],
  "selectsInAddForm": 0,
  "hasAssetCategory": false,
  "hasSelectProvider": false,
  "hasProductCategory": false,
  "hasEnvironmentQuestion": false,
  "hasIntendedPermissions": false,
  "hasSavedMasterCard": true
}
```

````carousel
![Rebuilt 4-Field Universal Add API Screen on Staging (Port 33900)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/staging_rebuilt_add_api.png)
<!-- slide -->
![Post-Save Permissions & Capabilities Modal for Bitget "Master" Profile](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/staging_rebuilt_capabilities_modal.png)
````

---

## 4. Saved Profile Management & Post-Save Permissions & Capabilities Verification

Each saved profile card in the Universal API Connection Manager displays:
- **Connection Name** (e.g., `Master`)
- **Identified Provider Badge** (`BITGET` / `BINANCE`, or `UNIDENTIFIED PROVIDER` with non-binding format hint and post-save `Identify as Bitget` / `Identify as Binance` buttons)
- **Passphrase Presence Indicator** for Bitget profiles (`Present (Encrypted)` vs. `Missing — Click Edit to enter passphrase`)
- **Enabled / Disabled Toggle** (`ON` / `OFF`, persisted server-side and enforced by strategy preflight)
- **Test Connection** button
- **Permissions & Capabilities** button (opens the post-save modal)
- **Edit** and **Delete** buttons

### Post-Save Permissions & Capabilities Panel (`GET /api/v1/connections/profiles/{id}/capability-report`)
Inside the post-save modal, capabilities are reported with truthful states (`VERIFIED`, `FAILED`, `UNSUPPORTED`, `NOT TESTED`, and `DISABLED` for withdrawals):
1. **Public market data:** `VERIFIED` (when public ping/contracts/ticker probes return HTTP 200)
2. **Private account authentication:** `VERIFIED` / `FAILED` / `NOT TESTED`
3. **Account / profile read:** `VERIFIED` / `FAILED` / `NOT TESTED`
4. **Balance read:** `VERIFIED` / `FAILED` / `UNSUPPORTED` / `NOT TESTED`
5. **Open orders read:** `VERIFIED` / `FAILED` / `NOT TESTED`
6. **Order history read:** `VERIFIED` / `FAILED` / `NOT TESTED`
7. **Position / exposure read:** `VERIFIED` / `FAILED` / `NOT TESTED`
8. **Order placement, cancellation, and modification:** `NOT TESTED` (never exercised during read-only discovery; live order submission remains hard-locked at HTTP 403)
9. **Withdrawal / transfer:** `DISABLED` (permanently unavailable to the bot)

---

## 5. Sanitized Bitget Private Authentication Trace (`prof_bitget_demo_a2bb3478` — "Master")

All 8 diagnostic points from Section E were verified against the live staging vault and runtime adapter (`CustomExchangeAdapter` in `exchange_framework.py`):

| # | Check | Finding / Evidence |
|---|---|---|
| 1 | **Is a non-empty passphrase genuinely saved?** | **No (`has_passphrase: False`).** In `/opt/tauric-platform-staging/backend/data/credential_vault.json`, `prof_bitget_demo_a2bb3478` has `api_key` present (length 35, prefix `bg_`), `api_secret` present (non-empty), and `passphrase: ""` (length 0). |
| 2 | **Does the profile decrypt intact using the staging vault key?** | **Yes.** `prof_bitget_demo_a2bb3478` decrypts cleanly with the staging `.env` `TAURIC_VAULT_KEY` and AES-256-GCM AAD `prof_bitget_demo_a2bb3478:BITGET:DEMO`. |
| 3 | **Configured environment & product** | `exchange: "BITGET"`, `environment: "DEMO"`, `product_type: "FUTURES_USDT"`, `is_active: True`. |
| 4 | **Adapter endpoint, query params, demo header & signing** | `resolve_bitget_endpoints_and_params("DEMO", "FUTURES_USDT")` resolves `productType=SUSDT-FUTURES`, symbol `SBTCSUSDT`, demo header `paptrading: "1"`, account path `/api/v2/mix/account/accounts?productType=SUSDT-FUTURES`, and signs `timestamp + "GET" + "/api/v2/mix/account/accounts" + "?productType=SUSDT-FUTURES"` with HMAC-SHA256 Base64 (`ACCESS-KEY`, `ACCESS-SIGN`, `ACCESS-TIMESTAMP`, `ACCESS-PASSPHRASE`). |
| 5 | **Server UTC clock synchronization** | `timedatectl status` confirms `System clock synchronized: yes`, `NTP service: active`. |
| 6 | **Public vs. Private Probe Execution** | Public probes (`GET /api/v2/public/time`, `GET /api/v2/mix/market/contracts?productType=SUSDT-FUTURES`, `GET /api/v2/mix/market/ticker?symbol=SBTCSUSDT&productType=SUSDT-FUTURES`) all succeed with **HTTP 200** (`code: "00000"`). Private probe (`GET /api/v2/mix/account/accounts?productType=SUSDT-FUTURES`) is **blocked at local preflight** before any network call because `passphrase` is `""`, returning `actionable_error_code: "MISSING_PASSPHRASE"`. |
| 7 | **Misleading Capability Evidence Fixed** | Previously, when preflight blocked due to `MISSING_PASSPHRASE`, `detect_account_capabilities` still set `ACCOUNT_AUTH` evidence to `"Exchange rejected signature, API key, or passphrase."` even though no network call was made. Fixed via `_auth_cap()` so `ACCOUNT_AUTH` now reports state `NOT TESTED` with evidence `"Blocked before any network request: Authentication request failed: Bitget requires a non-empty API passphrase. Preflight failed: no network request performed."` |
| 8 | **How to Complete Bitget Authentication on `Master`** | Click **Edit** on the `Master` card in the staging UI (`https://bybit-gateway.sheltr.agency:33900/trading/`), leave `API Key` and `API Secret` blank (preserving the existing encrypted key and secret byte-for-byte), enter the Bitget API Passphrase into `API Passphrase`, click **Update Connection**, and click **Test Connection**. |

---

## 6. Staging Vault Provenance Audit & Test Isolation (Section G)

### Test Vault Isolation Implemented
All 4 automated test scripts (`test_claude_audit_repairs.py`, `test_add_api_ux_and_bitget_auth.py`, `run_api_management_13_point_tests.py`, `test_universal_strategy_orchestration.py`) and the new `test_universal_api_rebuild.py` now set `os.environ["TAURIC_VAULT_PATH"]` to an isolated `/tmp/*.json` file before importing backend modules. Running all test suites (`20/20` in `test_universal_api_rebuild.py`, `12/12` in `test_claude_audit_repairs.py`, and `7/7` in `test_add_api_ux_and_bitget_auth.py` — **39/39 checks passed**) added **0** profiles to `/opt/tauric-platform-staging/backend/data/credential_vault.json`.

### Provenance Classification of the 40 Existing Staging Vault Profiles
A full backup of the 40-profile vault is saved at `/opt/tauric-platform-staging/backups/rebuild_20261023T233606Z/credential_vault.json.bak`.

#### A. Pre-Existing / User Profiles (4 Profiles — Keep)
| Profile ID | Provider | Label | Env | Created (UTC) | Notes |
|---|---|---|---|---|---|
| `prof_bitget_demo_a2bb3478` | `BITGET` | `Master` | `DEMO` | `2026-10-23T11:46:29Z` | User's primary Bitget profile (`bg_b••••••••4881`) |
| `prof_binance_demo_93c40749` | `BINANCE` | `Debug Profile 05` | `DEMO` | `2026-10-22T19:16:12Z` | Pre-existing Binance Testnet profile |
| `prof_bybit_demo_6fc24d01` | `BYBIT` | `Test Bybit Account` | `DEMO` | `2026-10-21T21:20:50Z` | Pre-existing Oct 21 profile |
| `prof_coinbase_demo_ed2f9954` | `COINBASE` | `Audit Coinbase Profile` | `DEMO` | `2026-10-21T22:05:51Z` | Pre-existing Oct 21 profile |

#### B. Automated Test-Fixture Profiles Created During Oct 23 Test Suites (36 Profiles — Candidates for Cleanup Upon Your Approval)
- **Created by `test_claude_audit_repairs.py` & `test_add_api_ux_and_bitget_auth.py` (18 profiles):**
  - `prof_binance_demo_248d0487`, `prof_binance_demo_c9b527f5`, `prof_binance_demo_ef8bd4f4`, `prof_binance_demo_85d7e041` (`Dependent Profile Test`)
  - `prof_bitget_demo_26e22c51`, `prof_bitget_demo_db0af4a5`, `prof_bitget_demo_405aa85f`, `prof_bitget_demo_cb444cf1` (`Retest Override Invariant Test`)
  - `prof_bitget_live_e5a8d1fc`, `prof_bitget_live_38d97c2f`, `prof_bitget_live_f4daacbe`, `prof_bitget_live_ef9ca96e` (`Renamed Profile Label After Edit`)
  - `prof_bybit_live_b8ba10c2`, `prof_bybit_live_457cb015`, `prof_bybit_live_8487da42`, `prof_bybit_live_d1484cf0` (`Collision Prevention Test`)
  - `prof_bitget_demo_ff926707`, `prof_bitget_demo_ef4ff24a` (`Updated Label Via UI Edit`)
- **Created by `test_universal_strategy_orchestration.py` (9 profiles):**
  - `prof_binance_demo_6d4e07bd`, `prof_binance_demo_f4c65fb2`, `prof_binance_demo_e09278fd` (`Binance Spot Strategy Alpha`)
  - `prof_binance_demo_e7c858b2`, `prof_binance_demo_44a75df5`, `prof_binance_demo_a21e78d5` (`Binance Spot Strategy Beta`)
  - `prof_binance_live_dbda4969`, `prof_binance_live_22a85f79`, `prof_binance_live_e4083e2b` (`Binance Live Institutional`)
- **Created by `run_api_management_13_point_tests.py` (9 profiles):**
  - `prof_binance_demo_9911de0a`, `prof_binance_demo_3203d00e`, `prof_binance_demo_65f17c14`, `prof_binance_demo_e4e44303` (`Automated Deletion Test Profile` / `Del Test Temp` / `Test Delete Now`)
  - `prof_bitget_demo_36be341b`, `prof_bitget_demo_a9da39a3` (`Bitget API 1` dummy test fixtures with key `bg_valid_key...`)
  - `prof_bybit_demo_e6087857`, `prof_bybit_demo_b4b71a13` (`Bybit Unified Demo` dummy test fixtures)
  - `prof_mt5_demo_f7f78042` (`ICMarkets Demo MT5` dummy test fixture)

> [!IMPORTANT]
> **Action Required for Vault Cleanup:** None of the 36 test-fixture profiles above have been deleted yet. Please confirm if you approve removing those 36 automated test-fixture profiles from `/opt/tauric-platform-staging/backend/data/credential_vault.json` so only your saved profiles remain.

---

## 7. Safety & Production Boundary Confirmation

- **Production Untouched:** `/opt/tauric-platform/` was not modified, rebuilt, or restarted (`tauric-backend` PM2 id `0` and `tauric-dashboard` PM2 id `1` untouched).
- **Live Trading Hard-Locked:** `POST http://127.0.0.1:8002/api/v1/orders/live/submit` verified returning **HTTP 403** (`live_trading_locked=true`, `read_only_mode=true`).
- **Zero Order Execution or Withdrawals:** No real orders were placed, amended, or cancelled; withdrawal capabilities remain permanently `DISABLED`.
