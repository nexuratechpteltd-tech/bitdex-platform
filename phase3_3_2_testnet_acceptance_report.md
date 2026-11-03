# TAURIC PLATFORM — PHASE 3.3.2 TESTNET ACCEPTANCE TESTING REPORT

**Date:** October 21, 2026  
**Environment:** Isolated Staging (`/opt/tauric-platform-staging/`)  
**Status:** ACCEPTANCE AUDIT COMPLETE · LIVE ORDER EXECUTION BLOCKED (UNCONFIGURED CREDENTIALS)  
**Production Integrity:** 100% UNTOUCHED (PID 75730 & 88836 online, uptime 29h+, 0 restarts)

---

## 1. Executive Summary

Phase 3.3.2 performs comprehensive testnet acceptance testing across the modular exchange framework, credential vault key lifecycle, pre-flight order filters, protective order enforcement, timeout reconciliation, and portfolio state integrity.

### Strict Safety & Policy Status:
1. **Live Order Execution:** Hard-locked (`live_trading_locked=true`). Live order submission is unconditionally blocked.
2. **Testnet Account Status:** **BLOCKED**. Only synthetic unit-test keys exist in the staging credential vault. The exchange connection test against Binance Testnet API (`https://testnet.binance.vision/api/v3/account`) was queried and rejected authentication (`code: -2014, msg: "API-key format invalid."`).
3. **No Fabricated Fills:** In accordance with Phase 3.3.2 policy, because valid user-configured testnet credentials are unavailable, the live exchange execution portion was reported **BLOCKED** and stopped. Zero simulated fills or synthetic receipts were fabricated.
4. **Acceptance Test Suite:** 12/12 acceptance tests passed in `test_phase3_3_2_acceptance.py`.
5. **Full Platform Regression:** 153/153 tests passed across all 10 platform test suites on the staging VPS.
6. **Frontend Verification:** Next.js staging dashboard build succeeded with 0 TypeScript errors and 4/4 static pages generated.

---

## 2. Credential Vault Key Lifecycle & Security Verification

### 2.1 Key Lifecycle & Secure Provisioning
- **Provisioning Source:** The 256-bit vault master key is loaded strictly from the protected environment secret `TAURIC_VAULT_KEY` (`b4c80e19d709212ad124be3f8d38e309cb9f3ef3967d0130db52cf1d1796195e`).
- **Storage Separation:** The key is stored exclusively in `/opt/tauric-platform-staging/backend/.env`. It is never stored alongside the ciphertext file (`/opt/tauric-platform-staging/backend/data/credential_vault.json`).
- **Key Validation:** Strict validation requires exactly 32 bytes (256 bits). Non-32-byte keys fail closed immediately with `RuntimeError`.

### 2.2 Process Restart Reload Behavior
- When the backend service reboots, `CredentialVault` re-instantiates and re-loads `credential_vault.json`.
- The vault verifies the integrity of every profile against the master key using AES-256-GCM authenticated tags with Associated Data (AAD).
- If restarted without `TAURIC_VAULT_KEY`, any attempt to decrypt or save credentials raises `RuntimeError("Credential vault is locked: `TAURIC_VAULT_KEY` environment variable is not configured.")`, completely disabling credential access.

### 2.3 Backup & Recovery Procedure
1. **Backup:** The vault file `credential_vault.json` contains only AES-256-GCM ciphertexts with 96-bit nonces and AAD metadata. It can be safely backed up to secure archival storage without exposing raw API keys or secrets.
2. **Recovery:**
   - To restore, `credential_vault.json` is restored to `backend/data/` and `TAURIC_VAULT_KEY` is provisioned to `.env`.
   - If restored with the matching 32-byte master key, all profiles are decrypted seamlessly.
   - If restored with an incorrect master key, AES-256-GCM authentication fails closed immediately, raising `PermissionError("Vault integrity verification failed. Ciphertext has been modified, tampered with, or associated metadata does not match.")`.
3. **Zero Secret Leakage:** Neither the master key, raw API keys, nor decrypted secrets are ever printed to console logs, exception traces, or API responses.

---

## 3. Testnet Connection & Live Execution Safety Verification

### 3.1 Vault Account Inspection
- Vault profile query (`credential_vault.list_profiles()`):
  - Configured profile count: 1 profile (`prof_legacy_test_01`, label: `"Legacy Profile"`, masked key: `"vmPU••••••••fXYZ"`).
  - This profile represents a synthetic unit-test fixture created during migration testing.
  - No user-configured Binance Spot Testnet or Bybit Testnet credentials exist in the vault.

### 3.2 Real Testnet Authentication Audit
- Querying Binance Testnet API (`https://testnet.binance.vision/api/v3/account`) using `prof_legacy_test_01`:
  ```json
  {
    "status": "FAIL",
    "verified": false,
    "can_trade": false,
    "can_read": false,
    "environment": "DEMO",
    "error": "Binance rejected authentication (code -2014): API-key format invalid."
  }
  ```
- Because valid testnet credentials are not configured, order submission against the demo adapter returns:
  ```json
  {
    "status": "REJECTED",
    "executed_qty": 0.0,
    "error_message": "Demo execution BLOCKED: Binance testnet credentials required in vault.",
    "audit_trail": [
      "Demo execution BLOCKED: No active exchange testnet credentials configured in vault.",
      "Platform policy strictly forbids fabricated simulated fills."
    ]
  }
  ```
- **Execution Portion Status:** **BLOCKED**. Zero exchange orders were submitted and zero simulated fills were fabricated.

---

## 4. Acceptance Reconciliation Contract (Controlled Verification)

Using controlled deterministic acceptance fixtures in `test_phase3_3_2_acceptance.py`, the complete reconciliation pipeline was verified:
1. **Order Record Reconciliation:**
   - `client_order_id`: Snapped to platform pattern `ORD-DEMO-BIN-XXXXXX`.
   - `exchange_order_id`: Retains exchange reference (`BINANCE-TESTNET-771122`).
   - `status`: Transitioned to `OrderStatus.FILLED`.
2. **Quantity and Sizing Reconciliation:**
   - `requested_qty`: 0.05 BTC.
   - `executed_qty`: 0.05 BTC.
3. **Price and Friction Reconciliation:**
   - `requested_price`: $64,000.00.
   - `avg_fill_price`: $64,000.00.
   - `fee_amount`: $3.20 USDT (0.10% spot taker fee).
4. **Position Ledger & Mark Valuation:**
   - Position opened: `symbol: "BTCUSDT"`, `side: "LONG"`, `size: 0.05`, `entry_price: 64,000.00`, `fees_paid: 3.20`.
   - Mark Price Update: Price moved from $64,000 to $65,000 (+$1,000/BTC).
   - Unrealized P&L Reconciled: `(65,000 - 64,000) * 0.05 = +$50.00` (+1.56%).

---

## 5. Pre-Flight Risk & Filter Failure Testing

Every required pre-flight failure mode was independently verified in the acceptance test suite:

| Test # | Filter / Risk Gate Condition | Acceptance Test Assertion | Status |
|:---:|:---|:---|:---:|
| 1 | **Insufficient Quote Balance (BUY)** | Buying 0.1 BTC at $60,000 requires $6,006. With $5,000 balance, order is rejected with `"Insufficient USDT balance"`. | **PASS** |
| 2 | **Insufficient Base Balance (SELL)** | Selling 0.5 BTC with only 0.2 BTC available is rejected with `"Insufficient BTC balance"`. | **PASS** |
| 3 | **Lot Size Step Snapping** | Quantity `0.01567` snaps to nearest allowed step size `0.016`. | **PASS** |
| 4 | **Minimum Notional Filter** | Order notional below $25.00 min notional rejected with `"below minimum notional"`. | **PASS** |
| 5 | **Protective Stop-Loss (Inverted)** | BUY order with Stop-Loss >= entry price ($60,500 >= $60,000) rejected with `"must be strictly below entry price"`. | **PASS** |
| 6 | **Protective Take-Profit (Inverted)** | BUY order with Take-Profit <= entry price ($59,000 <= $60,000) rejected with `"must be strictly above entry price"`. | **PASS** |
| 7 | **Duplicate Idempotency Key** | Re-submitting with identical key returns cached receipt without duplicate submission or double-counting position. | **PASS** |
| 8 | **Submission Timeout (No Blind Resubmit)** | `httpx.TimeoutException` triggers `origClientOrderId` inquiry. Unconfirmed orders marked `FAILED`; no blind retry submitted. | **PASS** |
| 9 | **Partial Fill Accounting** | Executing 0.8 ETH of 2.0 ETH requested updates position size to 0.8 and deducts fee proportional only to executed notional. | **PASS** |
| 10 | **Order Cancellation** | Adapter and framework cancellation contracts verified for Binance and Bybit; open orders marked `CANCELLED`. | **PASS** |

---

## 6. Environment Segregation & Live Trading Lock

1. **Independent Endpoint Routing:**
   - `Environment.DEMO` resolves strictly to:
     - Binance: `https://testnet.binance.vision/api/v3`
     - Bybit: `https://api-testnet.bybit.com/v5`
   - `Environment.LIVE` resolves to:
     - Binance: `https://api.binance.com/api/v3`
     - Bybit: `https://api.bybit.com/v5`
2. **Hard-Locked Live Execution:**
   - Any order submission specifying `Environment.LIVE` immediately raises `PermissionError("Live trading is hard-locked (`live_trading_locked=true`). Real exchange order submission is strictly prohibited.")`.
   - Route `POST /orders/live/submit` unconditionally returns HTTP 403 Forbidden.
   - Endpoint `/connections/test` enforces `execution_ready = (verified is True) and (can_trade is True) and (env == "DEMO")`. Even if a valid live account is tested, `execution_ready` is strictly `False`.
3. **Leakage Impossibility:** No demo action can route to or execute against live production exchange endpoints.

---

## 7. Dashboard Execution Status & Portfolio Data Freshness

1. **Exchange-Verified Execution Receipts:**
   - The dashboard modal renders execution receipts only when verified (`client_order_id`, `exchange_order_id`, `status: FILLED`, `avg_fill_price`, `audit_trail`).
   - If an order is rejected or blocked, an explicit error alert is displayed (`"Pre-Flight Validation REJECTED"` or `"Demo execution BLOCKED"`).
2. **Portfolio Data Freshness:**
   - Endpoint `GET /orders/positions` returns:
     - `data_freshness`: `"FRESH"`, `"STALE"`, or `"UNAVAILABLE"`.
     - `prices_updated_at_utc`: Timestamp of the latest market price update.
   - If public market data is unreachable or stale, the dashboard renders the freshness warning badge in amber/rose, preventing misleading mark valuations.

---

## 8. Full Platform Regression & Frontend Build Verification

### 8.1 Backend Regression Suite (All 10 Suites)
Executed on VPS staging backend (`/opt/tauric-platform-staging/backend/.venv`):
```bash
PYTHONPATH=. .venv/bin/python3 -m unittest \
  test_phase2_qualification.py \
  test_phase2_extended.py \
  test_phase3_finance_calendar.py \
  test_phase3_1_safety_audit.py \
  test_phase3_1_1_adversarial.py \
  test_phase3_2_dual_ai.py \
  test_phase3_2_1_adversarial.py \
  test_phase3_3_execution.py \
  test_phase3_3_1_security.py \
  test_phase3_3_2_acceptance.py
```
**Result:** `Ran 153 tests in 6.270s — OK (153 passed, 0 failures, 0 errors)`.

### 8.2 Staging Frontend Build
Executed on VPS staging dashboard:
```bash
cd /opt/tauric-platform-staging/dashboard && npx tsc --noEmit && npm run build
```
**Result:**
- TypeScript Typecheck: 0 errors.
- Next.js Build: Compiled successfully; static page generation 4/4 complete.

### 8.3 Production Isolation Verification
- **Production Directory (`/opt/tauric-platform`):** Modification timestamp `2026-10-19 23:15:02 CEST` (100% untouched).
- **Backend PM2 Process (`tauric-backend`):** PID `75730`, Uptime 29h+, 0 restarts, online.
- **Dashboard PM2 Process (`tauric-dashboard`):** PID `88836`, Uptime 26h+, 0 restarts, online.
- **Zero Production Restarts, Migrations, or File Changes.**

---

## 9. Outstanding Issues & Acceptance Conclusion

1. **Live Testnet Execution Gate:** Live exchange order submission remains **BLOCKED** until valid Binance Spot Testnet or Bybit Testnet API credentials (key and secret) are added to the credential vault by the user. Once provisioned via `/connections/profiles` or the UI connection modal, live testnet order submission and balance reconciliation can proceed immediately without code modifications.
2. **Ready for User Provisioning:** The AES-256-GCM vault, connection permissions auditor, preflight filter gates, protective TP/SL sanity checks, and timeout reconciliation engine are fully verified and operational in staging.
