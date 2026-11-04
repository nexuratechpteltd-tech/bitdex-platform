# BITDEX — Phase 12: Linux Infrastructure Audit

**Server:** Linux Staging Server (`169.58.218.168` / `vmi3525521`)  
**Audit Date:** November 5, 2026  
**Auditor:** Antigravity / Engineering Team  
**Scope:** Kernel, Network, Firewall, WireGuard Package, Gateway Port/Process Inspection  

---

## 1. System & OS Discovery

| Parameter | Observed Value | Status |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 24.04.4 LTS (Noble Numbat) | **PASSED** |
| **Linux Kernel** | `6.8.0-147-generic #147-Ubuntu SMP PREEMPT_DYNAMIC` x86_64 | **PASSED** (WireGuard kernel module supported) |
| **Hostname** | `vmi3525521` (`169.58.218.168`) | **PASSED** |
| **Hardware Resources** | 4 vCPU AMD EPYC, 7.8 GiB RAM, ~16% RAM utilization | **HEALTHY** |

---

## 2. WireGuard Package & Interface Availability

| Inspection Item | Command Executed | Result | Status |
| :--- | :--- | :--- | :--- |
| **WireGuard Tools (`wg`)** | `which wg` / `dpkg -l \| grep wireguard` | Not installed; command `wg` not found | **FAILED (Missing Package)** |
| **WireGuard Interface (`wg0`)** | `ip -br addr` | Interface `wg0` absent; only `lo` and `eth0` present | **FAILED (No Interface)** |
| **WireGuard Configurations** | `ls -la /etc/wireguard` | Directory does not exist | **FAILED (No Config)** |
| **WireGuard Systemd Unit** | `systemctl list-unit-files \| grep wg` | Unit `wg-quick@.service` not installed | **FAILED** |

---

## 3. Network Interfaces, Routes & Firewall (UFW)

### 3.1 Network Interfaces
- `eth0`: `169.58.218.168/17` (Public gateway: `169.58.128.1 dev eth0`)
- `lo`: `127.0.0.1/8`
- Route for `10.88.0.0/24`: **MISSING**. Any packet addressed to `10.88.0.2` exits through the default public route and is dropped.

### 3.2 UFW Firewall Rules Audit
- **Default Policy:** `deny (incoming)`, `allow (outgoing)`, `disabled (routed)`
- **Open TCP Ports:**
  - `22/tcp` (SSH) — ALLOW IN Anywhere
  - `80/tcp`, `443/tcp` (Web) — ALLOW IN Anywhere
  - `33900/tcp` (Bitdex Dashboard Next.js) — ALLOW IN Anywhere
  - `33800/tcp` (Bitdex Admin) — ALLOW IN Anywhere / cPanel proxy
  - `8080/tcp` — ALLOW IN Anywhere
- **WireGuard UDP Ingress (Port 51820 / Custom UDP):** **NOT OPEN**. If Linux is to accept incoming WireGuard handshakes or initiate UDP tunnel traffic through a restricted port, UFW must allow UDP traffic for the selected WireGuard port (e.g. `ufw allow 51820/udp`).

---

## 4. Local Ports & Process Inspection

### 4.1 Port `8095` Inspection
- **Listening Process:** **NONE**. `ss -tulpn | grep 8095` returned zero listeners.
- **Configured Usage:** `EXNESS_MT5_GATEWAY_URL=http://127.0.0.1:8095` in `/opt/tauric-platform-staging/backend/.env`.
- **Verdict:** Port `8095` has **NO** local service running on the Linux host. It was intended either as the direct gateway listening port on Windows or a local reverse proxy forwarder.

### 4.2 Port `8001` Inspection
- **Listening Process:** Local Python Uvicorn process (PID `556493`) running `/opt/tauric-platform/backend/app.main:app` (Tauric Production backend on `127.0.0.1:8001`).
- **Verdict:** Port `8001` on `127.0.0.1` is **ALREADY IN USE** by the production Tauric backend. It is **NOT** an Exness MT5 Gateway port on the Linux host. The Exness MT5 Gateway port `8001` referred to in specs is intended to listen on the **remote Windows host (`10.88.0.2:8001`)** across the WireGuard tunnel.

---

## 5. Gateway Environment Variables

Inspected in `/opt/tauric-platform-staging/backend/.env`:
- `EXNESS_MT5_GATEWAY_URL`: `http://127.0.0.1:8095` *(Masked)*
- `EXNESS_GATEWAY_AUTH_TOKEN`: `[REDACTED_HIGH_ENTROPY_TOKEN_LEN_64]` *(Masked)*

---

## 6. Audit Conclusion
Linux staging host `169.58.218.168` is ready to install `wireguard-tools` via `apt-get install -y wireguard`, but requires the user's Windows VPS public IP and peer public key before activating `/etc/wireguard/wg0.conf`.
