# BITDEX — Existing Windows VPS Audit & Infrastructure Discovery (Phase 1)

**Target Host:** Windows Server (reported provisioned)  
**Verification Host:** Linux Staging Server (`169.58.218.168`)  
**Date:** November 5, 2026  
**Status:** **FAILED / BLOCKED**

---

## 1. Executive Summary

An exhaustive probe was conducted from the Linux staging server (`169.58.218.168`) to locate, inspect, and verify the existing Windows VPS reported as already provisioned.

**Result:** The Windows VPS is completely unreachable from the Linux staging environment. No WireGuard tunnel is active on the Linux host, no host routes exist to `10.88.0.2`, and no external IP/credentials for RDP or WinRM are configured in the repository or environment files.

---

## 2. Detailed Technical Findings

| Inspection Item | Command / Check Executed | Actual Observed Output | Status |
| :--- | :--- | :--- | :--- |
| **1. OS & System Health** | Check network reachability to Windows host | Unreachable; ping `10.88.0.2` resulted in 100% packet loss | **BLOCKED** |
| **2. Exness MT5 Desktop Installation** | Check filesystem / processes on Windows host | No remote management channel (WinRM/RDP) available | **BLOCKED** |
| **3. MT5 Terminal Process Status** | Query `terminal64.exe` process status | Unable to connect to host | **BLOCKED** |
| **4. Existing Gateway Service Status** | Probe `http://10.88.0.2:8001/health` & `http://127.0.0.1:8095/health` | Both connection attempts timed out / refused | **FAILED** |
| **5. Python Environment & Deps** | Verify Python 64-bit & `MetaTrader5` package | Local Linux test confirmed `MetaTrader5` unavailable on Linux; Windows host unreachable | **BLOCKED** |
| **6. Gateway Configuration & Env** | Read `/opt/tauric-platform-staging/backend/.env` | `EXNESS_MT5_GATEWAY_URL=http://127.0.0.1:8095`, `EXNESS_GATEWAY_AUTH_TOKEN` set. Note discrepancy with `10.88.0.2:8001` | **FAILED** (Mismatched) |
| **7. Windows Firewall Rules** | Audit Windows NetFirewallRule `BITDEX_MT5_GATEWAY_INGRESS` | Requires administrative access on Windows machine | **BLOCKED** |
| **8. WireGuard Service & Tunnel** | Run `wg show`, `ip addr show wg0` on staging | `bash: wg: command not found`; `Device "wg0" does not exist`; `/etc/wireguard` missing | **FAILED** |
| **9. Linux-to-Windows Connectivity** | Ping `10.88.0.2`, curl port 8001 / 8095 | `2 packets transmitted, 0 received, 100% packet loss` | **FAILED** |
| **10. Gateway Auth & Heartbeat** | Send authenticated request with token | Unable to establish TCP handshake with remote daemon | **BLOCKED** |

---

## 3. Discrepancies & Root Causes

1. **Missing WireGuard Infrastructure on Linux:**
   The staging machine (`169.58.218.168`) does not have `wireguard-tools` installed, no `wg0` network interface configured, and no WireGuard configuration files in `/etc/wireguard/`.
2. **Missing Host Routing:**
   `ip route` shows no route for `10.88.0.0/24`. Any packet destined for `10.88.0.2` is routed out to the default gateway and discarded.
3. **No Connection Credentials for Windows:**
   There are no IP addresses, hostnames, SSH keys, WinRM tokens, or RDP credentials stored in `/opt/tauric-platform-staging/` or root environments.

---

## 4. Required Action to Unblock

1. Install and configure WireGuard on `169.58.218.168`:
   ```bash
   apt-get update && apt-get install -y wireguard
   # Place wg0.conf configuring 10.88.0.1/24 peering with Windows VPS public IP
   systemctl enable --now wg-quick@wg0
   ```
2. On the Windows VPS:
   - Execute `gateway/windows/setup_windows_gateway.ps1`.
   - Ensure the WireGuard Windows client is active with IP `10.88.0.2/24`.
   - Start the service using `install_service_nssm.bat`.
