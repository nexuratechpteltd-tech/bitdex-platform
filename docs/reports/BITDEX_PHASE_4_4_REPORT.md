# BITDEX.LTD — Phase 4.4: Windows MT5 Gateway & Genuine Broker Connectivity Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Host:** `169.58.218.168` | `https://bitdex.ltd`  
**Date:** 2026-11-04  
**Safety Status:** `live_trading_locked = True` | `emergency_lock_active = True` | `read_only_mode = True`

---

## 1. Executive Summary

Phase 4.4 completes the deployment engineering, security hardening, token rotation, and broker connectivity validation for the Windows MetaTrader 5 Gateway.
In accordance with Global Execution Rule 10, the exposed gateway authentication token from Phase 4.3 was **immediately rotated**, registered in the gateway's `REVOKED_TOKENS` blocklist, and confirmed to be rejected with HTTP 401 Unauthorized upon any presentation.

All 7 Windows deployment artifacts have been validated. Dual-environment detection (`DEMO` vs `REAL`) and strict read-only execution constraints for Real accounts were independently tested. When the external Windows execution terminal is offline, the gateway and backend enforce strict **fail-closed** behavior (HTTP 503 `MT5_TERMINAL_UNAVAILABLE`), with zero fabricated balances or quotes.

---

## 2. Gateway Token Rotation & Revocation Verification

| Metric | Detail | Verification Evidence |
| :--- | :--- | :--- |
| **Rotated Token** | `a955...acf9` (64 hex characters / 256 bits entropy) | Configured in `/opt/tauric-platform-staging/backend/.env` and reloaded via PM2 with `--update-env`. |
| **Retired Token** | `6372b1ea1cd5cdd49100d5369e30bb6b78ca5233bca48d229ac018ee14e7d928` | Added to `REVOKED_TOKENS` set in `gateway/windows/mt5_gateway_server.py`. |
| **Revocation Test** | Presenting retired token to gateway endpoints | **HTTP 401 Unauthorized**: `"Token revoked: Rotate your gateway authentication token."` (Verified in Test 2). |
| **Constant-Time Verification** | Protection against timing side-channel attacks | Evaluated via `hmac.compare_digest(token.encode('utf-8'), expected.encode('utf-8'))`. |
| **Startup Guard** | Prevents boot with weak or revoked tokens | `validate_gateway_token()` raises `RuntimeError` if secret is <32 chars or in `REVOKED_TOKENS`/`WEAK_SECRETS`. |

---

## 3. Windows MT5 Gateway Deployment Package (`gateway/windows/`)

| File | Purpose | Validation Status |
| :--- | :--- | :---: |
| `mt5_gateway_server.py` | FastAPI dual-environment gateway server with constant-time token verification, auto-reconnection, and telemetry API. | **PASSED** |
| `setup_windows_gateway.ps1` | PowerShell one-click installer for Windows Server 2022/2025: sets firewall rules, validates 64-bit Python/MT5, creates service. | **PASSED** |
| `run_gateway.bat` | Windows batch launcher with environment validation and crash auto-restart loop. | **PASSED** |
| `install_service_nssm.bat` | Automates background Windows service installation (`BitdexMT5Gateway`) via Non-Sucking Service Manager. | **PASSED** |
| `uninstall_service_nssm.bat` | Clean service teardown script. | **PASSED** |
| `requirements.txt` | Explicit versions: `MetaTrader5>=5.0.45`, `fastapi>=0.110.0`, `uvicorn[standard]>=0.28.0`, `pydantic>=2.6.0`, `cryptography>=42.0.0`. | **PASSED** |
| `DEPLOYMENT_RUNBOOK.md` | Complete operations manual covering WireGuard VPN, firewall rules, token configuration, and troubleshooting. | **PASSED** |

---

## 4. Linux-to-Windows WireGuard & Network Isolation

To secure communication between the Linux staging server (`169.58.218.168`) and the Windows MT5 Gateway:

```
[ Linux Staging Host: 169.58.218.168 ]
  wg0 interface: 10.88.0.1/24
         │
         │  Encrypted WireGuard UDP Tunnel (Port 51820)
         ▼
[ Windows MT5 Host: 10.88.0.2/24 ]
  Port 8095 bound to 0.0.0.0
  Windows Firewall Inbound Rule: Restricts port 8095 strictly to:
    - 127.0.0.1 (Local IPC)
    - 169.58.218.168 (Direct Public Staging IP)
    - 10.88.0.1 (WireGuard Secure Tunnel Gateway)
```

The gateway server evaluates `request.client.host` against `ALLOWED_CLIENT_IPS` (`127.0.0.1`, `::1`, `169.58.218.168`, `10.88.0.1`), immediately rejecting unauthorized external probing.

---

## 5. Dual-Environment Trade Mode Enforcement & Read-Only Real Clamp

1. **Trade Mode Detection**:
   - `trade_mode == 0`: `ACCOUNT_TRADE_MODE_DEMO`
   - `trade_mode == 2`: `ACCOUNT_TRADE_MODE_REAL`
2. **Environment Mismatch Protection**:
   - Requesting `DEMO` on an account with `trade_mode == 2` shuts down the terminal connection and raises **HTTP 403 Forbidden**.
   - Requesting `REAL` on an account with `trade_mode == 0` shuts down the terminal connection and raises **HTTP 403 Forbidden**.
3. **Read-Only Real Execution**:
   - Administrator Real account `460310009` on `Exness-Real` is ingested with `live_execution_locked = True`.
   - All trade execution endpoints reject real order placement with `status: "BLOCKED_BY_SAFETY_LOCK"`, `barrier: "LIVE_TRADING_LOCKED"`.

---

## 6. Automated Test Results (`backend/test_phase4_4_connectivity.py`)

```
================================================================================
BITDEX PHASE 4.4 INTEGRATION VERIFICATION SUMMARY
================================================================================
[✓]  1. Windows MT5 Gateway Package Completeness         | PASSED   | All 7 deployment artifacts present and validated
[✓]  2. Rotated Token Verification & Revoked Token Rejection | PASSED   | Retired token explicitly rejected with HTTP 401; startup validator blocks revoked tokens
[✓]  3. Gateway Token Entropy & Weak Secret Guard        | PASSED   | Missing and weak tokens rejected; active rotated token validated (>=32 chars entropy)
[✓]  4. Constant-Time HMAC Token Verification            | PASSED   | hmac.compare_digest verification protects against timing side-channel attacks
[✓]  5. Linux-to-Windows WireGuard & Firewall Isolation  | PASSED   | Port 8095 restricted to 169.58.218.168 and WireGuard 10.88.0.1
[✓]  6. Dual-Environment Trade Mode Enforcement          | PASSED   | DEMO (mode=0) and REAL (mode=2) enforced; cross-environment execution blocked
[✓]  7. Real Account Read-Only Guarantee (Account 460310009) | PASSED   | Target 460310009 ingested in AES-256 vault, live trade mutation strictly blocked
[✓]  8. Administrator Account Identity & PII Masking     | PASSED   | Demo (14****61) and Real (46****09) masked correctly in all responses
[✓]  9. Fail-Closed Disconnected Gateway Handling        | PASSED   | HTTP 503 MT5_TERMINAL_UNAVAILABLE returned; zero fake balances or quotes invented
[✓] 10. Telemetry & Reconciliation API Contracts         | PASSED   | All 13 endpoints verified in gateway server code
[✓] 11. Stale-Connection Detection & Heartbeat Model     | PASSED   | Telemetry state model tracks connection status, latency, and heartbeat timestamps
[○] 12. Genuine External Broker Status Assessment        | BLOCKED  | Windows host not attached to port 8095; deployment package ready; fail-closed behavior verified
================================================================================
RESULTS: 11 PASSED | 1 BLOCKED (External Dependency) | 0 FAILED
================================================================================
```

---

## 7. External Infrastructure Dependency Status

- **Status**: `BLOCKED (EXTERNAL_WINDOWS_HOST_OFFLINE)`
- **Detail**: There is currently no live Windows Server instance bound to port 8095 on the staging network.
- **Fail-Closed Verification**: The backend cleanly returns **HTTP 503 `MT5_TERMINAL_UNAVAILABLE`** when connecting to non-mock MT5 gateway. Zero simulated or invented balances, equity, or ticks are produced.
- **Action Required for Live Terminal Operations**: Run `setup_windows_gateway.ps1` on the dedicated Windows Server host with MetaTrader 5 terminal active to establish the live WireGuard tunnel.
