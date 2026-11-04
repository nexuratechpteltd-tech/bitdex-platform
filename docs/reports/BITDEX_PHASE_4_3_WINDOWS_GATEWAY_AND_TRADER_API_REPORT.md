# BITDEX.LTD — Phase 4.3: Windows MT5 Gateway Deployment & Official Exness Trader API Authentication Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Baseline Commit:** `65892fe948af3a727f17b14ed08813a5b990743a`  
**Final Deployed Commit:** `cfb7bcc9101561503aebe36baf3fd54935f3aa45`  
**Staging Host:** `169.58.218.168` | `https://bitdex.ltd`  
**Date:** 2026-11-04  
**Safety Status:** `live_trading_locked = True` | `emergency_lock_active = True` | `read_only_mode = True`

---

## Executive Summary

Phase 4.3 resolves the critical infrastructure blockers identified in the Phase 4.2 independent verification report. We have implemented:
1. **Production-Ready Windows MT5 Gateway Package**: Complete dual-environment (`DEMO` and `REAL`) architecture with PowerShell automation, NSSM Windows service runbook, constant-time token verification, and strict read-only enforcement on live accounts.
2. **Official Exness Trader API Cryptographic Authentication**: Full implementation of the official asymmetric **Ed25519** request-signing protocol (`EXN-API-KEY`, `EXN-DATA`, `EXN-SIGN`, unpadded Base64URL SHA-256 body hash matching Exness official specification), DNS Gateway Access Point discovery, and signed WebSocket handshake headers.
3. **Payments API Balance Ingestion**: Authoritative balance and wallet querying with zero fund mutation and official Exness Personal Area deposit routing.
4. **Automated Verification**: Complete execution of the 12-invariant acceptance test suite with **100% (12/12) passing**.

---

## Key Deliverables & Architecture

### 1. Windows MT5 Gateway Package (`gateway/windows/`)

The Windows gateway provides the IPC bridge between the Linux staging environment (`169.58.218.168`) and the Windows Server MetaTrader 5 execution terminal.

| File | Purpose | Security & Architecture Highlights |
| :--- | :--- | :--- |
| `mt5_gateway_server.py` | FastAPI MT5 Server | • Dual-environment support (`DEMO` and `REAL`).<br>• Enforces `trade_mode == 0` for Demo and `trade_mode == 2` for Real.<br>• **Enforces strict Read-Only mode on Real accounts**: rejects order placement, order modification, and position closure with HTTP 403.<br>• Constant-time token verification via `X-Gateway-Auth-Token`.<br>• Endpoints: `/health`, `/heartbeat`, `/account`, `/symbols`, `/tick/{symbol}`, `/candles/{symbol}`, `/margin/calculate`, `/positions`, `/orders/history`, `/trades/history`, `/reconcile`. |
| `setup_windows_gateway.ps1` | Automated PowerShell Installer | • Validates 64-bit Python 3.10+ and MetaTrader 5 installation.<br>• Configures machine-level `EXNESS_GATEWAY_AUTH_TOKEN`.<br>• Configures Windows Firewall inbound rule restricting port 8095 to staging IP (`169.58.218.168`) and WireGuard tunnel (`10.88.0.1`).<br>• Runs automated terminal connectivity test. |
| `run_gateway.bat` | Launcher Script | • Batch launcher with virtual environment activation and auto-restart loop. |
| `DEPLOYMENT_RUNBOOK.md` | Production Operations Manual | • Step-by-step instructions for Windows Server 2022/2025.<br>• NSSM Windows Service installation (`BitdexMT5Gateway`).<br>• WireGuard VPN tunnel configuration.<br>• Troubleshooting matrix and health check procedures. |

### 2. Official Exness Trader API (Ed25519 Protocol)

Implemented in `backend/app/services/exness/trader_api_adapter.py`:

```
Client Request (GET / POST)
        │
        ▼
Compute SHA-256 Body Hash  ──►  Empty GET: "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"
        │
        ▼
Construct EXN-DATA JSON    ──►  { "api_key": ..., "timestamp": ..., "body_hash": ..., "path": ... }
        │
        ▼
Base64URL Encode (No Pad)  ──►  EXN-DATA Header
        │
        ▼
Sign with Ed25519 Private Key
        │
        ▼
Base64URL Encode (No Pad)  ──►  EXN-SIGN Header
        │
        ▼
Send HTTP Headers:
  EXN-API-KEY: exnsk-...
  EXN-DATA: eyJhcGlfa2V5Ijoi...
  EXN-SIGN: Jd91Fks...
```

- **DNS Gateway Access Point Discovery**:
  `GET /v1/trading/access-point?account_id={account_id}` resolves regional cluster URLs (`https://{region}.trading.exness-api.com`) dynamically with signed headers.
- **WebSocket Streaming**:
  Signed GET headers for `/ws/ticks` handshake, with standardized subscription frames for instruments (`BTCUSDm`, `XAUUSDm`, etc.) and transactions.

### 3. Safety Controls & Fail-Closed Behavior

1. **Global Safety Locks Active**:
   - `live_trading_locked = True`
   - `emergency_lock_active = True`
   - `read_only_mode = True`
2. **Disconnected Bridge Fail-Closed**:
   - When the Windows MT5 Gateway service is unreachable, the API returns **HTTP 503 `MT5_TERMINAL_UNAVAILABLE`**.
   - Zero balances or quotes are fabricated.
3. **Tenant & Environment Isolation**:
   - Customer accounts and Administrator accounts are strictly segregated.
   - Demo and Real accounts render on separate status cards (`active_demo_connection` vs `active_real_connection`) without data cross-contamination.

---

## Acceptance Test Suite Results (12/12 Passed)

Automated test runner: `/opt/tauric-platform-staging/backend/test_phase4_3_acceptance.py`

| # | Test Invariant | Result | Verification Details |
| :---: | :--- | :---: | :--- |
| **1** | Windows MT5 Gateway Package & Architecture | **PASSED** | Dual-environment models, PowerShell automation, and endpoints verified. |
| **2** | DEMO MT5 Trade Mode (`trade_mode=0`) Guard | **PASSED** | DEMO adapter enforces strict environment matching and rejects live accounts. |
| **3** | REAL MT5 Read-Only Ingestion (Account `460310009`) | **PASSED** | Target account ingested in AES-256 vault; read-only lock active. |
| **4** | Account / Environment Card Separation | **PASSED** | Demo and Real status cards rendered distinctly without data leakage. |
| **5** | Secure Linux-to-Windows Gateway IPC | **PASSED** | 64-char high-entropy token, constant-time verification header configured. |
| **6** | Official Exness Trader API Ed25519 Signing | **PASSED** | `EXN-API-KEY`, `EXN-DATA`, `EXN-SIGN`, SHA-256 body hash match official spec. |
| **7** | DNS Gateway Access Point Discovery Protocol | **PASSED** | `GET /v1/trading/access-point?account_id=...` with signed headers verified. |
| **8** | Authenticated WebSocket Handshake & Frames | **PASSED** | Signed GET handshake, `/ws/ticks`, and transaction event frames verified. |
| **9** | Payments API Balance & Personal Area Integration | **PASSED** | Wallets reconciled; official PA deposit redirect (`https://my.exness.com/pa/deposit`) verified. |
| **10** | Strict Multi-Tenant Account Isolation | **PASSED** | Zero admin leakage to customers; cross-tenant mutation strictly blocked (404). |
| **11** | Disconnected Gateway Fail-Closed Handling | **PASSED** | HTTP 503 `MT5_TERMINAL_UNAVAILABLE` returned; zero fake balances invented. |
| **12** | Platform Global Safety Locks Active | **PASSED** | `live_trading_locked=True` and `read_only_mode=True` enforced; real orders blocked. |

---

## Windows Server Deployment Instructions

To bring the live Windows MT5 Gateway terminal bridge online on the Windows host:

1. Copy the `gateway/windows/` directory to `C:\BitdexGateway\` on the Windows Server.
2. Open PowerShell as Administrator and run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
   cd C:\BitdexGateway
   .\setup_windows_gateway.ps1
   ```
3. Set the shared secret token in environment:
   ```powershell
   [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_AUTH_TOKEN", "6372b1ea1cd5cdd49100d5369e30bb6b78ca5233bca48d229ac018ee14e7d928", "Machine")
   ```
4. Start the service:
   ```powershell
   nssm start BitdexMT5Gateway
   ```
5. Verify health:
   ```powershell
   curl http://127.0.0.1:8095/health -Headers @{"X-Gateway-Auth-Token"="6372b1ea1cd5cdd49100d5369e30bb6b78ca5233bca48d229ac018ee14e7d928"}
   ```
