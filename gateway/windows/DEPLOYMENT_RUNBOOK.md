# BITDEX — Windows MT5 Gateway Deployment Runbook

## 1. Overview
The BITDEX Exness HFT architecture connects the Linux staging backend (`169.58.218.168`) to a dedicated Windows VPS running the official Exness MetaTrader 5 Terminal and the `bitdex-mt5-gateway` daemon.

Because MetaTrader 5 requires Windows 64-bit native IPC APIs (`MetaTrader5.dll` / `terminal64.exe`), a Windows environment is mandatory to interact directly with the broker terminal.

---

## 2. Windows VPS Hardware & Software Requirements

- **Operating System:** Windows Server 2022 Datacenter or Windows 10/11 Pro (64-bit).
- **vCPU:** Minimum 2 vCPUs (4 recommended for tick-level orderbook streaming).
- **RAM:** Minimum 4 GB RAM.
- **Disk:** 50 GB NVMe SSD.
- **Python Version:** Python 3.11.x or 3.12.x (64-bit). Ensure "Add Python to PATH" is checked during installation.
- **Broker Software:** Exness MetaTrader 5 Desktop Terminal (downloaded directly from Exness Client Portal).

---

## 3. Step-by-Step Gateway Installation on Windows VPS

### Step 1: Install Exness MT5 Terminal
1. Download `metatrader5setup.exe` from the Exness member area.
2. Install to default path: `C:\Program Files\Exness MetaTrader 5\terminal64.exe`.
3. Launch Exness MT5 and log into your **Exness Demo Account**:
   - Login: `<your-demo-login>` (e.g., `149827361`)
   - Password: `<your-demo-password>`
   - Server: `Exness-MT5Trial` (or designated trial server)
4. Ensure the status bar in the bottom right corner turns green with data transfer (e.g. `124/18 kb`).

### Step 2: Install Gateway Python Dependencies
Open PowerShell or Command Prompt as Administrator:
```cmd
cd C:\bitdex-mt5-gateway
pip install -r requirements.txt
```

### Step 3: Run the Gateway Daemon
```cmd
run_gateway.bat
```
The gateway will start listening on port `8095` with endpoint:
`http://0.0.0.0:8095`

---

## 4. Secure Communication & Network Configuration

### Option A: Cloudflare Tunnel / Tailscale / Wireguard (Recommended)
1. Install Wireguard or Cloudflare Tunnel on the Windows VPS.
2. Expose port `8095` only to the Linux Staging Server IP (`169.58.218.168`).
3. Set Windows Firewall rule:
   ```powershell
   New-NetFirewallRule -DisplayName "BITDEX MT5 Gateway" -Direction Inbound -LocalPort 8095 -Protocol TCP -Action Allow -RemoteAddress 169.58.218.168
   ```

### Option B: TLS Reverse Proxy (Caddy / Nginx on Windows)
1. Use Caddy on Windows with an SSL certificate for `mt5-gateway-staging.bitdex.ltd`.
2. Reverse proxy `https://mt5-gateway-staging.bitdex.ltd` -> `http://127.0.0.1:8095`.

---

## 5. Linux Staging Backend Configuration

Once the Windows Gateway is reachable, set the following environment variables in `/opt/tauric-platform-staging/backend/.env`:

```env
# Exness MT5 Gateway Configuration
EXNESS_MT5_GATEWAY_URL="http://<WINDOWS_VPS_IP_OR_HOSTNAME>:8095"
EXNESS_GATEWAY_AUTH_TOKEN="bitdex_mt5_gateway_secure_ipc_token_2026"
```

Reload backend on staging:
```bash
pm2 reload tauric-backend-staging
```

---

## 6. Secure Demo Credential Entry (Zero Chat Exposure)

Do **NOT** paste credentials into chat, commit them to git, or store them in plaintext files.

To securely connect the demo account:
1. Log in to the BITDEX Customer Portal or use the authenticated REST API endpoint:
   ```bash
   POST https://bitdex.ltd/api/v1/hft/exness/demo/connect
   Authorization: Bearer <CUSTOMER_JWT_TOKEN>
   Content-Type: application/json

   {
     "account_login": "149827361",
     "password": "<DEMO_PASSWORD>",
     "server_name": "Exness-MT5Trial",
     "use_mock": false
   }
   ```
2. The password is immediately encrypted into the database using AES-256-GCM via `ExnessCredentialVault`.
3. The password is never logged and never stored in plaintext.
4. The gateway verifies the account is strictly `DEMO` before completing authentication.
