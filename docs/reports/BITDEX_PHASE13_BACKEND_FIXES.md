# BITDEX — PHASE 13: BACKEND DEFECT REPAIRS & TELEMETRY API REPORT

**Timestamp:** 2026-11-05T00:15:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Execution Environment:** Production-Equivalent Staging  

---

## 1. Executive Summary

During Phase 13 implementation, four major backend architectural and data-integrity defects were investigated and systematically repaired:
1. **Stale/Expired Symbol Lease Contention (`BTCUSDT`)**: Repaired compare-and-swap (CAS) expiry logic in `engine_coordinator.py` and `saas_customer.py` so expired leases automatically transition to `EXPIRED` status without blocking valid customer sessions.
2. **Margin Adequacy Validation**: Eliminated arbitrary string-based bypasses and implemented authoritative balance comparisons with explicit separation of Available vs Required margin.
3. **Binance Public Market Data Labelling**: Corrected misleading environment labelling from "Binance Futures Testnet" to "Binance Spot Market Data" with explicit read-only live data badges.
4. **Authoritative Customer HFT Activity Endpoints**: Deployed three new broker-backed customer endpoints (`/positions`, `/orders`, `/account-summary`) with zero fabricated telemetry.

---

## 2. Component 1: Expired Symbol Lease Atomic Handling

### Defect Identified
The `futures_symbol_leases` table stored `status = 'ACTIVE'` with past UTC timestamps (`expires_at < now`). The lease acquisition query in `acquire_lease()` checked only `status = 'ACTIVE'`, causing an expired lease (e.g., `LSE-3874238fc47c702f` created Nov 3, 2026) to indefinitely block new session validations on `BTCUSDT` across engines and accounts.

### Implementation Fix in `backend/app/services/engine_coordinator.py`
1. **`clean_expired_leases(conn)`**:
   ```python
   def clean_expired_leases(conn) -> int:
       now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
       cur = conn.execute(
           "UPDATE futures_symbol_leases SET status = 'EXPIRED' WHERE status = 'ACTIVE' AND expires_at <= ?",
           (now_utc,)
       )
       return cur.rowcount
   ```
2. **`get_symbol_active_lease(conn, symbol)`**:
   - Executes `clean_expired_leases(conn)` atomically.
   - Evaluates active leases with `expires_at > now_utc`.
3. **`acquire_lease()`**:
   - Enforces cross-engine and cross-account exclusivity only against genuinely active unexpired leases.
   - Automatically reuses expired or released lease rows via atomic CAS updates.

### Test Results on Staging
- All 5 `EngineCoordinator` unit tests passed:
  - Test 1 (Acquire lease on `BTCUSDT`): **PASSED** (`LSE-TEST-01` acquired).
  - Test 2 (Same-account competing engine collision blocked): **PASSED** (Engine A collision rejected).
  - Test 3 (Cross-account collision blocked): **PASSED** (Account 2 collision rejected).
  - Test 4 (Same-engine renewal with UTC extension): **PASSED** (`expires_at` extended).
  - Test 5 (Explicit release): **PASSED** (Status updated to `RELEASED`).

---

## 3. Component 2: Margin Adequacy Validation Repair

### Defect Identified
In `backend/app/routes/saas_customer.py`, the validation gate previously checked:
```python
if "testnet" in env:
    passed = True
```
This allowed accounts with `$0.00` balance to pass margin checks under testnet while failing under demo, and failed to surface the actual dollar shortfall to the user.

### Implementation Fix
In `get_hft_pre_trade_validation_route()`:
1. Authoritative available balance is extracted directly from `futures_accounts` or `billing_accounts`.
2. Required margin is calculated from `margin_allocation_usd` and configured isolated leverage.
3. Explicit condition: `is_adequate = (avail_balance >= margin_req and margin_req > 0)`.
4. Detail string explicitly returns dollar values:
   `"Available: $0.00 | Required: $50.00 (3x isolated leverage) — Insufficient margin in DEMO account."`
5. Verified on staging account `USR-402F7BFE6D`: correctly evaluates to `[FAIL]` with honest telemetry.

---

## 4. Component 3: Binance Environment Normalization

### Defect Identified
Frontend and backend labels inconsistently referred to Binance public market data as "Binance Futures Testnet API" with live credentials, creating security confusion.

### Implementation Fix
1. In `saas_customer.py`, normalized exchange connection badge to:
   - Name: `"Binance Spot Market Data"`
   - Detail: `"Public WebSocket & REST feed active. Controlled Validation Mode: Live Mainnet locked, read-only mode enforced."`
2. Verified that zero private Binance API keys or live trading routes are invoked for public ticker data.

---

## 5. Component 4: New Customer HFT Trading Activity Endpoints

Deployed 3 new REST endpoints under `/api/v1/saas/customer/trading/hft/`:

| Endpoint | Method | Response Payload | Verification Status |
| :--- | :--- | :--- | :--- |
| `/trading/hft/positions` | `GET` | Returns open and closed positions with direction, size, entry price, mark price, unrealized PnL, leverage, and stop/take-profit levels. | **HTTP 200 OK** |
| `/trading/hft/orders` | `GET` | Returns open and closed working limit GTX orders with side, price, quantity, status, and timestamp. | **HTTP 200 OK** |
| `/trading/hft/account-summary` | `GET` | Authoritative broker account summary: wallet balance, available margin, margin in use, unrealized PnL, equity, and margin mode (`ISOLATED`). | **HTTP 200 OK** |

All endpoints require JWT bearer authentication, enforce tenant isolation, and return broker-confirmed data with zero synthetic interpolation.
