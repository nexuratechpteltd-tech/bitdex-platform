# BITDEX — Windows MT5 Gateway Production Deployment Runbook (Phase 4.3)

## 1. Overview & Architectural Blueprint
The BITDEX Exness HFT architecture connects the Linux staging backend (`169.58.218.168`) to a dedicated Windows Server host running the official Exness MetaTrader 5 Terminal and the `bitdex-mt5-gateway` daemon.

Because MetaTrader 5 relies on Windows 64-bit native IPC APIs (`MetaTrader5` / `terminal64.exe`), a Windows environment is mandatory to interact directly with the broker terminal.

```
+-------------------------------------------------------------+
| Linux Staging Backend (169.58.218.168 / Ubuntu 24.04 LTS)   |
|   - tauric-backend-staging (FastAPI Port 8002)              |
|   - exness_hft.py (Risk Guards & Order Routing)             |
|   - live_trading_locked = True | emergency_lock_active = True|
+-------------------------------------------------------------+
                                |
                mTLS / Private WireGuard Tunnel
                  (TCP Port 8095 or Port 8443)
                                |
+-------------------------------------------------------------+
| Windows Gateway Host (Windows Server 2022 / 2025 Standard)  |
|   - MT5 Gateway Service (FastAPI / Uvicorn, Port 8095)      |
|   - X-Gateway-Auth-Token Authentication (Min 32 characters) |
|   - Python 3.11 / 3.12 (64-bit) with MetaTrader5 package    |
|   - Exness MT5 Terminal (DEMO execution / REAL read-only)   |
+-------------------------------------------------------------+
```

---

## 2. Windows Server Hardware & Software Prerequisites

- **Operating System:** Windows Server 2022 Standard / Datacenter or Windows 10/11 Pro (64-bit).
- **vCPU:** Minimum 2 vCPUs (4 dedicated recommended for sub-10ms tick streaming).
- **RAM:** Minimum 4 GB RAM (8 GB ECC recommended).
- **Storage:** 50 GB NVMe SSD.
- **Python Version:** Python 3.11.x or 3.12.x (64-bit). Ensure "Add Python to PATH" is selected during installation.
- **Broker Software:** Official Exness MetaTrader 5 Desktop Terminal.

---

## 3. Automated PowerShell Installation (One-Click)

On the Windows VPS, open PowerShell as **Administrator** and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd C:\bitdex-mt5-gateway
.\setup_windows_gateway.ps1 -GatewayPort 8095 -StagingIP 169.58.218.168 -TunnelIP 10.88.0.1
```

This automated script performs:
1. Verification of 64-bit Python architecture.
2. Installation of all pinned packages (`MetaTrader5`, `fastapi`, `uvicorn`, `cryptography`, `pydantic`).
3. Discovery and validation of `terminal64.exe`.
4. Generation and persistent system environment configuration of `EXNESS_GATEWAY_AUTH_TOKEN`.
5. Creation of Windows Advanced Firewall inbound rule restricting TCP 8095 strictly to `169.58.218.168` and `10.88.0.1`.
6. Self-test ping against `http://127.0.0.1:8095/health`.

---

## 4. Manual Configuration & Running as a Service

### Step 1: Install Exness MT5 Terminal
1. Download `exness5setup.exe` from the verified Exness client portal:
   `https://download.mql5.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe`
2. Install in portable mode:
   ```cmd
   exness5setup.exe /portable /dir:C:\ExnessMT5
   ```
3. Launch Exness MT5 and configure credentials:
   - **For Demo Environment:** Log into Administrator Demo account on `Exness-MT5Trial`.
   - **For Real Environment (Read-Only):** Log into Administrator Real account `460310009` on `Exness-Real`.
4. Confirm terminal status bar shows green signal bars with live tick data transfer.

### Step 2: Install as a Persistent Windows Service (NSSM)
To keep the gateway running 24/7 across Windows reboots and user logoffs:
```cmd
install_service_nssm.bat
```
To verify service status:
```powershell
Get-Service BitdexMT5Gateway
```

---

## 5. Dual-Environment Gateway Operation

### DEMO Account Operation
- The gateway verifies `acct_info.trade_mode == 0` (ACCOUNT_TRADE_MODE_DEMO).
- Confirms server is `Exness-MT5Trial` (or designated trial server).
- Streams live broker bid/ask ticks, position synchronization, and allows simulated demo testing.

### REAL Account Read-Only Monitoring (Target: 460310009)
- The gateway verifies `acct_info.trade_mode == 2` (ACCOUNT_TRADE_MODE_REAL).
- Validates account login `460310009` and server `Exness-Real`.
- **Strict Read-Only Guarantee:** The gateway daemon contains zero trade execution, order submission, or position close endpoints.
- Provides authentic broker balance, equity, free margin, leverage (risk clamped to 1:200), and quotes.
- Rejects any environment mismatch (attempting to connect a Real account in Demo mode throws `HTTP 403 Forbidden`).

---

## 6. Linux Staging Backend Configuration

Update `/opt/tauric-platform-staging/backend/.env`:
```env
EXNESS_MT5_GATEWAY_URL="http://<WINDOWS_VPS_IP_OR_TUNNEL>:8095"
EXNESS_GATEWAY_AUTH_TOKEN="<MATCHING_AUTH_TOKEN_FROM_SETUP>"
```

Reload backend process:
```bash
pm2 reload tauric-backend-staging
```

Verify end-to-end connectivity from Linux staging:
```bash
curl -H "X-Gateway-Auth-Token: <TOKEN>" http://<WINDOWS_VPS_IP_OR_TUNNEL>:8095/health
```

---

## 7. Heartbeat Monitoring & Auto-Reconnection

- The gateway includes an automatic heartbeat monitor.
- If the MetaTrader 5 terminal process disconnects from Exness servers, the gateway daemon automatically triggers `mt5.initialize()` with exponential backoff.
- The Linux staging backend checks `GET /health` and `GET /heartbeat` every 15 seconds. If 3 consecutive failures occur, the risk watchdog trips the circuit breaker to prevent stale order routing.
