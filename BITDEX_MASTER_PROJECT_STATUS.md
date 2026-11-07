# BITDEX — Master Project Status & Live Execution Registry

**Current Date**: 2026-11-07  
**Current Phase**: **Phase 7B.2 Completed & Verified** (Multi-Tenant Technical Proof & Architecture Validation)  
**Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Active Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Latest Git Commit**: `27ec640` (Phase 7A Remediation pushed to remote)  
**Safety Governance**:
- `live_trading_locked = True`
- `emergency_lock_active = True`
- `read_only_mode = True`

---

## 1. Environment & Infrastructure Topology

| Host / Node | Public IP | WireGuard IP | Role | OS / Specs | Active Services |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Linux Staging VPS** | `169.58.218.168` | `10.88.0.1/24` | API Gateway, Backend & Customer Dashboard | Ubuntu 22.04 LTS, 8 vCPUs, 16GB RAM | • PM2 `tauric-backend-staging` (Port 8002)<br>• PM2 `tauric-dashboard-staging` (Port 33900)<br>• PM2 `bitdex-watchdog-staging` (PID 1159614)<br>• WireGuard `wg0` (UDP 51820) |
| **Windows MT5 VPS** | `149.33.34.123` | `10.88.0.2/24` | MetaTrader 5 Terminal Host & Secure IPC Bridge | Windows Server 2022 Standard (Build 20348), 1 vCPU (Xeon Gold 6154 @ 3.0GHz), 3GB RAM | • NSSM Service `BitdexMT5Gateway` (Port 8095)<br>• MetaTrader 5 Terminal (`terminal64.exe` Build 6306)<br>• WireGuard Windows Service |

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
  - Mutating endpoints (`/order/submit`, `/order/modify`, `/order/cancel`, `/position/close`) reject with `HTTP 403 Forbidden`.
  - Proved previous BTCUSD position closures were manual user GUI actions (`DEAL_REASON_CLIENT`).
  - Verified Real account `16000629657` is native `EXNESS_TERMINAL` ($0.00 balance, not MT5).
- **Phase 7A — Immediate Dashboard & Account Corrections** (Commit `27ec640`):
  - **Demo vs Real Separation**: Eliminated red "Live Execution Lock" warning when Demo is selected; Demo shows green "Demo Execution Authorization: Passed" and amber "DEMO AUTHORIZED • READ-ONLY" badge. Real accounts continue to enforce strict step-up consent and live order locks.
  - **Orders & Holdings Categorization**: Classified displayed records into distinct badges: Verified Broker Position, Simulated Strategy Position (`SEEDED_FIXTURE`), Historical Position, and Unverified Position.
  - **Account Selector Enhancement**: Categorized dropdown into Demo and Real sections, surfaced platform (`MT5` vs `EXNESS_TERMINAL`), masked ID, balance, currency, connection status, and instant checklist refresh.
  - **Five-Account Forensic Reconciliation**: Verified all 5 accounts from user screenshots, documenting exact broker platform, environment, and error states.
- **Phase 7B.1 — Architecture Validation & Technical Proof of Concept**:
  - Validated MT5 portable mode instance isolation, Exness API specification audit, resource usage benchmarks, and capacity models.
- **Phase 7B.2 — Multi-Tenant Proof & Technical Architecture Validation**:
  - Proven MT5 multi-instance process isolation on Windows VPS (dual terminals running in segregated directories).
  - Explicitly disclosed broker authentication blocker for second Demo account (requires user GUI login).
  - Implemented and deployed interactive Windows worker supervisor (Session 1 desktop environment verified).
  - Validated tenant-isolated AES-256-GCM encryption with 100% cryptographic isolation across synthetic tenants.
  - Reviewed unified trading_accounts database migration DDL and safe rollback scripts (unapplied).
  - Benchmarked MT5 worker latency: local Windows IPC = 0.040 - 0.080 ms vs WireGuard WAN RTT = 248.7 ms.
  - Verified Phase 6.0 Launch Readiness Security Audit: 12 Passed, 0 Failed.

---

## 3. Account Registry & Forensic Classification

| Account ID | Environment | Platform | Server | Connection Status | Verified Balance | Verified Equity | Classification / Technical State |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`474861031`** | **DEMO** | **MT5** | `Exness-MT5Trial15` | **ACCOUNT_DATA_VERIFIED** | **`$5,076.03`** | **`$5,076.03`** | **Active Verified MT5 Demo Account**. Authenticated via Windows Gateway (`10.88.0.2:8095`). Selected in HFT dashboard. |
| **`16000629657`** | **REAL** | **EXNESS_TERMINAL** | `https://api.exness.com` | **ACCOUNT_DATA_VERIFIED** | **`$0.00`** | **`$0.00`** | **Active Verified Exness Terminal Account**. `stream_id: dx.2.real.std`. Not eligible for MT5 (`mt5_eligible: false`). Real trading locked. |
| **`460310009`** | **REAL** | **MT5** | `Exness-MT5Real*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Real MT5 Standard Account** (Historical screenshot: $14.35). Incompatible with Exness Trader Web API (`HTTP 401/400`). Requires dedicated MT5 Real worker terminal. |
| **`478461031`** | **DEMO** | **MT5** | `Exness-MT5Trial*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Historical Demo MT5 RawSpread Account** ($5,070.71 in screenshot). Superseded on active Windows terminal by `474861031` ($5,076.03). Preserved in database. |
| **`17000660016`** | **DEMO** | **EXNESS_TERMINAL** | `https://api.exness.com` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Demo Exness Standard Account** ($500.00 in screenshot). Incompatible with current API key scope (key is strictly scoped to Real account `16000629657`). |
| **`473001359`** | **DEMO** | **MT5** | `Exness-MT5Trial*` | **AUTH_FAILED** | *DATA UNAVAILABLE* | *DATA UNAVAILABLE* | **Demo MT5 Standard Account** ($10,000.00 in screenshot). MT5 protocol account; requires MT5 worker instance. |

---

## 4. Orders & Holdings Classification Registry

| Position Identifier | Instrument | Exchange | Platform | Environment | Category Badge | Data Source | Last Synced / Timestamp |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`POS-DEMO-BTC-01`** | `BTCUSDT` | `BINANCE` | Spot/Perps | `DEMO` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Preview Benchmark) | `2026-11-04T20:23:00Z` |
| **`POS-DEMO-ETH-02`** | `ETHUSDT` | `BINANCE` | Spot/Perps | `DEMO` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Preview Benchmark) | `2026-11-04T20:23:00Z` |
| **`POS-DEMO-SOL-03`** | `SOLUSDT` | `BYBIT` | Spot/Perps | `DEMO` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Preview Benchmark) | `2026-11-04T20:23:00Z` |
| **`POS-DEMO-BNB-04`** | `BNBUSDT` | `BINANCE` | Spot/Perps | `DEMO` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Preview Benchmark) | `2026-11-04T20:23:00Z` |
| **`POS-FRESH-01`** | `BTCUSDT` | `BINANCE` | Spot | `DEMO` | **Unverified Position** | `UNKNOWN` (Legacy Ledger Store) | `2026-11-04T20:22:59Z` |
| **`POS-PAPER-AVAX-05`** | `AVAXUSDT` | `TAURIC_SIM`| Paper Sim | `PAPER` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Paper Engine) | `2026-11-04T20:23:00Z` |
| **`POS-PAPER-LINK-06`** | `LINKUSDT` | `TAURIC_SIM`| Paper Sim | `PAPER` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Paper Engine) | `2026-11-04T20:23:00Z` |
| **`POS-PAPER-XRP-07`** | `XRPUSDT` | `TAURIC_SIM`| Paper Sim | `PAPER` | **Simulated Strategy Position** | `SEEDED_FIXTURE` (Paper Engine) | `2026-11-04T20:23:00Z` |

---

## 5. Outstanding Tasks & Next Authorized Actions

- **Current Status**: Phase 7A remediation is committed (`27ec640`) and deployed to staging. Phase 7B blueprint is published.
- **Immediate Requirement**: Await explicit client review and authorization of the Phase 7B Commercial Architecture Blueprint before commencing Phase 7C refactoring.
- **Safety Locks Maintained**: Live trading, emergency lock, and read-only mode remain strictly enforced across all components.
