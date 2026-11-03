# TAURIC — Urgent Universal API Management & Connection Repair Report
**Environment:** Staging Only (`/opt/tauric-platform-staging/`)  
**Target Services:** `tauric-backend-staging` (Port 8002, PM2 ID 3) & `tauric-dashboard-staging` (Port 33900, PM2 ID 5)  
**Production Status:** STRICTLY FROZEN & UNTOUCHED (PM2 IDs 0 & 1, Uptime 9h+)  
**Safety Invariants:** `live_trading_locked = true`, `read_only_mode = true`, Real live exchange order submit returns HTTP 403  
**Date:** October 24, 2026  

---

## 1. Executive Summary

This engineering remediation resolved critical API connection, profile management, and dashboard UX defects in the TAURIC platform on staging:
1. **Isolated Provider Authentication Diagnostics:** Diagnosed and separated authentication failure reasons between Binance and Bitget using real staging evidence without exposing plain credentials.
2. **Profile ON/OFF Toggle:** Added profile state toggling to `CredentialVault`, ensuring that turning a profile OFF persists across reloads, updates the UI immediately, and strictly excludes the profile from strategy preflight and downstream execution.
3. **Profile Disconnect / Delete:** Fixed profile deletion end-to-end. Deletion triggers an accessible confirmation dialog explicitly naming the target profile label, removes the profile instantly from UI state, purges encrypted credentials from AES-256-GCM vault storage, and leaves remaining profiles completely unharmed.
4. **Provider-Agnostic Schema Engine:** Bitget mandates API Key, Secret Key, and API Passphrase (`requires_passphrase: true`), whereas Binance strictly requires only API Key and Secret Key (`requires_passphrase: false`), omitting the passphrase field entirely.
5. **Compact Initial Macroeconomic Calendar:** The calendar defaults to a compact, non-intrusive preview showing 3 upcoming events, feed synchronization timestamp, and event horizon scope. An accessible `See more` / `Show less` button expands to the full 14-day schedule and filters without losing state.
6. **13-Point Acceptance Gate:** All 13 independent acceptance criteria passed (`13/13 PASS`).

---

## 2. Root-Cause Analysis: Binance Authentication Failure

### Staging Vault Profile Evidence
- **Profile ID:** `prof_binance_demo_93c40749`
- **Exchange:** `BINANCE`
- **Environment:** `DEMO` (Target: `https://testnet.binance.vision`)
- **Product:** `SPOT`
- **Label:** `Debug Profile 05`

### Diagnostic Test Output
```
[Public Connectivity]
- GET https://testnet.binance.vision/api/v3/ping -> HTTP 200 OK (285ms)
- GET https://testnet.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT -> HTTP 200 OK (265ms, 1,373 symbols discovered)
- GET https://testnet.binance.vision/api/v3/ticker/price?symbol=BTCUSDT -> HTTP 200 OK (238ms, BTCUSDT = $81,304.06)

[Private Account Probe]
- GET https://testnet.binance.vision/api/v3/account
- Raw HTTP Status: 401 Unauthorized
- Raw Provider Error Code: -2014
- Provider Message: {"code": -2014, "msg": "API-key format invalid."}
```

### Root Cause
Decrypted inspection of the stored record in staging vault revealed:
- `api_key`: Length 1 character (`"1"`)
- `api_secret`: Length 1 character (`"1"`)

The profile contained single-character placeholder dummy credentials instead of valid 64-character alphanumeric API credentials. Because Binance public endpoints (`ping`, `exchangeInfo`, `ticker`) succeed without authentication, prior naive tests falsely reported the connection as working. The upgraded diagnostic cleanly decouples public data from private authentication and returns actionable remediation for code `-2014`.

### Actionable Remedy
Generate a legitimate Binance Spot Testnet key pair (64 characters each) at `https://testnet.binance.vision/` and update the profile in the Connections Manager. Do NOT supply a passphrase for Binance.

---

## 3. Root-Cause Analysis: Bitget Authentication Failure

### Staging Vault Profile Evidence
- **Profile ID:** `prof_bitget_demo_a2bb3478`
- **Exchange:** `BITGET`
- **Environment:** `DEMO` (Headers: `paptrading: 1`, Product: `USDT-FUTURES`)
- **Product:** `FUTURES_USDT`
- **Label:** `Master`

### Diagnostic Test Output
```
[Public Connectivity]
- GET https://api.bitget.com/api/v2/public/time -> HTTP 200 OK (370ms, serverTime: 1792783913930)
- GET https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES -> HTTP 200 OK (325ms, 857 contracts discovered)
- GET https://api.bitget.com/api/v2/mix/market/ticker?symbol=BTCUSDT&productType=USDT-FUTURES -> HTTP 200 OK (297ms, BTCUSDT = $81,282.10)

[Private Account Probe]
- GET https://api.bitget.com/api/v2/mix/account/accounts?productType=USDT-FUTURES
- Raw HTTP Status: 400 Bad Request
- Raw Provider Error Code: 40099
- Provider Message: {"code": "40099", "msg": "exchange environment is incorrect"}
```

### Root Cause
Two concurrent issues were verified from the encrypted vault record:
1. **Passphrase Missing:** The vault record stored `_credentials_enc` with an empty string for the API Passphrase (`Length: 0`). Bitget API v2 strictly requires `ACCESS-PASSPHRASE` in all signed private requests.
2. **Environment Mismatch (Code `40099`):** The API key `bg_b...4881` was generated on Bitget Production (Live), but the profile was configured for Bitget Demo Futures (`paptrading: 1`). Bitget returns `40099 exchange environment is incorrect` when a Live API key is presented with demo paper-trading headers.

### Actionable Remedy
1. For **Bitget Demo Trading:** Use a dedicated Bitget Demo API Key, Secret, and Passphrase generated under Bitget Demo/Simulation Trading.
2. For **Bitget Live Trading:** Switch the profile environment to `LIVE`, whitelist the Germany VPS egress IP (`169.58.218.168`), and enter the Key, Secret, and mandatory Passphrase.

---

## 4. Profile ON/OFF Toggle Verification

- **Backend Persistence:** `CredentialVault.toggle_active(profile_id, is_active)` persists the boolean flag directly to disk (`vault_encrypted.json`).
- **Endpoint:** `POST /api/v1/connections/profiles/{profile_id}/toggle-active/`
- **Strategy Preflight Exclusion:** When a profile is toggled `OFF`:
  - `strategy_preflight` returns `status: "BLOCKED"`, `eligible: false`, and attaches blocker: `"Connection profile '[label]' is disabled (OFF)."`.
  - The preflight check confirms: `"Profile '[label]' is toggled OFF (Inactive). Disabled profiles cannot execute strategies."`.
  - Frontend execution dropdown immediately excludes `is_active === false` profiles from candidate selection.
- **Independence:** Flipping profile `prof_binance_demo_93c40749` between `ON` and `OFF` has zero effect on `prof_bitget_demo_a2bb3478` or any other configured profile.

---

## 5. Profile Disconnect / Delete Verification

- **Confirmation Dialog:** Clicking "Disconnect API" prompts the user with:
  `Are you sure you want to disconnect and delete connection profile "[Profile Label]"? This will permanently purge its credentials from the vault.`
- **Instant UI Removal:** The component optimistically filters out the target profile from `connections` state and clears any open diagnostic or preflight selection modal referencing the deleted profile.
- **Vault Storage Purge:** `DELETE /api/v1/connections/profiles/{profile_id}/` deletes the record from `self._profiles` in `CredentialVault` and writes the updated dictionary to disk.
- **Preservation of Remaining Profiles:** Automated test created temporary profile `prof_binance_demo_a96de9d6`, verified its presence, issued `DELETE`, verified permanent removal from disk, and proved that existing Binance and Bitget profiles remained intact.

---

## 6. Provider Schema Separation

| Attribute | Binance Schema | Bitget Schema |
| :--- | :--- | :--- |
| **Provider ID** | `BINANCE` | `BITGET` |
| **Auth Signing** | `HMAC_SHA256_HEX` | `HMAC_SHA256_BASE64` |
| **Sign Placement** | Query parameter (`signature=...`) | HTTP Header (`ACCESS-SIGN`) |
| **Key Header** | `X-MBX-APIKEY` | `ACCESS-KEY` |
| **Timestamp Header** | `timestamp` query parameter | `ACCESS-TIMESTAMP` header |
| **Requires Passphrase** | **`false`** | **`true`** |
| **Passphrase Header** | None (Omitted) | `ACCESS-PASSPHRASE` |
| **Credential Fields** | `api_key` (Required), `api_secret` (Required) | `api_key` (Required), `api_secret` (Required), `passphrase` (Required) |

---

## 7. Compact Initial Macroeconomic Calendar UX

- **Initial State:** `isCalendarExpanded` is initialized to `false` (`useState<boolean>(false)`).
- **Default Preview:** Displays a compact 3-item grid (`events.slice(0, 3)`) featuring country/currency badges, event titles, scheduled time in PKT/UTC, and consensus/prior figures.
- **Controls:** Features an accessible `<button>` equipped with:
  - `aria-expanded={isCalendarExpanded}`
  - `aria-controls="macroeconomic-calendar-content"`
  - Dynamic label toggling between `"See more"` (when collapsed) and `"Show less"` (when expanded).
- **Expansion Container:** `<div id="macroeconomic-calendar-content">` expands to reveal the full country filter bar and comprehensive 14-day schedule without causing page layout shifts.

---

## 8. Full 13-Point Acceptance Test Matrix

| # | Acceptance Test Item | Result | Evidence / Details |
| :---: | :--- | :---: | :--- |
| **1** | Binance public connectivity (ping / exchangeInfo / ticker) | **PASS** | HTTP 200 OK. 1,373 symbols discovered. BTCUSDT = $81,253.40. |
| **2** | Binance private check runs only against chosen environment | **PASS** | Targets `https://testnet.binance.vision/api/v3/account` when DEMO. Zero environment swapping. |
| **3** | Binance diagnostic reports exact provider error & remediation | **PASS** | Raw code `-2014`. Actionable remediation returned in `capability_matrix`. |
| **4** | Bitget public connectivity (time / contracts / ticker) | **PASS** | HTTP 200 OK. 857 contracts discovered. BTCUSDT = $81,237.40. |
| **5** | Bitget private check runs only against chosen env & product | **PASS** | Targets `USDT-FUTURES` with `paptrading: 1`. Zero silent fallback. |
| **6** | Bitget diagnostic reports exact provider error & remediation | **PASS** | Raw code `40099`. Actionable remediation returned in `capability_matrix`. |
| **7** | Bitget passphrase is required by schema & Binance omits it | **PASS** | Bitget `requires_passphrase: true`. Binance `requires_passphrase: false`. |
| **8** | Profile OFF persists across reload & excludes from preflight | **PASS** | Persisted `is_active: false`. Strategy preflight status `BLOCKED`. |
| **9** | Profile ON makes profile eligible for strategy preflight | **PASS** | Persisted `is_active: true`. Profile active check `PASSED (INFO)`. |
| **10** | Toggling one profile does not affect state of another | **PASS** | Binance toggled OFF/ON while Bitget remained ON throughout. |
| **11** | Disconnect / delete removes permanently from vault & UI | **PASS** | Test profile purged from vault JSON; remaining profiles intact. |
| **12** | Calendar preview displays 2–3 items with See more / Show less | **PASS** | Initial state collapsed; displays 3 items; accessible ARIA attributes verified. |
| **13** | Live trading remains locked (HTTP 403 on live order submit) | **PASS** | `POST /orders/live/submit` returned HTTP 403 Forbidden. Safe invariant enforced. |

**Final Score:** **13 / 13 PASSED (100%)**

---

## 9. Recommended User Procedure for Connecting Keys

### A. For Binance
1. Navigate to **Connections Manager** in the Tauric dashboard.
2. Select **Add Connection** -> Exchange: **BINANCE**.
3. Choose Environment:
   - For **DEMO / Paper Trading:** Choose `DEMO`. Generate a 64-character testnet key pair at [testnet.binance.vision](https://testnet.binance.vision/).
   - For **LIVE Trading Mode:** Choose `LIVE`. Generate read-only API keys in Binance Production API Management with Germany VPS egress IP (`169.58.218.168`) whitelisted.
4. Paste `API Key` and `API Secret`. (Passphrase field is intentionally omitted).
5. Click **Save & Test Connection**.

### B. For Bitget
1. In **Connections Manager**, select **Add Connection** -> Exchange: **BITGET**.
2. Product Type: **USDT-M Futures**.
3. Choose Environment:
   - For **DEMO:** Select `DEMO`. Provide a Bitget Demo key pair and passphrase.
   - For **LIVE:** Select `LIVE`. Enter your live Bitget API Key, Secret, and the passphrase chosen during key generation. Whitelist egress IP `169.58.218.168`.
4. Click **Save & Test Connection**.

---

## 10. Operational Boundary & Safety Declaration

- **Production State:** Production (`/opt/tauric-platform/`, PM2 ID 0 and 1) is completely untouched and was never restarted or modified.
- **Live Trading Lock:** Platform live trading execution is unconditionally locked (`live_trading_locked = true`, `read_only_mode = true`). Real live order submissions return HTTP 403. Zero live exchange orders were placed.
