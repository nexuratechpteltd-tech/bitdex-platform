# BITDEX — PHASE 7B.3: COMPLETE HFT SESSION-START REMEDIATION & END-TO-END VERIFICATION

**Document Version:** 1.0.0  
**Date:** 2026-11-07  
**Environment:** Linux Staging VPS (`169.58.218.168`) & Windows Server 2022 VPS (`149.33.34.123`)  
**Git Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Target Account:** Exness Demo `#474861031` (`EXN-CONN-3D40DE9B8CE8`)  
**Platform:** MetaTrader 5 (`Exness-MT5Trial15`)  
**Selected Instrument:** `BTCUSD` (Exness CFD)  
**Safety Locks:** `live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True`

---

## 1. Executive Summary & Root Cause Resolution

In the prior diagnostic audit, clicking the **Arm & Start Session** button in the High-Frequency Trading (HFT) dashboard produced no visible response. Furthermore, the dashboard displayed a hardcoded Binance USDⓈ-M Perps strategy (`BTCUSDT`) despite selecting an Exness Demo MT5 account.

Phase 7B.3 has executed complete root cause remediation across the frontend component and backend routing layer. All silent failures have been eliminated, account-aware instrument discovery has been implemented, and end-to-end browser automation confirms clean session arming into `ARMED_READ_ONLY` mode.

### Root Causes Remediated:
1. **Frontend Hardcoded Pair & Stale Query State:**
   - In `dashboard/src/components/InstitutionalTradingDashboard.tsx`, `selectedPair` was initialized with hardcoded `"BTCUSDT"`. The `fetchHftPairs` function never sent `account_id` as a query parameter.
   - **Fix:** `selectedPair` is initialized cleanly; `fetchHftPairs(targetAcctId)` appends `?account_id=${encodeURIComponent(targetAcctId)}`. When switching between broker accounts, the instrument catalogue is dynamically reloaded and automatically selects the first eligible broker pair (`BTCUSD` for Exness).
2. **Backend Binance Exchange Connection Hard-Gate:**
   - In `backend/app/routes/saas_customer.py`, `start_hft_session_route` required an active connection in `user_exchange_connections` (Binance API keys), completely ignoring `exness_demo_connections`. If an Exness account was selected, it threw `Cannot start session: No active Binance Testnet exchange connection linked`.
   - **Fix:** Broker routing resolves the account via `_resolve_hft_account(conn, user_id, req.account_id)`. For Exness MT5, it resolves `EXNESS_MT5_GATEWAY` with worker `INST-474861031`.
3. **Mismatched Instruments & Incomplete Checklist Silencing:**
   - Attempting to trade `BTCUSDT` on Exness MT5 is invalid. The backend pairs and pre-trade validation endpoints now discover genuine Exness CFD pairs (`BTCUSD`, `ETHUSD`, `XAUUSD`, `EURUSD`, `GBPUSD`) and explicitly reject unsupported symbols (`BTCUSDT`).
   - The UI button is never silently disabled: when requirements are incomplete, it informs the user via actionable toasts and dynamic state labels (`Arm & Start Session (Read-Only)` or `Checklist Incomplete — Click to Inspect`).
4. **Session Lifecycle Persistence:**
   - Backend `start_hft_session_route` acquires an atomic symbol lease (`futures_symbol_leases`), updates `futures_accounts.engine_b_enabled = 1`, and upserts `futures_strategy_configs` status to `ACTIVE`.
   - Disarming cleanly releases the symbol lease and resets `engine_b_enabled = 0`.

---

## 2. Mandatory 14-Point Acceptance Test Suite

The 14 acceptance test cases were executed directly against the staging backend (`http://127.0.0.1:8002/api/v1/saas`) using authenticated session tokens:

| # | Test Case Description | Method & Endpoint | Payload / Query | Expected Status | Actual Status | Result |
|---|----------------------|-------------------|-----------------|-----------------|---------------|--------|
| **1** | Connected Accounts Discovery | `GET /customer/trading/hft/connected-accounts` | None | `HTTP 200` | `HTTP 200` | **PASS** |
| **2** | Exness CFD Pairs Discovery | `GET /customer/trading/hft/pairs` | `?account_id=EXN-CONN-3D40DE9B8CE8` | `HTTP 200` | `HTTP 200` | **PASS** |
| **3** | Default Pairs Discovery (No Account Param) | `GET /customer/trading/hft/pairs` | None (falls back to preferred) | `HTTP 200` | `HTTP 200` | **PASS** |
| **4** | Exness Account Summary | `GET /customer/trading/hft/account-summary` | `?account_id=EXN-CONN-3D40DE9B8CE8` | `HTTP 200` | `HTTP 200` | **PASS** |
| **5** | Pre-Trade Validation (`BTCUSD`, Exness) | `GET /customer/trading/hft/validation` | `?symbol=BTCUSD&account_id=...` | `HTTP 200` | `HTTP 200` | **PASS** |
| **6** | Pre-Trade Validation (`BTCUSDT` Rejected) | `GET /customer/trading/hft/validation` | `?symbol=BTCUSDT&account_id=...` | `HTTP 200` | `HTTP 200` | **PASS** |
| **7** | Start Session (`BTCUSD`, Exness MT5) | `POST /customer/trading/hft/session/start` | `{"account_id": "...", "symbol": "BTCUSD"}` | `HTTP 200` | `HTTP 200` | **PASS** |
| **8** | Start Session Rejection (`BTCUSDT` on Exness) | `POST /customer/trading/hft/session/start` | `{"account_id": "...", "symbol": "BTCUSDT"}` | `HTTP 400` | `HTTP 400` | **PASS** |
| **9** | Start Session Cross-Tenant Isolation | `POST /customer/trading/hft/session/start` | Foreign user account ID | `HTTP 404` | `HTTP 404` | **PASS** |
| **10** | Start Session Non-Existent Account | `POST /customer/trading/hft/session/start` | `NONEXISTENT_ACCT_999` | `HTTP 404` | `HTTP 404` | **PASS** |
| **11** | Fetch Positions (Exness Account) | `GET /customer/trading/hft/positions` | `?account_id=EXN-CONN-3D40DE9B8CE8` | `HTTP 200` | `HTTP 200` | **PASS** |
| **12** | Fetch Orders (Exness Account) | `GET /customer/trading/hft/orders` | `?account_id=EXN-CONN-3D40DE9B8CE8` | `HTTP 200` | `HTTP 200` | **PASS** |
| **13** | Stop / Disarm Session (Exness MT5) | `POST /customer/trading/hft/session/stop` | `{"account_id": "...", "symbol": "BTCUSD"}` | `HTTP 200` | `HTTP 200` | **PASS** |
| **14** | Lease Release Verification | `GET /customer/trading/hft/validation` | `?symbol=BTCUSD&account_id=...` | `HTTP 200` | `HTTP 200` | **PASS** |

**Acceptance Score: 14 / 14 Passed (100%)**

---

## 3. End-to-End Browser Automation Verification

Playwright headless browser execution on staging validated the exact UI click flow:
1. Navigated to `http://127.0.0.1:33900/#hft` with authenticated session tokens.
2. Verified Trading Account selector rendered:  
   `Exness — Demo Account — #4748•••031 [MT5] · VERIFIED · $5076.03 USD`.
3. Verified Step 1 rendered:  
   `Select MT5 CFD Contract (5 Qualified Candidates)` with `BTCUSD` selected ($75,718.00).
4. Verified Step 2 rendered:  
   `STRATEGY CONFIGURATION (BTCUSD)`: Direction `AUTO`, Margin `$50.00`, Leverage `3x`.
5. Verified Step 3 rendered:  
   `PRE-TRADE SAFETY CHECKLIST` — All 9 gates passed (`READY`).
6. Verified Step 4 Strategy Label rendered:  
   `Autonomous CFD Momentum Scalper · Exness MT5`.
7. Clicked `#btn-start-hft-session`.
8. Captured live network interaction:  
   `POST /api/backend/saas/customer/trading/hft/session/start` -> `HTTP 200 OK`.
9. Verified immediate transition to `Session State: ACTIVE` with red `Emergency Stop / Disarm` button rendered.
10. Definitive browser screenshots captured:
    - Composite View: `phase7b3_hft_armed_composite.png`
    - Lifecycle View: `phase7b3_hft_session_armed_readonly.png`

---

## 4. Safety Lock Adherence
- All order placement, modifications, and closures remain strictly barred.
- Backend routing enforces `live_trading_locked: true`, `emergency_lock_active: true`, and `read_only_mode: true`.
- Windows MT5 Gateway (`10.88.0.2:8095`) maintains server-side execution blocks.
- Zero orders or test trades were submitted during testing.
