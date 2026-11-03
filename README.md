# BITDEX Platform — Institutional Quantitative Architecture & Engineering Specification

**Central Repository:** `git@github.com:nexuratechpteltd-tech/bitdex-platform.git`  
**Staging Environment:** `https://bitdex.ltd` (`/opt/tauric-platform-staging/`)  
**Production Status:** STRICTLY OFF-LIMITS (`/opt/tauric-platform/`)  
**Global Security Locks:** `live_trading_locked = True`, `read_only_mode = True`

---

## 1. System Overview

BITDEX is an institutional-grade algorithmic cryptocurrency intelligence and autonomous execution platform built for Binance USD(S)-M Futures and Spot markets. The platform operates on a non-custodial, hardware-isolated tenant model designed around mathematical risk budgets, deterministic fee accounting, and dual-layer position protection.

```
+-----------------------------------------------------------------------------+
|                          BITDEX MULTI-ENGINE CORE                           |
+-----------------------------------------------------------------------------+
                                       |
                +----------------------+----------------------+
                |                                             |
                v                                             v
    +-----------------------+                     +-----------------------+
    |       ENGINE A        |                     |       ENGINE B        |
    |  Spot Grid & Swing    |                     | High-Frequency Scalp  |
    |  (Multi-Day Hold)     |                     | (Donchian / RVOL / ADX|
    +-----------------------+                     +-----------------------+
                |                                             |
                +----------------------+----------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |    ENGINE COORDINATOR (R1)        |
                     |  - Atomic CAS Lease Lock (SQLite) |
                     |  - Mutual Exclusivity Enforcer    |
                     |  - Aggregate Exposure Gate (<=50%)|
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |   FUTURES RISK & SIZING (R2)      |
                     |  - Risk-First Position Sizing     |
                     |  - Hard 5x Leverage Ceiling Clamp |
                     |  - Itemized Maker/Taker Fees      |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |    TWO-LAYER PROTECTION (R3)      |
                     |  1. Exchange-Native STOP_MARKET   |
                     |  2. Independent PM2 Watchdog      |
                     +-----------------------------------+
```

---

## 2. Core Milestone Implementation Matrix (R1–R8)

| Milestone | Component | Implementation Status | Test Coverage | Primary Commit |
| :--- | :--- | :---: | :---: | :--- |
| **R0.1 / R0.2** | Git Staging Initialization | **COMPLETE** | Checksum & Merge Verified | `98e1217`, `5e6d40d` |
| **R1** | Dual-Engine Foundation & Symbol Leases | **COMPLETE** | 8/8 Unit Tests PASS (0.036s) | `aae1e6e` |
| **R2** | Risk-First Sizing & Net Fee Accounting | **COMPLETE** | 8/8 Unit Tests PASS (0.001s) | `b34e259` |
| **R3** | Two-Layer Protection & Watchdog Daemon | **COMPLETE** | 5/5 Unit Tests PASS (0.014s) | `f7693b7` |
| **R4** | Dynamic Perpetual Pair Discovery | **COMPLETE** | 3/3 Unit Tests PASS (0.005s) | `05621ca` |
| **R5** | Engine B Autonomous Scalp Execution | **COMPLETE** | 4/4 Unit Tests PASS (0.165s) | `6d182dd` |
| **R6** | Mobile-First Institutional UI Redesign | **COMPLETE** | 7 Viewports Verified (360px–1440px) | `7e5fd35` |
| **R7** | Extended Testnet Shadow Validation | **COMPLETE** | 100 Shadow Cycles + 50 Executions | `3574b5f` |
| **R8** | Final Security & Operational Acceptance | **COMPLETE** | 28/28 Unit Tests + Full PRAGMA Pass | `HEAD` |

---

## 3. Architecture Deep-Dive

### R1: Dual-Engine Foundation & Mutual-Exclusivity Leases
- **Service:** `app/services/engine_coordinator.py` (`EngineCoordinator`)
- **Database Table:** `futures_symbol_leases` with atomic Compare-And-Swap (CAS) state locking.
- **Rules:**
  - No two engines can trade or hold positions in the same symbol concurrently.
  - Active leases have a 15-minute heartbeat TTL with automatic stale-lease reclamation.
  - Hard aggregate portfolio exposure ceiling clamped at **50.0%** of available margin equity.
  - Engine B is hard-disabled by default (`engine_b_enabled = 0`) on all newly provisioned accounts.

### R2: Risk, Position Sizing & Accounting
- **Service:** `app/services/futures_risk_sizing_engine.py` (`FuturesRiskSizingEngine`)
- **Rules:**
  - Capital-at-risk first sizing: Notional is strictly derived from distance to stop ($\le 1.0\%$ account equity).
  - Maximum leverage clamped at **5x** regardless of exchange allowance.
  - Anti-inflation gate: Rejects trades if Binance `MIN_NOTIONAL` requires taking more risk than the assigned budget.
  - Deterministic fee modeling: 0.02% Maker, 0.04% Taker, with continuous 8-hour funding drag accrual.
  - Multi-tier partial-fill net P&L reconciliation with exact cent precision.

### R3: Two-Layer Position Protection & Independent Watchdog
- **Supervisor Service:** `app/services/protection_watchdog.py` (`ProtectionWatchdog`)
- **Independent Daemon:** `run_watchdog_daemon.py` managed under PM2 (`bitdex-watchdog-staging`, PID 1159614).
- **Two Protection Layers:**
  1. **Layer 1 (Exchange-Native):** Atomically attaches a Binance `STOP_MARKET` order immediately upon entry fill.
  2. **Layer 2 (Out-of-Band Supervisor):** Polling loop running every 1.5 seconds checking:
     - Naked position detection (missing stop order).
     - Quantity mismatches between open positions and active stops.
     - Liquidation danger proximity ($< 3.0\%$ mark-to-liquidation distance triggers immediate emergency flatten order and trips account circuit breaker).

### R4: Dynamic Binance Futures Perpetual Pair Discovery
- **Service:** `app/services/futures_discovery.py` (`MarketDiscoveryService`)
- **Gates:**
  - Contract Type: Strictly `PERPETUAL` (quarterly/delivery delivery contracts rejected).
  - Quote Asset: `USDT`.
  - Spread Gate: Bid/Ask spread $\le 5$ basis points ($\le 0.05\%$).
  - 24h Rolling Volume: $\ge \$20,000,000$ USD equivalent.
  - Premium Index Funding Rate: $|Funding| \le 0.05\%$.

### R5: Engine B Autonomous Execution Controller
- **Service:** `app/services/futures_engine_b.py` (`EngineBFuturesService`)
- **Strategy:** `POST_ONLY_MOMENTUM_SCALP`
  - Breakout detection across 20-period Donchian channels (1m and 5m).
  - Trend confirmation: ADX(14) $\ge 22.0$ with directional indicator confirmation ($+DI > -DI$ for longs, $-DI > +DI$ for shorts).
  - Relative Volume (RVOL): $\ge 1.5$ volume expansion over 20-period moving average.
  - Execution: Post-Only Maker limit orders (GTX) at Best Bid/Ask with 15-second cancellation timeout to prevent chasing.

### R6: Institutional Mobile-First UI & Protection Center
- **Component:** `dashboard/src/components/ProtectionCenter.tsx`
- **Design System:**
  - Deep Institutional Dark Palette: `#0A0A0E` canvas, `#121218` elevated surfaces, `#272735` borders.
  - Visual Accents: `#00E5FF` (Cyan primary), `#10B981` (Emerald armed/positive), `#EF4444` (Emergency red).
  - Real-time indicator displaying Live Watchdog PID, Two-Layer Armed status, active mutual exclusivity leases, and portfolio exposure ratio.
  - Responsive Bottom Sticky Navigation Bar on screens $\le 768$px with $\ge 48$px touch targets for instantaneous one-thumb access to Trading, Balances, Billing, and Support.
  - Verified across 7 responsive breakpoints: 360px, 375px, 390px, 430px, 768px, 1024px, 1440px with zero horizontal scroll overflow.

### R7: Extended Testnet Shadow Validation Results
- **Validation Script:** `run_r7_testnet_validation.py`
- **Output Report:** `r7_testnet_validation_report.json`
- **Summary Metrics:**
  - **Total Market Cycles Evaluated:** 100
  - **Signal Distribution:** 26 LONG, 27 SHORT, 47 NO_TRADE
  - **Controlled Executions:** 50 Completed Trades
  - **Win Rate:** **60.0%** (30 Wins, 20 Losses)
  - **Gross Realized P&L:** **+$3,787.88 USD**
  - **Itemized Trading Fees:** -$228.38 USD
  - **Net Realized P&L:** **+$3,559.53 USD**
  - **Profit Factor:** **16.59**
  - **Average Slippage:** **0.71 bps**
  - **Stop Placement Reliability:** **100.0%** (50/50 stops confirmed)
  - **Naked Position Count:** **0**
  - **Cooldown & Collision Breakers:** Verified under load (0 lease violations).

---

## 4. Strict Safety & Boundary Verification (R8)

1. **Production Isolation:**
   - Production path `/opt/tauric-platform/` and production website `https://sheltr.agency` are strictly off-limits and have **zero** file modifications or process interactions.
2. **Global Trading Locks:**
   - `live_trading_locked = True` and `read_only_mode = True` are hardcoded in `app/config.py`.
   - Zero real-money orders, zero Mainnet API orders, and zero fund transfers.
3. **Customer Record & Override Preservation:**
   - Ali Ajmal (`USR-904424B4FB`) has 3 active $0.00 promotional fee overrides fully preserved in `customer_pricing_overrides`:
     - `AI_ANALYSIS`: `$0.00` (OVR-A0580A6C1F)
     - `PLATFORM_ACTIVATION`: `$0.00` (OVR-E4ACF0A583)
     - `STRATEGY_EXECUTION`: `$0.00` (OVR-F1595D5315)
4. **Database Health:**
   - `PRAGMA integrity_check` $\to$ `ok`
   - `PRAGMA foreign_key_check` $\to$ `0 violations`
5. **Daemon Supervision:**
   - `bitdex-watchdog-staging` running 24/7 under PM2 with zero unhandled restarts and 1.5s persistent heartbeat writing to `/opt/tauric-platform-staging/backend/watchdog_heartbeat.json`.

---
*© 2026 BITDEX — Institutional Quantitative Digital Asset Architecture*
