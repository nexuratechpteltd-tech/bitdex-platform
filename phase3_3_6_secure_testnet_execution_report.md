# TAURIC PLATFORM — PHASE 3.3.6 SECURE PROVISIONING & TESTNET EXECUTION REPORT

**Date:** October 22, 2026  
**Environment:** Isolated Staging (`/opt/tauric-platform-staging/`)  
**Trusted HTTPS UI:** `https://bybit-gateway.sheltr.agency:33900/trading/`  
**Server-Side Provisioning Tool:** `/opt/tauric-platform-staging/backend/scripts/provision_credentials.py`  
**Status:** **CREDENTIAL PROVISIONING SECURED (HTTPS & CLI) · PREFLIGHT BLOCKED (AWAITING USER CREDENTIALS) · ZERO ORDERS SUBMITTED**  
**Live Trading Invariants:** `live_trading_locked=true` · `read_only_mode=true`  
**Production Integrity:** 100% UNTOUCHED (Uptime: 31h+, PID 75730 & 88836 online, 0 restarts, dir date 2026-10-19)

---

## 1. Executive Summary

In Phase 3.3.6, the staging credential-provisioning security vulnerability (plain HTTP transmission over port 33900) was fully resolved. 

Two secure, verified provisioning pathways are now active:
1. **Trusted HTTPS Web Interface:** The staging dashboard has been configured with native TLS/HTTPS on port 33900 using the authentic, valid Let's Encrypt certificate (`bybit-gateway.sheltr.agency`, TLSv1.2/1.3, Verify return code: 0 ok). Plain HTTP access has been completely shut down.
2. **Secure Server-Side CLI Tool:** A dedicated Python provisioning utility (`scripts/provision_credentials.py`) allows interactive credential ingestion via `getpass` (masked input, zero terminal echo, zero shell history or `ps aux` command-line argument exposure).

In strict accordance with platform safety boundaries:
- **Current Vault Status:** `credential_vault.json` contains **0 user profiles** (`{}`).
- **Zero Fabrication:** No simulated fills, fake balances, or synthetic exchange receipts were created.
- **Execution Readiness:** Reported as **BLOCKED** pending the user's provisioning of genuine Binance Spot Testnet or Bybit Spot Testnet credentials.
- **Order Submission:** Stopped before order submission. No orders will be submitted without explicit user confirmation of the exact order parameters.
- **Testing:** All 158 tests passed across 11 test suites (`158/158 OK in 6.010s`). Production remains 100% untouched.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PHASE 3.3.6 VERIFICATION GATE                         │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ Control / Boundary                   │ Status                               │
├──────────────────────────────────────┼──────────────────────────────────────┤
│ Plain HTTP Staging Dashboard         │ DISABLED (Connection reset/rejected) │
│ Trusted HTTPS Staging Dashboard      │ PASS (https://bybit-gateway...:33900)│
│ TLS Certificate Validation           │ PASS (Let's Encrypt, Return code: 0)│
│ Server-Side Provisioning Tool (CLI)  │ PASS (scripts/provision_credentials) │
│ Staging Backend Service (Port 8002)  │ ONLINE (Uptime: 30m+, 0 errors)      │
│ Rotated Vault Master Key Active      │ PASS (256-bit AES-256-GCM in .env)   │
│ Master Key Masked Identifier         │ 8254••••••••25ad                     │
│ Secret Redaction Across Routes & UI  │ PASS (100% masked, zero raw secrets) │
│ Staging Vault Cleanliness            │ PASS (0 profiles in staging vault)   │
│ User Testnet Credentials Status      │ ABSENT (0 profiles configured)       │
│ Authenticated Preflight Gate         │ BLOCKED (Awaiting User Credentials)  │
│ Public Testnet Ping Reachability     │ PASS (Binance 285ms, Bybit 261ms)    │
│ Live Trading Execution Hard-Lock     │ PASS (PermissionError 403 enforced)  │
│ Fabricated Fills / Receipts          │ ZERO (Strictly prohibited & enforced)│
│ Order Submission Status              │ HALTED (Awaiting explicit approval)  │
│ Backend Regression Suite             │ PASS (158/158 passed in 6.010s)      │
│ Production Environment Isolation     │ 100% UNTOUCHED (PID 75730 31h+ uptime│
└──────────────────────────────────────┴──────────────────────────────────────┘
```

---

## 2. Credential Provisioning Security Resolution

### 2.1 Remediation of Plain HTTP Vulnerability
- **Finding:** In Phase 3.3.5, the staging dashboard was accessible at `http://169.58.218.168:33900/trading/` over unencrypted HTTP, presenting a risk of plaintext credential interception across the network.
- **Resolution:**
  - Plain HTTP was immediately terminated.
  - Next.js staging dashboard was wrapped in a native HTTPS server (`server.js`) listening on `0.0.0.0:33900`.
  - All plain HTTP requests to port 33900 now receive `(52) Empty reply from server` and are immediately dropped.

### 2.2 Certificate & TLS Verification
- **Certificate Path:** `/etc/letsencrypt/live/bybit-gateway.sheltr.agency/fullchain.pem`
- **Private Key Path:** `/etc/letsencrypt/live/bybit-gateway.sheltr.agency/privkey.pem`
- **OpenSSL Verification:**
  ```text
  subject=CN=bybit-gateway.sheltr.agency
  issuer=C=US, O=Let's Encrypt, CN=YE2
  Verify return code: 0 (ok)
  Protocols: TLSv1.2, TLSv1.3
  Cipher: ECDHE-ECDSA-AES128-GCM-SHA256
  ```
- **External Curl Verification:**
  `curl -I https://bybit-gateway.sheltr.agency:33900/trading/` -> `HTTP/1.1 200 OK`.
- **Zero Production Risk:** The HTTPS server runs as an independent process on port 33900 in staging. No modifications were made to `/etc/nginx/`, and Nginx was not restarted or reloaded.

### 2.3 Server-Side Provisioning Method (CLI)
For maximum operational security, a dedicated script was deployed at:
`/opt/tauric-platform-staging/backend/scripts/provision_credentials.py` (`chmod 700`).

**Security Properties:**
- Uses Python `getpass.getpass()` for interactive entry: keys and secrets are never echoed to the screen.
- Never accepts secrets via command-line arguments: completely invisible in `ps aux` and bash history (`~/.bash_history`).
- Reads directly into memory and encrypts using AES-256-GCM under the rotated master key (`8254••••••••25ad`).
- Immediately tests permissions against the testnet matching engine (`https://testnet.binance.vision/api/v3` or `https://api-testnet.bybit.com/v5`) to verify whether `can_trade == True`.
- Supports automated ingestion via `stdin` JSON without persistent plaintext files.

---

## 3. Provisioning Instructions for the User

You may configure your Binance Spot Testnet or Bybit Spot Testnet credentials using either secure method below:

### Method A — Trusted HTTPS Staging UI
1. Navigate in your browser to:  
   👉 **`https://bybit-gateway.sheltr.agency:33900/trading/`**
2. In the top-right header, click **API Connections**.
3. Select:
   - **Exchange:** `Binance (Spot)` or `Bybit (Spot V5)`
   - **Environment:** `Demo (Testnet / Paper)`
   - **Account Label:** e.g. `Binance Testnet Primary`
   - **API Key & Secret:** Enter your testnet credentials (inputs are masked with `type="password"`).
4. Click **Save Connection Profile** (stored encrypted with AES-256-GCM).
5. Click **Test Demo** to verify testnet connectivity and read balances.

### Method B — Server-Side Interactive CLI
Run via SSH on the staging server:
```bash
cd /opt/tauric-platform-staging/backend
.venv/bin/python3 scripts/provision_credentials.py
```
Follow the interactive masked prompts:
```text
============================================================
TAURIC SECURE TESTNET CREDENTIAL PROVISIONING
============================================================
Select Exchange [1] Binance Spot Testnet, [2] Bybit Spot Testnet: 1
Target Environment: DEMO (Isolated Testnet)
Account Label [default: BINANCE Spot Testnet Primary]: 
Enter Testnet API Key: [hidden]
Enter Testnet API Secret: [hidden]
```
The script will encrypt your credentials into the vault, verify testnet connectivity, and display testnet balances.

---

## 4. Current Preflight Status & Proposed Testnet Order

### 4.1 Current Preflight Status: `BLOCKED`
- **Reason:** 0 user-configured profiles in staging vault (`credential_vault.json` is `{}`).
- **Safeguard:** No order can be submitted without genuine credentials. Zero simulated fills or synthetic receipts will be generated.

### 4.2 Fresh Market Data & Proposed Controlled Order
Using real-time book-ticker data fetched from the Binance Spot Testnet matching engine:
- **Symbol:** `BTCUSDT`
- **Current Best Bid:** `84,543.29 USDT`
- **Current Best Ask:** `84,543.30 USDT`
- **Spread:** `0.01 USDT`

```yaml
Proposed Testnet Order:
  Exchange: Binance Spot Testnet
  Environment: DEMO (Testnet Only)
  Symbol: BTCUSDT
  Side: BUY
  Order Type: LIMIT
  Quantity: 0.001 BTC
  Limit Price: 84543.29 USDT (Current Best Bid)
  Estimated Notional: 84.54 USDT
  Time in Force: GTC (Good 'Til Cancelled)
  Exchange Filter Verification:
    - Min Quantity: 0.00001 BTC (Order 0.001 >= 0.00001 -> PASS)
    - Step Size: 0.00001 BTC (Order 0.001 multiple of 0.00001 -> PASS)
    - Tick Size: 0.01 USDT (Limit 84543.29 multiple of 0.01 -> PASS)
    - Min Notional: 5.00 USDT (Notional 84.54 >= 5.00 -> PASS)
  Deterministic Risk Gates:
    - Market Data Freshness: FRESH (Real-time book ticker)
    - Liquidity Status: QUALIFIED (Spread 0.01 USDT)
    - Economic Event Blackout: False (No active blackout)
    - Setup Validity: Active (>0s)
  Post-Execution Reconciliation Plan:
    - Retrieve exchange order ID & actual execution status
    - Reconcile executed quantity vs requested quantity
    - Compute average fill price & verify exchange fees (0.10% standard maker/taker)
    - Reconcile testnet account balance deductions
    - Open platform mark-to-market position record
```

**ORDER SUBMISSION IS HALTED.** No order will be submitted until:
1. Real testnet credentials are provisioned in the vault.
2. Authenticated preflight returns `status: PASS` and `can_trade: True`.
3. Separate explicit confirmation is provided authorizing this exact order.

---

## 5. Security & Safeguards Verification

### 5.1 Test Suite Verification (158 Tests Passed)
Executed on VPS staging backend (`/opt/tauric-platform-staging/backend/.venv`):
```bash
PYTHONPATH=. .venv/bin/python3 -m unittest \
  test_phase2_qualification.py \
  test_phase2_extended.py \
  test_phase3_finance_calendar.py \
  test_phase3_1_safety_audit.py \
  test_phase3_1_1_adversarial.py \
  test_phase3_2_dual_ai.py \
  test_phase3_2_1_adversarial.py \
  test_phase3_3_execution.py \
  test_phase3_3_1_security.py \
  test_phase3_3_2_acceptance.py \
  test_phase3_3_5_preflight.py
```
**Result:** `Ran 158 tests in 6.010s — OK (158 passed, 0 failures, 0 errors)`.

### 5.2 Production Environment Isolation
- **Production Directory (`/opt/tauric-platform`):** Untouched (timestamp `2026-10-19 23:15:02 CEST`).
- **Production Backend (`tauric-backend`):** PID `75730`, Uptime 31h+, 0 restarts, online on port 8001.
- **Production Dashboard (`tauric-dashboard`):** PID `88836`, Uptime 27h+, 0 restarts, online on port 8080.
- **Invariants:** `live_trading_locked=true`, `read_only_mode=true`. Zero production mutations.
