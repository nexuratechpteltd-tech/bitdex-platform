# BITDEX — Master Project Status & Live Execution Registry

**Current Date**: 2026-11-08  
**Current Phase**: **Phase 7C Completed & Verified** (Automated High-Frequency Scalping Engine)  
**Website**: `https://bitdex.ltd`  
**Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Active Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Latest Git Baseline**: `08ca2f6` (Phase 7B.7 Accepted)  
**Safety Governance**:
- `live_trading_locked = True`
- `emergency_lock_active = True`
- `read_only_mode = True`

---

## 1. Environment & Infrastructure Topology

| Host / Node | Public IP | WireGuard IP | Role | OS / Specs | Active Services |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Linux Staging VPS** | `169.58.218.168` | `10.88.0.1/24` | API Gateway, Backend & Customer Dashboard | Ubuntu 22.04 LTS, 8 vCPUs, 16GB RAM | • PM2 `tauric-backend-staging` (Port 8002)<br>• PM2 `tauric-dashboard-staging` (Port 33900)<br>• PM2 `bitdex-watchdog-staging` (PID 1159614)<br>• WireGuard `wg0` (UDP 51820) |
| **Windows MT5 VPS** | `149.33.34.123` | `10.88.0.2/24` | MetaTrader 5 Terminal Host & Secure IPC Bridge | Windows Server 2022 Standard (Build 20348), 1 vCPU (Xeon Gold 6154 @ 3.0GHz), 3GB RAM | • NSSM Service `BitdexMT5Gateway` (Port 8095)<br>• MetaTrader 5 Terminal (`terminal64.exe` Build 6306)<br>• Local Scalper Agent (`local_scalper_agent.py`)<br>• WireGuard Windows Service |

---

## 2. Project Execution History & Milestones

- **Phase 1 — Core Platform & Exness Integration**:
  - Exness Trader API connector with Ed25519 payload signing.
  - HFT account selector and pre-trade risk validation gates.
  - One-time real account voluntary consent modal (`REAL-CONSENT-v2`).
- **Phase 2 — Windows VPS Connectivity & Secure Tunnel**:
  - OpenSSH passwordless Ed25519 authentication (`administrator@149.33.34.123`).
  - WireGuard private tunnel (`10.88.0.1` <-> `10.88.0.2`) with mutual keepalives.
- **Phase 3 — MT5 Infrastructure & Gateway Service**:
  - Official Exness MetaTrader 5 terminal installation (Build 6306).
  - Python 3.11 isolated runtime with MetaTrader 5 Python IPC.
  - Hardened Windows Gateway 4.3.0 managed via NSSM.
- **Phase 4 — Genuine MT5 Demo Connection**:
  - Genuine Exness Demo MT5 account (`474861031`, `Exness-MT5Trial15`, RawSpread) connected.
  - Real-time balance (**$5,076.03 USD**), equity (**$5,076.03 USD**), and zero open positions.
- **Phase 5 — Backend & Dashboard Integration**:
  - Integrated `ExnessMT5GatewayAdapter` into Linux staging backend.
  - Connected account registry synchronized and displayed on customer portal.
- **Phase 6 — Safety Audit & Hard Server-Side Blocks** (Commit `11bf820`):
  - Added hard server-side execution defense blocks to `mt5_gateway_server.py`.
  - Mutating endpoints reject with `HTTP 403 Forbidden`.
  - Proved previous BTCUSD position closures were manual user GUI actions (`DEAL_REASON_CLIENT`).
  - Verified Real account `16000629657` is native `EXNESS_TERMINAL` ($0.00 balance, not MT5).
- **Phase 7A — Immediate Dashboard & Account Corrections** (Commit `27ec640`):
  - Separated Demo vs Real trading consent workflows.
  - Verified 5 Exness accounts across Demo and Real environments.
- **Phase 7B.1 to 7B.7 — Forensic Audits & CAS Lease Conflict Remediation**:
  - Remediated symbol lease collisions and duplicate tenant registrations on broker login `474861031`.
  - Quarantined cross-tenant duplicate `USR-66BCFD7350` as `DUPLICATE_TENANT_CONFLICT`.
  - Verified primary verified owner `USR-ADM-B022F490` (`hello@nexura.ltd`).
  - Baseline commit `08ca2f6` pushed to remote.
- **Phase 7C — Automated High-Frequency Scalping Engine** (Current):
  - **Product Transformation**: Rebranded HFT trading product into **AUTOMATED HIGH-FREQUENCY SCALPING ENGINE** across dashboard, navigation, and API endpoints.
  - **Two-Sided Regime-Aware Engine**: Evaluates independent BUY and SELL opportunities with no directional bias, using EMA cross structures, RSI momentum, and ATR bounds.
  - **Mandatory Broker-Side Stop Loss & Take Profit**: Zero orders permitted without exchange-verified SL/TP meeting broker `stops_level` (50 points = $0.50 on Exness BTCUSD) and minimum 1.5:1 Risk:Reward ratio.
  - **Multi-Entry & Anti-Grid Barriers**: Max 3 positions, 30% equity exposure cap, min 1.0x ATR spacing between entries, $50.00 daily loss limit, and 30m consecutive-loss cooldown.
  - **Local Windows VPS Execution Architecture**: Implemented `local_scalper_agent.py` beside MT5 terminal (<0.45ms compute, <0.82ms IPC), achieving a **39.75ms total execution loop** (82.8x faster than the 3,292.5ms cloud path). Documented Session 0 service isolation limitation.
  - **20-Point Test Suite**: 100% pass rate (20/20 test cases verified on staging).
  - **Authoritative Screenshots**: Captured and verified `phase7c_scalping_engine_waiting_state.png`, `phase7c_scalping_engine_section4_armed.png`, and `phase7c_overview_workspace.png`.

---

## 3. Account Registry & Forensic Classification

| Account ID | Environment | Platform | Server | Connection Status | Verified Balance | Verified Equity | Classification / Technical State |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`474861031`** | **DEMO** | **MT5** | `Exness-MT5Trial15` | **ACCOUNT_DATA_VERIFIED** | **`$5,076.03`** | **`$5,076.03`** | **Active Verified MT5 Demo Account**. Sole authorized owner: `USR-ADM-B022F490`. Authenticated via Windows Gateway (`10.88.0.2:8095`). Selected in Scalping dashboard. |
| **`16000629657`** | **REAL** | **EXNESS_TERMINAL** | `https://api.exness.com` | **ACCOUNT_DATA_VERIFIED** | **`$0.00`** | **`$0.00`** | **Active Verified Exness Terminal Account**. `stream_id: dx.2.real.std`. Not eligible for MT5 (`mt5_eligible: false`). Real trading locked. |
| **`460310009`** | **REAL** | **MT5** | `Exness-MT5Real*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Real MT5 Standard Account** (Historical screenshot: $14.35). Incompatible with Exness Trader Web API (`HTTP 401/400`). Requires dedicated MT5 Real worker terminal. |
| **`478461031`** | **DEMO** | **MT5** | `Exness-MT5Trial*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Historical Demo MT5 RawSpread Account** ($5,070.71 in screenshot). Superseded on active Windows terminal by `474861031` ($5,076.03). Preserved in database. |
| **`17000660016`** | **DEMO** | **EXNESS_TERMINAL** | `https://api.exness.com` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Demo Exness Standard Account** ($500.00 in screenshot). Incompatible with current API key scope (key is strictly scoped to Real account `16000629657`). |
| **`473001359`** | **DEMO** | **MT5** | `Exness-MT5Trial*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Demo MT5 Standard Account** ($10,000.00 in screenshot). MT5 protocol account; requires MT5 worker instance. |

---

## 4. Safety Locks & Operational Constraints

All production and staging execution systems operate under continuous fail-safe governance:
- `live_trading_locked = True`: All mutating order dispatch endpoints reject with `HTTP 403 Forbidden`.
- `emergency_lock_active = True`: Global emergency kill-switch is engaged.
- `read_only_mode = True`: Strategy engines operate exclusively in monitored, read-only telemetry mode.
- Zero orders have been submitted, modified, or cancelled on the Exness broker or any live exchange.
