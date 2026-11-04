# BITDEX — Phase 12: Gateway Endpoint Reconciliation

**Configured Env:** `EXNESS_MT5_GATEWAY_URL=http://127.0.0.1:8095`  
**Specification Reference:** `http://10.88.0.2:8001`  
**Local Linux Port 8001 Conflict:** Occupied by PID `556493` (`/opt/tauric-platform/backend`)  
**Date:** November 5, 2026  

---

## 1. Discrepancy Analysis

An apparent conflict existed between three values:
1. `EXNESS_MT5_GATEWAY_URL=http://127.0.0.1:8095` in `/opt/tauric-platform-staging/backend/.env`.
2. `http://10.88.0.2:8001` designated as the WireGuard tunnel endpoint.
3. `127.0.0.1:8001` listening locally on Linux for the production Tauric backend.

### Investigation Findings
- **Local Port 8095:** Nothing listens on `127.0.0.1:8095` on Linux. In `setup_windows_gateway.ps1`, the default port parameter is set to `8095` (`param([string]$GatewayPort = "8095")`).
- **Local Port 8001:** Port `8001` on Linux is used exclusively by the local uvicorn process for Tauric production backend (`127.0.0.1:8001`). Thus, the Linux staging server cannot bind a local gateway on `127.0.0.1:8001`.
- **Target Windows Host:** On the remote Windows host, the port can be either `8001` or `8095`. Because traffic travels inside the private WireGuard tunnel (`10.88.0.2`), listening on `10.88.0.2:8001` or `10.88.0.2:8095` on the Windows host will **NOT** conflict with Linux's local `127.0.0.1:8001`.

---

## 2. Architectural Resolution Options

### Recommended Architecture (Direct Private Tunnel Routing):
- **Windows Host Listener:** Bind `mt5_gateway_server.py` to `10.88.0.2:8001` (or `0.0.0.0:8001` restricted by Windows Firewall to `10.88.0.1`).
- **Linux Backend Configuration:**
  Update `/opt/tauric-platform-staging/backend/.env`:
  ```bash
  EXNESS_MT5_GATEWAY_URL=http://10.88.0.2:8001
  ```
- **Advantages:**
  1. Direct, clean routing over the encrypted WireGuard tunnel.
  2. No secondary local proxy or iptables port redirection needed.
  3. Zero port collision with Linux's `127.0.0.1:8001` (since `10.88.0.2` is a distinct IP).

### Alternative Architecture (Local Port Forwarding via Loopback 8095):
If the backend must continue pointing to `http://127.0.0.1:8095`:
- Create a lightweight forwarder (e.g. systemd socket/nginx stream) on Linux:
  `127.0.0.1:8095` $\rightarrow$ `10.88.0.2:8001`.
- **Evaluation:** Unnecessary complexity. Direct communication to `http://10.88.0.2:8001` is standard for WireGuard topology.

---

## 3. Decision & Safe Implementation Rule
Do **NOT** change `EXNESS_MT5_GATEWAY_URL` in `.env` immediately.  
Only update `EXNESS_MT5_GATEWAY_URL=http://10.88.0.2:8001` **after** the WireGuard handshake between `10.88.0.1` and `10.88.0.2` has succeeded and `ping 10.88.0.2` returns `0% packet loss`.
