# BITDEX — WireGuard & MT5 Gateway Verification Report (Phase 2)

**Linux Staging Endpoint:** `10.88.0.1` (Designated)  
**Windows Host Endpoint:** `10.88.0.2` (Designated)  
**Gateway Target Port:** `8001` / `8095`  
**Date:** November 5, 2026  
**Status:** **FAILED (Network/Tunnel) / PASSED (Local Logic Unit Tests)**

---

## 1. Network & Tunnel Verification

| Check | Expected | Actual Evidence | Result |
| :--- | :--- | :--- | :--- |
| **WireGuard Package** | Installed on Linux | `wg: command not found` | **FAILED** |
| **Interface `wg0`** | `10.88.0.1/24` UP | `Device "wg0" does not exist.` | **FAILED** |
| **WireGuard Handshake** | Latest handshake < 180s | No handshake / interface absent | **FAILED** |
| **ICMP Connectivity** | Ping `10.88.0.2` 0% loss | 2 packets transmitted, 0 received, 100% loss | **FAILED** |
| **Health Check (Remote)** | HTTP 200 from `10.88.0.2:8001/health` | Network unreachable / timed out | **FAILED** |
| **Health Check (Local Config)** | HTTP 200 from `127.0.0.1:8095/health` | Connection refused (port not listening) | **FAILED** |
| **Public Exposure Check** | Port 8095 / 8001 not open to 0.0.0.0 | `ss -tulpn` shows neither 8095 nor 8001 listening on public interfaces | **PASSED** |

---

## 2. In-Process Gateway Software Verification (Unit Level)

Execution of `test_phase4_4_connectivity.py` evaluated the Python gateway software in isolation:

1. **Package Completeness:**
   All 7 deployment artifacts present in `/opt/tauric-platform-staging/gateway/windows/`:
   - `mt5_gateway_server.py`
   - `setup_windows_gateway.ps1`
   - `run_gateway.bat`
   - `install_service_nssm.bat`
   - `uninstall_service_nssm.bat`
   - `DEPLOYMENT_RUNBOOK.md`
   - `requirements.txt`
   *(Status: PASSED)*

2. **Security & Cryptography:**
   - **Rotated Token Authentication:** High entropy 384-bit token verified. *(PASSED)*
   - **Revoked Token Rejection:** Known compromised/revoked tokens explicitly rejected with HTTP 401. *(PASSED)*
   - **Timing-Attack Resistance:** Token validation utilizes constant-time `hmac.compare_digest`. *(PASSED)*
   - **Fail-Closed Behavior:** Gateway adapter returns HTTP 503 `MT5_TERMINAL_UNAVAILABLE` when terminal or bridge is down; zero fake data emitted. *(PASSED)*

---

## 3. Conclusion

The software architecture and security guards of the MT5 Gateway are sound and fully tested at the unit/mock layer. However, the physical WireGuard tunnel and communication bridge to the external Windows host are **OFFLINE**.
