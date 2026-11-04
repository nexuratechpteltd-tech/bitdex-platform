# BITDEX — Phase 12: Windows VPS Access & Verification Checklist

**Target:** Windows Server (MetaTrader 5 & Gateway Host)  
**Package Path:** `/opt/tauric-platform-staging/gateway/windows/`  
**Date:** November 5, 2026  
**Status:** **AWAITING USER ACCESS / BLOCKED**

---

## 1. Existing Repository Artifacts for Windows
All required automation and installation scripts exist in `/opt/tauric-platform-staging/gateway/windows/`:

1. `setup_windows_gateway.ps1`: Automated PowerShell installer (checks 64-bit Python, MT5 terminal paths, firewall rules, generates/loads `EXNESS_GATEWAY_AUTH_TOKEN`).
2. `mt5_gateway_server.py`: Hardened FastAPI MT5 gateway daemon binding to `0.0.0.0` or tunnel IP, validating `X-Gateway-Auth-Token` and client IP allowlist (`ALLOWED_CLIENT_IPS`).
3. `run_gateway.bat`: Interactive startup batch script with crash-loop protection.
4. `install_service_nssm.bat`: Service registration via Non-Sucking Service Manager (`BitdexMT5Gateway`).
5. `uninstall_service_nssm.bat`: Clean service uninstallation.
6. `DEPLOYMENT_RUNBOOK.md`: Step-by-step deployment runbook.
7. `requirements.txt`: Python package specifications (`MetaTrader5>=5.0.45`, `fastapi`, `uvicorn`, `pydantic`, `cryptography`).

---

## 2. Windows-Side Verification Checklist

Once remote administrative access to the Windows VPS (via RDP or PowerShell WinRM) is established, execute the following verification steps:

### Step 1: System & Architecture Verification
- [ ] OS: Windows Server 2022 or 2025 Standard / Datacenter (64-bit).
- [ ] Hardware: Minimum 2 vCPU, 4GB RAM (Recommended 4 vCPU, 8GB RAM).
- [ ] Verify 64-bit Python 3.11 or 3.12:
  ```powershell
  python --version
  python -c "import struct; print(struct.calcsize('P') * 8)" # Must print 64
  ```

### Step 2: Official Exness MT5 Desktop Installation
- [ ] Verify official Exness MT5 terminal executable exists at one of:
  - `C:\Program Files\Exness MetaTrader 5\terminal64.exe`
  - `C:\Program Files\MetaTrader 5\terminal64.exe`
  - `C:\ExnessMT5\terminal64.exe`
- [ ] Launch `terminal64.exe` manually once to initialize user profile.
- [ ] In MT5 Desktop: `Tools` -> `Options` -> `Expert Advisors`:
  - [x] Check **Allow algorithmic trading**.
  - [x] Check **Allow DLL imports**.

### Step 3: MetaTrader 5 Python Package Verification
- [ ] Verify the official MetaTrader5 Python package can link to the terminal:
  ```powershell
  python -c "import MetaTrader5 as mt5; print('MT5 version:', mt5.__version__); init = mt5.initialize(); print('MT5 init:', init); mt5.shutdown()"
  ```
  *(Must print `MT5 init: True` without DLL load error)*

### Step 4: WireGuard Windows Client Installation & Peering
- [ ] Install official WireGuard for Windows (`https://download.wireguard.com/windows-client/wireguard-installer.exe`).
- [ ] Generate Windows Keypair:
  ```powershell
  # In elevated cmd/powershell
  wg genkey | Tee-Object -Variable privkey | wg pubkey
  ```
- [ ] Configure `C:\Program Files\WireGuard\Data\Configurations\wg-bitdex.conf`:
  - Interface IP: `10.88.0.2/24`
  - Peer: Linux Staging (`169.58.218.168:51820`)
  - AllowedIPs: `10.88.0.0/24`
  - PersistentKeepalive: `25`
- [ ] Activate tunnel and verify ping to `10.88.0.1`.

### Step 5: Gateway Configuration & Service Startup
- [ ] Place `gateway/windows/` files in `C:\BitdexGateway\`.
- [ ] Configure environment variables (Machine scope):
  ```powershell
  [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_AUTH_TOKEN", "<ROTATED_TOKEN>", "Machine")
  [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_PORT", "8001", "Machine")
  [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_HOST", "10.88.0.2", "Machine")
  [Environment]::SetEnvironmentVariable("ALLOWED_CLIENT_IPS", "127.0.0.1,::1,10.88.0.1,169.58.218.168", "Machine")
  ```
- [ ] Configure Windows Firewall:
  ```powershell
  New-NetFirewallRule -DisplayName "BITDEX_GATEWAY_WIREGUARD" -Direction Inbound -LocalPort 8001 -Protocol TCP -Action Allow -RemoteAddress "10.88.0.1"
  ```
- [ ] Run `install_service_nssm.bat` to launch `BitdexMT5Gateway` as a Windows service.
- [ ] Test health endpoint from Windows host:
  ```powershell
  Invoke-RestMethod -Uri "http://10.88.0.2:8001/health" -Headers @{"X-Gateway-Auth-Token"="<ROTATED_TOKEN>"}
  ```
