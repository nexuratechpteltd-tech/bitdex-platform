# BITDEX — HFT Dashboard Red Indicator Root Cause Analysis

**Audit Date:** November 5, 2026  
**Scope:** Root cause investigation of all red indicators and validation gates on the HFT Dashboard (`https://bitdex.ltd/#hft`).  

---

## 1. Margin Sizing & Capital Allocation ($100 at 5x Leverage Marked Red)

### Root Cause & Failed Backend Rule:
- **Backend File:** `/opt/tauric-platform-staging/backend/app/routes/saas_customer.py`
- **Function:** `get_hft_pretrade_validation_route(symbol, current_user)` (Lines 2235–2240)
- **Validation Logic:**
  ```python
  acc_row = conn.execute("SELECT * FROM futures_accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
  avail_balance = float(acc_row["available_balance"]) if acc_row else 0.0
  has_margin = avail_balance >= margin_req or (conn_row and conn_row["environment"] == "testnet")
  ```
- **Observed Database State (`futures_accounts` for active user):**
  - Account: `FACC-814FCE09C6D4`
  - `wallet_balance`: `$0.00`
  - `available_balance`: `$0.00`
  - Configured Margin Required: `$100.00`
- **Result:**
  - `avail_balance ($0.00) >= margin_req ($100.00)` evaluates to **`False`**.
  - `conn_row["environment"]` is stored as `"DEMO"` or `"LIVE"` rather than literal lowercase `"testnet"`, failing the secondary bypass.
- **Exposure Math:**
  - Allocated Margin: `$100.00`
  - Leverage: `5x`
  - Notional Scalp Exposure: `$100.00 * 5 = $500.00 USD`
  - Maximum Safe Daily Risk (2% cap): `$10.00 USD`
  - Required Margin: `$100.00` | Available Margin: `$0.00` $\rightarrow$ **FLAGGED RED (MARGIN_ADEQUACY FAILED)**.

---

## 2. Engine Exclusivity Mutual Lock (CAS) on BTCUSDT

### Current Lease Owner Investigation:
- **Backend File:** `/opt/tauric-platform-staging/backend/app/routes/saas_customer.py` (Line 2248) and `/opt/tauric-platform-staging/backend/app/services/engine_coordinator.py`
- **Query:** `SELECT * FROM futures_symbol_leases WHERE symbol = 'BTCUSDT' AND status = 'ACTIVE' LIMIT 1`
- **Actual Row in Database:**
  ```json
  {
    "account_id": "FACC-814FCE09C6D4",
    "symbol": "BTCUSDT",
    "engine_id": "ENGINE_B",
    "lease_token": "LSE-3874238fc47c702f",
    "acquired_at": "2026-11-03T20:53:29Z",
    "expires_at": "2026-11-03T21:54:51Z",
    "status": "ACTIVE",
    "metadata_json": "{}"
  }
  ```
- **Root Cause:**
  1. The lease was acquired on **November 3, 2026 at 20:53:29 UTC** and expired at **21:54:51 UTC** on November 3.
  2. The SQL query simply checks `status = 'ACTIVE'` without filtering out `WHERE expires_at > CURRENT_TIMESTAMP`.
  3. Because no background sweeping worker updated `status = 'EXPIRED'`, this zombie lease is treated as an active collision lock, marking the gate red whenever another session evaluates `BTCUSDT`.

---

## 3. Pre-Trade Gate: `Missing Broker Stops: 0 Unprotected` & `PRE_TRADE_BLOCKED`

### Detailed Mechanics:
- **Backend File:** `/opt/tauric-platform-staging/backend/app/services/exness/risk_guard.py` (`detect_missing_stop_loss`) and `InstitutionalTradingDashboard.tsx` (Lines 1880–1890)
- **What "0 Unprotected" Means:**
  - The risk guard iterates through open positions: `unprotected = [p for p in positions if not p.get("sl") or float(p["sl"]) <= 0]`.
  - Because there are currently **0 open positions**, `unprotected_positions_count` is **`0`** (which is mathematically correct and green).
- **Why `PRE_TRADE_BLOCKED` Is Returned:**
  - `POST /hft/exness/risk/check` evaluates:
    ```python
    if self.limits.emergency_lock_active or settings.live_trading_locked:
        return False, "PRE_TRADE_BLOCKED (Emergency Lock Active)"
    ```
  - Even though open stops are 0, the top-level safety barrier `live_trading_locked = True` triggers the pre-trade block message.

---

## 4. Emergency Lock Architecture Disaggregation

The platform implements three independent safety locks:

| Lock Name | Config Location | Purpose & Scope | Current Value |
| :--- | :--- | :--- | :--- |
| **`live_trading_locked`** | `backend/app/config.py` | Platform-wide binary kill-switch preventing live money order transmission to external broker APIs. | **`True`** |
| **`read_only_mode`** | `backend/app/config.py` | Clamps entire SaaS and database mutations to read-only; denies real and demo order placement. | **`True`** |
| **`emergency_lock_active`** | `app/services/exness/risk_guard.py` | Local quantitative circuit breaker triggered when portfolio drawdown or daily loss threshold is exceeded. | **`True`** |
