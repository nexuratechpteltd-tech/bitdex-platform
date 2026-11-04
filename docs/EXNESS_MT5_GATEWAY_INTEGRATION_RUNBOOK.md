# EXNESS MT5 GATEWAY INTEGRATION RUNBOOK
## Authoritative Infrastructure, Security, Deployment & Integration Specification
**Target Platform:** BITDEX Institutional Trading Architecture  
**Document Revision:** 3.0  
**Status:** Pre-Deployment Runbook / Readiness Specification  
**Security Classification:** Highly Confidential — Internal Engineering Runbook  

---

## 1. Executive Overview & Gateway Architecture

The BITDEX platform utilizes a decoupled, asynchronous gateway architecture to bridge Linux-based quantitative risk engines with MetaTrader 5 (MT5) execution terminals. Because the official `MetaTrader5` Python package requires Windows native API libraries (`metatrader.dll`), the broker execution gateway runs on a dedicated Windows VPS host.

```
+-------------------------------------------------------------+
| Linux Staging Backend (169.58.218.168 / Ubuntu 24.04 LTS)   |
|   - tauric-backend-staging (FastAPI Port 8002)             |
|   - exness_hft.py (Risk Guards & Order Routing)             |
|   - live_trading_locked = True | emergency_lock_active = True|
+-------------------------------------------------------------+
                                |
                mTLS / Private WireGuard Tunnel
             (Encrypted Port 8443 or Custom Port)
                                |
+-------------------------------------------------------------+
| Windows Gateway Host (Windows Server 2022 / 2025 Standard)  |
|   - MT5 Gateway Service (FastAPI / Uvicorn + Windows Service)|
|   - X-Gateway-Auth-Token Authentication                     |
|   - Python 3.11/3.12 (64-bit) with MetaTrader5 package      |
|   - Exness MT5 Terminal (Dedicated DEMO Account)            |
+-------------------------------------------------------------+
```

---

## 2. Windows VPS Hardware & Network Requirements

| Specification | Minimum Requirement | Institutional Recommendation | Rationale |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows Server 2022 (64-bit) | Windows Server 2025 Datacenter | Native MT5 COM/API stability and security patching |
| **CPU** | 2 vCPUs (x86_64) | 4 vCPUs Dedicated (High Frequency >= 3.4 GHz) | Low jitter for tick streaming & queue processing |
| **Memory (RAM)** | 4 GB | 8 GB ECC RAM | Avoid memory starvation during historical rate ingestion |
| **Storage** | 60 GB NVMe SSD | 120 GB High-IOPS NVMe | Fast SQLite caching and terminal log persistence |
| **Colocation / Region** | London (LD4) or Amsterdam (AMS) | London (LD4 / Equinix) | Proximity to Exness MT5 trading servers (< 3ms latency) |
| **Network Security** | Static IPv4 with Firewall | WireGuard / IPsec tunnel to Linux Staging host | Zero public HTTP exposure |

---

## 3. Exness MT5 Terminal Installation & Configuration

1. **Terminal Download**:
   Download the official Exness MT5 setup executable from the verified Exness broker portal:
   `https://download.mql5.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe`
2. **Installation Directory**:
   Install the terminal in isolated portable mode:
   ```cmd
   exness5setup.exe /portable /dir:C:\ExnessMT5
   ```
3. **Terminal Configuration (`terminal.ini`)**:
   - Enable automated algorithmic trading: `Allow Live Trading = True` (for DEMO account execution only).
   - Configure WebRequest permissions: Restrict to `https://127.0.0.1` and internal tunnel subnets.
   - Set maximum bars in chart: `50,000` (conserves RAM and avoids tick processing bottlenecks).
   - Enable portable log rotation.

---

## 4. Exness DEMO Account Provisioning & Security Standards

In accordance with strict security rules, **LIVE broker accounts are strictly prohibited** during Phase 3.0:
- **Account Type**: Exness `Raw Spread` or `Zero` DEMO account.
- **Server Name**: `Exness-MT5Trial` or `Exness-MT5Trial2`.
- **Base Currency**: `USD`.
- **Initial Demo Balance**: `$5,000.00` to `$10,000.00` (funded via Exness Personal Area Demo deposit).
- **Demo Leverage**: Clamped to a maximum of `1:200` (to match platform margin risk models).
- **Credential Storage**:
  - Broker account credentials (`login`, `password`, `server`) must NEVER be hardcoded in git repositories or shell scripts.
  - On the Windows VPS, credentials must be configured via environment variables or encrypted Windows DPAPI credential vaults:
    ```cmd
    set EXNESS_ACCOUNT_LOGIN=12345678
    set EXNESS_ACCOUNT_PASSWORD=<STORED_IN_SECURE_VAULT>
    set EXNESS_ACCOUNT_SERVER=Exness-MT5Trial
    set EXNESS_EXPECTED_ACCOUNT_TYPE=DEMO
    ```

---

## 5. Gateway Service Installation & Hardening

The gateway service wraps the MetaTrader5 Python API in a hardened asynchronous HTTP/WebSocket service:

### 5.1 Service Dependencies (`requirements.txt`)
```
MetaTrader5>=5.0.45
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
cryptography>=42.0.0
websockets>=12.0
```

### 5.2 Mandatory Security Gates in Gateway Implementation
1. **Header-Based Authentication**:
   Every incoming request must provide:
   `X-Gateway-Auth-Token: <STRONG_HIGH_ENTROPY_TOKEN>` (minimum 48 hex characters).
   Requests without this header or with incorrect tokens must return `HTTP 401 Unauthorized` immediately.
2. **Strict Account Type Validation**:
   Upon calling `mt5.account_info()`, the gateway must inspect `account_info.trade_mode`:
   - `mt5.ACCOUNT_TRADE_MODE_DEMO`: Permitted.
   - `mt5.ACCOUNT_TRADE_MODE_REAL` / `ACCOUNT_TRADE_MODE_CONTEST`: **REJECT & HALT STARTUP**.
   The service must immediately terminate and refuse connections if connected to a real broker account.
3. **Fail-Closed MT5 Error Handling**:
   If `mt5.initialize()` fails or the terminal loses connection to the broker:
   - The service must return `HTTP 503 Service Unavailable` with details `{ "status": "GATEWAY_DISCONNECTED", "mt5_last_error": mt5.last_error() }`.
   - It must NEVER return fabricated or empty zeroed account responses.

---

## 6. Secure Transport & Firewall Configuration

1. **Private Tunnel Setup (WireGuard)**:
   - Configure a private point-to-point WireGuard tunnel between the Linux staging server (`169.58.218.168`, tunnel IP `10.88.0.1`) and the Windows Gateway host (tunnel IP `10.88.0.2`).
   - The Windows MT5 Gateway service must bind exclusively to `10.88.0.2:8443` or `127.0.0.1:8443`.
2. **Windows Firewall Rule**:
   ```cmd
   netsh advfirewall firewall add rule name="BITDEX_GATEWAY_WIREGUARD" dir=in action=allow protocol=TCP localport=8443 remoteip=10.88.0.1
   ```
   No public inbound ports (80, 443, 8443) should be opened to `0.0.0.0/0`.
3. **Mutual TLS (mTLS)**:
   When running over HTTPS, generate a self-signed root CA and client certificates:
   - Gateway presents server certificate signed by internal CA.
   - Linux backend presents client certificate signed by internal CA.

---

## 7. Symbol Discovery & Instrument Mapping

Exness MT5 instruments use broker-specific suffixes:
- Gold: `XAUUSDm` (Mini) or `XAUUSD`
- Bitcoin: `BTCUSDm` or `BTCUSD`
- Forex: `EURUSDm`, `GBPUSDm`, `USDJPYm`

The gateway must implement dynamic symbol discovery:
1. `GET /gateway/symbols`:
   Calls `mt5.symbols_get()` and filters instruments matching verified active market subscriptions.
2. Extracts contract specifications:
   - `contract_size`: (e.g. 100,000 for EURUSD, 1.0 for BTCUSD, 100 for XAUUSD)
   - `volume_min`: (e.g. 0.01 lots)
   - `volume_step`: (e.g. 0.01 lots)
   - `volume_max`: (e.g. 100.0 lots)
   - `trade_tick_size`: minimum price step
   - `trade_tick_value`: value of 1 tick per 1 lot

---

## 8. Real-Time Tick & Historical Data Feeds

1. **Tick Streaming (`/gateway/tick/{symbol}`)**:
   Calls `mt5.symbol_info_tick(symbol)` and returns:
   ```json
   {
     "symbol": "BTCUSDm",
     "bid": 78345.50,
     "ask": 78347.10,
     "spread_pts": 1.6,
     "timestamp_ms": 1793798400000,
     "flags": 6
   }
   ```
2. **Historical Bar Retrieval (`/gateway/history/{symbol}`)**:
   Calls `mt5.copy_rates_from_pos(symbol, timeframe, 0, count)`:
   - Returns structured OHLCV candles.
   - Rejects synthetic fallbacks; returns authoritative broker bars.

---

## 9. Reconnection & Supervisor Daemon

1. **Keepalive Ping**:
   Linux staging backend polls `GET /gateway/health` every 15 seconds.
2. **Heartbeat Supervisor**:
   If 3 consecutive health checks fail:
   - The Linux risk engine trips the gateway circuit breaker.
   - Pre-trade validation sets `broker_connection_state = "DISCONNECTED"`.
   - The Windows gateway service monitors MT5 process status; if `terminal64.exe` exits or freezes, the supervisor restarts the process and re-authenticates.

---

## 10. Audit & Integration Sign-Off Checklist

Before any connection is marked `CONNECTED` in the customer UI:
- [ ] Windows VPS provisioned in London/Amsterdam region.
- [ ] MT5 terminal installed in portable mode.
- [ ] Genuine Exness Demo credentials configured via secure environment variable vault.
- [ ] WireGuard / TLS private tunnel operational between Linux and Windows hosts.
- [ ] `X-Gateway-Auth-Token` validated with strong entropy.
- [ ] `account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO` confirmed authoritatively.
- [ ] Real-time tick stream verified for `BTCUSDm`, `XAUUSDm`, and `EURUSDm`.
- [ ] All 11 platform quantitative risk controls validated against the live gateway feed.
- [ ] `live_trading_locked = True` and `emergency_lock_active = True` remain strictly enforced.
