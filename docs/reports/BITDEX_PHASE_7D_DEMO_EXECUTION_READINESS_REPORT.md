# BITDEX — PHASE 7D: CONTROLLED DEMO EXECUTION READINESS
## Forensic Audit, Architecture Delivery & Acceptance Report

**Date**: 2026-11-08  
**Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Active Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Previous Verified Baseline**: Phase 7C (`614d06f`)  
**Target Environment**: Staging Only  
**Target Account**: Exness MT5 Demo `#474861031`  
**Server**: `Exness-MT5Trial15`  
**Account Tier**: RawSpread (Hedging mode, USD)  
**Balance / Equity**: **$5,076.03 USD** / **$5,076.03 USD**  
**Linux Staging VPS**: `169.58.218.168`  
**Windows MT5 VPS**: `149.33.34.123` via WireGuard `10.88.0.2`  

---

## 1. Executive Summary

Phase 7D delivers the **Controlled Demo Execution Readiness** framework for the **Automated High-Frequency Scalping Engine**. 

### Critical Safety Compliance:
1. **ZERO LIVE OR DEMO BROKER ORDERS SUBMITTED**:
   - Testing was conducted exclusively via high-fidelity market data replay and pre-execution simulation.
   - The interactive MetaTrader 5 terminal process (`terminal64.exe` PID 320) and Windows Gateway (`mt5_gateway_server.py`) submitted **zero live or demo orders to the Exness trade server during this phase**.
2. **PERMANENT REAL TRADING LOCK ENFORCED**:
   - Real accounts are architecturally and structurally forbidden from accessing this execution pathway.
   - Any attempt to submit a live/real account (`CONN-BIN-LIVE-MIGRATED` or physical account with environment `REAL`) immediately triggers an immutable `HTTP 403 Forbidden` (`REAL_TRADING_PERMANENTLY_LOCKED`).
   - Global safety locks remain permanently active:
     - `live_trading_locked = True`
     - `real_trading_locked = True`
     - `read_only_mode = True`
3. **ISOLATED DEMO AUTHORIZATION & EMERGENCY CONTROLS**:
   - Dedicated scoped endpoints created:
     - `POST /api/v1/saas/customer/trading/hft/session/demo-authorize`
     - `POST /api/v1/saas/customer/trading/hft/session/emergency-disarm`
     - `GET /api/v1/saas/customer/trading/hft/session/demo-status`
     - `POST /api/v1/saas/customer/trading/hft/session/demo-simulate-order`
   - Verification suite passed 10/10 automated barrier checks with 100% pass rate.
4. **MANDATORY BROKER-SIDE STOP LOSS & TAKE PROFIT**:
   - Orders without protective broker-side Stop Loss and Take Profit are strictly rejected.
   - Stop Loss distance is strictly checked against the authentic broker minimum (`stops_level_points = 50.0` points / $0.50 for BTCUSD).
   - Risk:Reward ratio must strictly meet or exceed **1.50:1**.

---

## 2. Stage 1 — Forensic Pre-Flight Verification

Independently retrieved from current staging runtime and Windows VPS:

| Telemetry Item | Measured Runtime Value | Evidence / Verification Source |
| :--- | :--- | :--- |
| **Git Working Tree** | Clean on `feature/hft-redesign-and-navigation-cleanup` | `git status` (Baseline `614d06f`) |
| **Linux Backend Service** | Online (`tauric-backend-staging` PID 2185810, port 8002) | PM2 Process Monitor |
| **Linux Watchdog Service** | Online (`bitdex-watchdog-staging` PID 1159614, uptime 4D) | PM2 Process Monitor |
| **Linux Dashboard UI** | Online (`tauric-dashboard-staging` PID 2167787, port 33900) | PM2 Process Monitor |
| **Windows MT5 GUI Terminal** | `terminal64.exe` PID 320, 141.8 MB WorkingSet, Session 2 (Active RDP) | PowerShell `Get-Process terminal64` |
| **Exness Account Identity** | Login: `474861031`, Server: `Exness-MT5Trial15`, Tier: RawSpread | Authentic terminal log `20261107.log` |
| **Exness Connection Status** | Authorized through Access Point #5 (ping: 259.95 ms, build 6230), hedging mode | Authentic terminal log `20261107.log` |
| **Account Balance & Equity** | Balance: **$5,076.03 USD**, Equity: **$5,076.03 USD**, Open Positions: 0 | `exness_demo_connections` & MT5 sync |
| **Broker-Side Stops Level** | `stops_level_points = 50.0` points ($0.50 min stop distance) | `local_scalper_agent.py` symbol_info |
| **Strategy Decision Latency** | **0.015 ms** on Windows Local Execution Worker | Windows runtime benchmark |
| **WireGuard Tunnel RTT** | **254.0 ms** average between Frankfurt (10.88.0.1) and Windows (10.88.0.2) | WireGuard ICMP telemetry |

---

## 3. Stage 2 — Demo-Only Execution Isolation Architecture

### 3.1 Scoped Permissions & Validation Gates
- **Explicit Account Verification**:
  - Target account must exist in `exness_demo_connections` with `account_type == 'DEMO'` and `verification_status == 'ACCOUNT_DATA_VERIFIED'`.
  - Account must belong strictly to authenticated tenant `USR-ADM-B022F490`. Cross-tenant and duplicate conflict accounts (`EXN-CONN-3D40DE9B8CE8`) are rejected.
- **Dedicated Token Issuance**:
  - Authorizing issues a cryptographically random, tokenized permission: `DEMO-AUTH-<16-HEX>` with a 3,600-second TTL (1 hour).
  - Stored in database table `hft_demo_authorizations`.

### 3.2 Risk Barrier Limits
- **Simultaneous Positions Limit**: Maximum **3** positions total across the account.
- **Instrument Position Limit**: Maximum **2** entries per symbol (anti-grid, anti-martingale).
- **Total Exposure Cap**: Total allocated margin must not exceed **30.0%** of account equity ($1,522.80 on $5,076.03).
- **Daily Loss Cap**: Maximum daily loss capped at **$50.00 USD**. Exceeding triggers automatic trading lockout.
- **Consecutive Loss Cooldown**: **3** consecutive losses enforce an immediate **30-minute** cooldown.

### 3.3 Emergency Stop Disarm Control
- Dedicated endpoint `POST /api/v1/saas/customer/trading/hft/session/emergency-disarm` immediately revokes all active tokens, marks `emergency_stop_triggered = 1`, and logs audit trail.

---

## 4. Stage 3 — Global Safety Architecture

1. **Live Real Trading Permanently Locked**:
   - `live_trading_locked = True`
   - `real_trading_locked = True`
   - Any Real account passed to demo execution returns `HTTP 403 Forbidden` (`REAL_TRADING_PERMANENTLY_LOCKED`).
2. **Server-Side Gateway Safety Locks**:
   - In `C:\bitdex-mt5-gateway\mt5_gateway_server.py`:
     - Lines 42-44: `LIVE_TRADING_LOCKED = True`, `READ_ONLY_MODE = True`, `EMERGENCY_LOCK_ACTIVE = True`.
     - Lines 871-910: `/order/submit`, `/order/modify`, `/order/cancel`, `/position/close` reject all calls with `HTTP 403 Forbidden`.
   - Live broker-side execution remains 100% disabled.

---

## 5. Stage 4 — Acceptance Test Suite Verification

Test Suite: `backend/tests/test_phase7d_demo_readiness.py`  
Command: `.venv/bin/python3 tests/test_phase7d_demo_readiness.py`  
Result: **10 passed, 0 failed (100% pass rate in 0.078s)**

```text
test_01_demo_authorization_success:
  Explicit verified Demo account receives an isolated Demo authorization token. -> PASS (ok)
test_02_hard_reject_real_account:
  Any Real account authorization attempt is hard-rejected with HTTP 403. -> PASS (ok)
test_03_reject_duplicate_tenant_conflict_account:
  Duplicate tenant conflict account is strictly rejected with HTTP 403. -> PASS (ok)
test_04_reject_cross_tenant_unauthorized_account:
  Unauthorized cross-tenant account request is blocked. -> PASS (ok)
test_05_mandatory_sl_and_tp_enforcement:
  Rejection of orders missing Stop Loss, Take Profit, or with invalid distances. -> PASS (ok)
test_06_risk_barrier_max_positions_limit:
  Risk Barrier Gate: Reject order when 3 simultaneous positions are open. -> PASS (ok)
test_07_risk_barrier_exposure_cap:
  Risk Barrier Gate: Reject order exceeding 30% account equity exposure cap. -> PASS (ok)
test_08_risk_barrier_daily_loss_limit:
  Risk Barrier Gate: Reject order when daily loss limit ($50.00 USD) is reached. -> PASS (ok)
test_09_emergency_stop_disarm:
  Emergency Stop disarms Demo authorization instantly and revokes execution. -> PASS (ok)
test_10_simulated_order_pre_execution_zero_live_orders:
  Simulated order pre-execution passes all gates, confirming ZERO live orders to MT5. -> PASS (ok)
```

### Live HTTP API End-to-End Verification (Port 8002)
- `POST /api/v1/saas/customer/trading/hft/session/demo-authorize` -> **HTTP 200 OK** (issued `DEMO-AUTH-C458A49E54D824F5`)
- `GET /api/v1/saas/customer/trading/hft/session/demo-status` -> **HTTP 200 OK** (`is_authorized: True`, TTL 3600s)
- `POST /api/v1/saas/customer/trading/hft/session/demo-simulate-order` -> **HTTP 200 OK** (`PASSED_ALL_RISK_BARRIERS`, 0 orders to MT5)
- `POST /api/v1/saas/customer/trading/hft/session/emergency-disarm` -> **HTTP 200 OK** (`emergency_disarmed: True`)
- `POST /api/v1/saas/customer/trading/hft/session/demo-authorize` on Real account -> **HTTP 403 Forbidden** (`REAL_TRADING_PERMANENTLY_LOCKED`)

---

## 6. Stage 5 — Delivery & Explicit Pre-Trade Hold

All Phase 7D requirements have been implemented, tested, and validated.
**In strict accordance with the master protocol, ZERO genuine broker orders have been submitted.**

> [!IMPORTANT]
> **PRE-TRADE SIGN-OFF HOLD**:
> Controlled Demo Execution Readiness is fully operational. Any genuine Demo order dispatch on Exness MT5 Demo `#474861031` requires your explicit written sign-off before submission.
