# BITDEX — PHASE 7E: FIRST GENUINE DEMO EXECUTION
## Forensic Audit, Preflight Verification & Acceptance Report

**Date**: 2026-11-08  
**Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Active Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Previous Verified Baseline**: Phase 7D (`28df8eb`)  
**Target Environment**: Staging Only  
**Target Account**: Exness MT5 Demo `#474861031`  
**Server**: `Exness-MT5Trial15`  
**Account Tier**: RawSpread (Hedging mode, USD)  
**Balance / Equity**: **$5,076.03 USD** / **$5,076.03 USD**  
**Linux Staging VPS**: `169.58.218.168` (WireGuard `10.88.0.1`)  
**Windows MT5 VPS**: `149.33.34.123` (WireGuard `10.88.0.2:8095`)  

---

## 1. Forensic Audit of Phase 7D Implementation

### 1.1 Git Working Tree & Commit Heritage
- **Active Branch**: `feature/hft-redesign-and-navigation-cleanup`
- **Remote Tracking**: `origin/feature/hft-redesign-and-navigation-cleanup` (synchronized, zero unpushed commits prior to this phase).
- **Baseline Commit**: `28df8eb` (*feat(phase7d): implement controlled demo execution readiness, isolated demo authorization & emergency controls*).
- **Working Tree**: Clean prior to Phase 7E additions.

### 1.2 DemoExecutionService & Phase 7D Endpoints Inspection
All four Phase 7D endpoints are implemented in `app/routes/saas_customer.py` and backed by `app/services/demo_execution_service.py`:
1. `POST /api/v1/saas/customer/trading/hft/session/demo-authorize`:
   - Enforces strict tenant ownership (`USR-ADM-B022F490`).
   - Verifies account status (`ACCOUNT_DATA_VERIFIED`).
   - Issues cryptographically isolated token `DEMO-AUTH-*` with 3,600-second TTL.
   - Rejects Real accounts with `HTTP 403 Forbidden` (`REAL_TRADING_PERMANENTLY_LOCKED`).
2. `POST /api/v1/saas/customer/trading/hft/session/emergency-disarm`:
   - Instantly disarms all active tokens, marks `emergency_stop_triggered = 1`, and logs audit trail.
3. `GET /api/v1/saas/customer/trading/hft/session/demo-status`:
   - Reports live authorization status, remaining TTL, risk limit usage, and platform safety flags.
4. `POST /api/v1/saas/customer/trading/hft/session/demo-simulate-order`:
   - Simulates pre-execution order validation against mandatory broker-side SL/TP, position caps, and exposure barriers. Zero live orders dispatched.
5. `POST /api/v1/saas/customer/trading/hft/session/demo-preflight` *(Phase 7E Addition)*:
   - Non-mutating preflight validation checking broker symbol mapping (`BTCUSD` -> `BTCUSDr`), margin requirements, and exact monetary risk.

---

## 2. Windows Gateway Audit & Execution Block Inspection

Inspection of `C:\bitdex-mt5-gateway\mt5_gateway_server.py` on the Windows VPS confirms:
- **Global Safety Variables**:
  - `LIVE_TRADING_LOCKED = True` (Line 42)
  - `EMERGENCY_LOCK_ACTIVE = True` (Line 43)
  - `READ_ONLY_MODE = True` (Line 44)
- **Active Mutating Execution Blocks**:
  - Lines 871-875: `POST /order/submit` raises `HTTP 403 Forbidden` (`ORDER_EXECUTION_BLOCKED: Platform safety lock active (live_trading_locked=True, read_only_mode=True, emergency_lock_active=True). Zero live orders permitted.`).
  - Lines 877-886: `POST /order/modify` raises `HTTP 403 Forbidden` (`ORDER_MODIFICATION_BLOCKED`).
  - Lines 889-898: `POST /order/cancel` raises `HTTP 403 Forbidden` (`ORDER_CANCELLATION_BLOCKED`).
  - Lines 901-910: `POST /position/close` raises `HTTP 403 Forbidden` (`POSITION_CLOSE_BLOCKED`).

### Interaction of Demo Authorization with Platform Locks
- **Real Trading Exclusion**: `LIVE_TRADING_LOCKED` and `READ_ONLY_MODE` remain permanently active across all Real accounts.
- **Isolated Demo Scope**: Demo authorization permissions apply strictly and exclusively to server-confirmed Demo account `474861031`. Any request specifying a Real account is hard-rejected at both the Linux API layer and the Windows Gateway layer.
- **Emergency Lock Primacy**: `EMERGENCY_LOCK_ACTIVE` acts as an unconditional circuit breaker. If triggered, Demo authorization is immediately revoked and execution is blocked.

---

## 3. Interactive MT5 Worker & Session Topology

Process inspection on Windows VPS (`149.33.34.123`):
- **GUI Terminal Process**: `terminal64.exe` PID 320 running in **Session 2 (Interactive RDP Session of `Administrator`)**, WorkingSet: 142.1 MB.
- **Terminal Status**: Authenticated to `Exness-MT5Trial15` on Demo account `#474861031` (RawSpread, Hedging, 313 symbols synchronized, 0 open positions).
- **Session 0 Orphaned Process**: `terminal64.exe` PID 4664 was spawned non-interactively in Session 0.
- **IPC Limitation Evidence**: In Session 0, calling `mt5.initialize()` returns `(-10005, 'IPC timeout')` because Windows Session 0 Isolation blocks cross-session UI message queues.
- **Worker Execution Architecture**:
  - The local scalping agent (`local_scalper_agent.py`) and interactive test worker run in the user session (Session 2), bypassing Session 0 isolation with **0.015 ms** decision latency.

---

## 4. Proposed First Demo Trade Parameters & Monetary Risk

The non-mutating preflight test was executed against `POST /api/v1/saas/customer/trading/hft/session/demo-preflight` and verified:

```json
{
  "status": "SUCCESS",
  "preflight_status": "READY_FOR_EXECUTION_HELD",
  "execution_intent": "NON_MUTATING_PREFLIGHT",
  "account_verification": {
    "broker_login": "474861031",
    "server_name": "Exness-MT5Trial15",
    "environment": "DEMO",
    "account_tier": "RawSpread",
    "verified_balance_usd": 5076.03,
    "verified_equity_usd": 5076.03,
    "free_margin_usd": 5076.03
  },
  "proposed_order": {
    "client_symbol": "BTCUSD",
    "broker_symbol": "BTCUSDr",
    "direction": "BUY",
    "order_type": "ORDER_TYPE_BUY",
    "volume": 0.01,
    "entry_price": 75800.0,
    "stop_loss": 75700.0,
    "take_profit": 76000.0,
    "stop_distance_usd": 100.0,
    "risk_reward_ratio": 2.0,
    "max_monetary_risk_usd": 1.0,
    "target_monetary_profit_usd": 2.0,
    "risk_pct_of_equity": 0.0197
  },
  "safety_governance": {
    "live_trading_locked": true,
    "real_trading_locked": true,
    "read_only_mode": true,
    "emergency_lock_active": false,
    "real_accounts_barred": true,
    "broker_order_submitted": false
  }
}
```

### Risk & Exposure Summary:
- **Broker Symbol**: `BTCUSDr` (Exness RawSpread CFD instrument).
- **Direction**: `BUY` (Market Order).
- **Volume**: **`0.01` lots** (Minimum broker lot size).
- **Entry Price Reference**: `$75,800.00 USD`.
- **Mandatory Protective Stop Loss**: `$75,700.00 USD` (Distance = `$100.00 USD`, conforming to broker minimum `stops_level` of $0.50).
- **Take Profit Target**: `$76,000.00 USD` (Distance = `$200.00 USD`, Risk:Reward ratio = **2.0:1** >= 1.50).
- **Maximum Monetary Risk**: **`$1.00 USD`** (**`0.0197%`** of account equity).
- **Target Monetary Profit**: **`$2.00 USD`**.
- **Required Margin**: **`~$3.79 USD`** (at 1:200 leverage). Account free margin is **`$5,076.03 USD`**.

---

## 5. Automated Acceptance Test Suite (11/11 PASS)

Test Suite: `backend/tests/test_phase7d_demo_readiness.py`  
Command: `.venv/bin/python3 tests/test_phase7d_demo_readiness.py`  
Result: **11 passed, 0 failed (100% pass rate in 0.132s)**

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_01` | Explicit verified Demo account receives isolated Demo authorization token | **PASS (ok)** |
| `test_02` | Any Real account authorization attempt is hard-rejected with HTTP 403 | **PASS (ok)** |
| `test_03` | Duplicate tenant conflict account is strictly rejected with HTTP 403 | **PASS (ok)** |
| `test_04` | Unauthorized cross-tenant account request is blocked | **PASS (ok)** |
| `test_05` | Rejection of orders missing Stop Loss, Take Profit, or with invalid distances | **PASS (ok)** |
| `test_06` | Risk Barrier Gate: Reject order when 3 simultaneous positions are open | **PASS (ok)** |
| `test_07` | Risk Barrier Gate: Reject order exceeding 30% account equity exposure cap | **PASS (ok)** |
| `test_08` | Risk Barrier Gate: Reject order when daily loss limit ($50.00 USD) is reached | **PASS (ok)** |
| `test_09` | Emergency Stop disarms Demo authorization instantly and revokes execution | **PASS (ok)** |
| `test_10` | Simulated order pre-execution passes all gates, confirming ZERO live orders to MT5 | **PASS (ok)** |
| `test_11` | Non-mutating preflight test confirms account identity, broker symbol BTCUSDr and monetary risk | **PASS (ok)** |

---

## 6. Remaining Blockers & Explicit Pre-Trade Hold

### Remaining Blockers:
1. **Interactive Worker Session Dispatch**:
   - The Windows Gateway service (`http://10.88.0.2:8095`) runs in Session 0, where `MetaTrader5.initialize()` blocks on Windows GUI message queues.
   - For genuine Demo order execution, the order must be dispatched via the interactive worker running in Session 2 (`terminal64.exe` PID 320) or through the interactive worker bridge.
2. **Global Gateway Lock**:
   - `C:\bitdex-mt5-gateway\mt5_gateway_server.py` `/order/submit` currently has the hard platform block active. To permit Demo-only execution, an isolated Demo pathway (`/demo/order/submit`) scoped strictly to `#474861031` on `Exness-MT5Trial15` must be enabled while leaving Real accounts permanently locked.
3. **Pre-Trade Hold**:
   - Execution is held pending explicit user sign-off.

> [!IMPORTANT]
> **EXPLICIT PRE-TRADE SIGN-OFF HOLD**:
> All non-mutating preflight verifications have passed with 100% success. **Zero genuine orders have been submitted to Exness**.
>
> **Do you authorize proceeding with the first genuine Demo execution of 0.01 lot BTCUSDr on Exness MT5 Demo `#474861031` (Max Monetary Risk: $1.00 USD)?**
