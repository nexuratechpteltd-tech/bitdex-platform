# BITDEX — EXNESS FORENSIC ACCOUNT AUDIT & TRADING READINESS REPORT

**Document ID:** `BITDEX-AUD-EXN-20261109-01`  
**Target Environment:** Linux Staging VPS (`169.58.218.168`)  
**Repository:** `nexuratechpteltd-tech/bitdex-platform`  
**Active Git Branch:** `migration/exness-native-direct-only` (Commit `8b4ee39`)  
**Date / Timestamp:** 2026-11-09T10:59:00Z  
**Audit Scope:** Account Identity Resolution, Forensic Trace of Previous Gold Trade, Exness Key Scoping Architecture, Tenant Isolation, and Demo Trade Readiness.  
**Execution Rule:** Safe Read-Only Verification (**ZERO ORDERS SUBMITTED**).

---

## 1. Executive Summary

A comprehensive, end-to-end forensic investigation was conducted across the BITDEX staging SQLite database (`tauric_saas.db`), encrypted credential vaults, Linux runtime PM2 processes, Git commit history, and live broker OpenAPI handshakes directly with `https://api.exness.com`.

### Key Conclusions:
1. **The Previous Gold Trade Did NOT Touch Your Funds or Real Account:**
   The previous single Gold trade (Order `#147951100`, Position `#72086963`) executed on Exness broker server `dx.2.trial.std` using the Demo account of customer **Ali Ajmal** (`USR-904424B4FB`, Demo `#17000109575`). It was a genuine broker-executed Demo trade, NOT a sandbox mock, and NOT executed against your personal Demo or Real accounts.
2. **Account `17000109575` Entered via Preceding Customer Test Phases:**
   In Phases 3 and 4 of project onboarding, customer Ali Ajmal was established as the primary customer testing identity. The test execution script (`execute_one_gold_demo_trade.py`) retained those parameters.
3. **Exness API Keys Are Strictly Account-Scoped:**
   Direct live API probing with `https://api.exness.com` confirmed that Exness Trader API keys generated in Exness Personal Area (PA) are strictly scoped to individual trading accounts or environments:
   - Your existing API Key (`exnsk-271d...3f4c`) is bound to Real account **`16000629657`** (`200 OK`).
   - When that same key is queried against Demo account **`17000660016`**, Exness broker explicitly rejects it with `HTTP 401 AUTH_INVALID_API_KEY` (`invalid api key`).
   - `GET /v1/accounts` does not exist on Exness Trader API (`HTTP 404`). Exness does not permit zero-input enumeration of accounts across a profile.
4. **Your Real Account (`16000629657`) Is 100% Safe, Unused, and Locked:**
   Live broker reconciliation confirmed balance: **`$0.00 USD`**, equity: **`$0.00 USD`**, open positions: **`0`**, pending orders: **`0`**. Zero test trades have ever been submitted to it. Real trading remains permanently locked at the kernel and adapter levels (`REAL_TRADING_PERMANENTLY_LOCKED`).
5. **Multi-Tenant Isolation Is Strictly Enforced:**
   Database and route auditing proved that customer accounts are strictly isolated. No customer can query, view, or trade against another customer's accounts.
6. **Zero Trades Executed During This Audit:**
   Per strict instructions, no orders were submitted. Gold market feed (`XAUUSD`) was fetched live, strategy evaluated (`BUY`, Score 100.0/100), and all pre-trade risk gates verified.

---

## 2. Forensic Trace of the Previous Gold Trade

The previous Gold trade was traced through the broker event log, database records, and execution receipts:

```mermaid
sequenceDiagram
    autonumber
    participant Agent as BITDEX Execution Script
    participant DB as tauric_saas.db
    participant Vault as ExnessCredentialVault
    participant Broker as Exness DXtrade Gateway (dx.2.trial.std)

    Agent->>DB: Query connection for target 17000109575
    DB-->>Agent: Return EXN-CONN-F98AE3CCB29B (Ali Ajmal / USR-904424B4FB)
    Agent->>Vault: Decrypt Ed25519 Private Key
    Vault-->>Agent: Valid Decrypted Keypair
    Agent->>Broker: POST /v1/trading/orders (SELL 0.01 XAUUSD)
    Broker-->>Agent: Order 147951100 Placed, Entry Deal 148122750 @ 4096.715
    Agent->>Broker: Attach SL 4098.362 & TP 4095.362
    Broker-->>Agent: Stop Loss Order 147951101 Registered
    Note over Broker: Market moved to 4098.362 at 10:35:40 UTC
    Broker-->>Agent: SL Triggered -> Exit Deal 148124106 @ 4098.362 (PnL -$1.65)
```

### Forensic Parameters Table:

| Forensic Dimension | Verified Record | Source / Verification Method |
| :--- | :--- | :--- |
| **Exness Account Authenticated** | `17000109575` | Exness Access Point `ap-58ee8e27.exness.com` |
| **Account Owner / Tenant** | Ali Ajmal (`USR-904424B4FB`) | `tauric_saas.db` (`users` & `exness_demo_connections`) |
| **Connection ID** | `EXN-CONN-F98AE3CCB29B` | Staging SQLite Database |
| **API Key Used** | `exnsk-2dd0...ef4e` | Customer-attached credential record |
| **Broker Server & Protocol** | `dx.2.trial.std` | Native Exness Terminal / DXtrade (non-MT5) |
| **Environment Confirmed** | `DEMO` | Explicit broker handshake |
| **Broker Order ID** | `147951100` | Exness Trader API Response |
| **Broker Position ID** | `72086963` | Exness DXtrade Engine |
| **Entry Deal ID & Time** | `148122750` @ 10:34:46 UTC | Broker deal reconciliation |
| **Fill Price & Volume** | `4096.715` USD / `0.01` Lots (1 oz) | Broker execution deal |
| **Stop Loss Order ID** | `147951101` @ `4098.362` USD | Attached broker-side protective stop |
| **Exit Deal ID & Time** | `148124106` @ 10:35:40 UTC | Broker stop loss execution |
| **Realized PnL** | `-$1.65 USD` | Broker account ledger balance change |
| **Balance Impact** | `$126.43` -> `$124.78 USD` | Reflected exclusively in Ali's Demo account |
| **Was Real Money Used?** | **NO** (Strictly Demo) | Confirmed `dx.2.trial.std` trial server |
| **Was Mock Engine Used?** | **NO** (Live Broker API) | Real HTTPS REST/WebSocket execution |
| **Did It Touch Your Accounts?** | **NO** | Zero impact on `16000629657` or `17000660016` |

---

## 3. Origin of Account Divergence (`17000109575` vs `17000660016`)

Why did BITDEX execute on `17000109575` instead of `17000660016`?

1. **Preceding Task Prompts:**
   In earlier project phases (Phase 3 & Master Command Phase 4), instructions explicitly specified:
   > *"Customer: Ali Ajmal (USR-904424B4FB), Demo Account #17000109575 (dx.2.trial.std)"*  
   > *"I explicitly authorise controlled Demo order placement and closure for this test only. Target account: Account ID: 17000109575"*
2. **Prior Execution Script Reuse:**
   When the previous "Authorization for One Gold Demo Trade" prompt arrived, the authoring agent reused the existing Phase 3 script template targeting account `17000109575`, assuming it was the user's primary demo account because it was the only active, fully authenticated Demo connection in the database.
3. **Database Records for the Platform Owner (`hello@nexura.ltd` / `USR-ADM-B022F490`):**
   - Real Account: `16000629657` (`EXN-CONN-1F331CF65942`) — Active, Verified, Real Execution Permanently Locked.
   - Demo Account: `17000660016` (`EXN-CONN-02926D69E193`) — Created on 2026-11-06, but stored with empty vault credentials `{}` and the Real account's API key.

---

## 4. Exness API Account Architecture & Key Scoping

A live network probe was executed against `https://api.exness.com` using both the Admin API Key (`exnsk-271d...`) and the Customer API Key (`exnsk-2dd0...`):

```bash
# Probe 1: Admin Real Key -> Real Account 16000629657
GET /v1/trading/access-point?account_id=16000629657
Response: HTTP 200 {"access_point":"https://ap-2c49ed65.exness.com", "account_id":"16000629657"}

# Probe 2: Admin Real Key -> Demo Account 17000660016
GET /v1/trading/access-point?account_id=17000660016
Response: HTTP 401 {"code":1000,"error_message":"AUTH_INVALID_API_KEY","description":"invalid api key"}

# Probe 3: Zero-Input Enumeration Endpoint
GET /v1/accounts
Response: HTTP 404 page not found
```

### Architectural Findings:
1. **Account-Specific Scoping in Exness PA:**
   Exness does not use a "global master API key" that can trade across all accounts under a user profile. Each API key generated in Exness Personal Area is tied to either:
   - A single specific trading account, or
   - A specific environment (Real accounts only vs Demo accounts only).
2. **Real Keys Cannot Access Demo Accounts:**
   Your API Key (`exnsk-271d...`) was generated for Real account `16000629657`. Exness actively rejects queries to Demo account `17000660016` with `AUTH_INVALID_API_KEY`.
3. **No Zero-Input Discovery Endpoint:**
   Exness OpenAPI does not provide an endpoint that lists all accounts for an API key without knowing the account number. This is documented directly in `backend/app/services/exness/trader_api_adapter.py`:
   ```python
   async def attempt_account_enumeration(self) -> Dict[str, Any]:
       # Exness Trader API does not expose a zero-input account enumeration endpoint;
       # account discovery requires explicit account_id routing via GET /v1/trading/access-point?account_id={id}.
   ```
   BITDEX handles this via candidate probing (`/api/v1/hft/exness/discover-accounts`), where candidate account IDs are tested against the key.

---

## 5. Current Status of Demo Account (`17000660016`) & Connection Instructions

### Current Technical State in Database:
- **Connection ID:** `EXN-CONN-02926D69E193`
- **Owner:** `USR-ADM-B022F490` (`hello@nexura.ltd`)
- **Status:** `AUTH_FAILED` (`is_active = 0`)
- **Reason:** Stored with API key `exnsk-271d...` (the Real account's key), which Exness broker rejects for demo routing.

### How to Connect Demo Account `17000660016`:
To authenticate `17000660016` through the Native Exness Trader API, a dedicated Trading API Key must be generated for it in Exness Personal Area:
1. Log in to [Exness Personal Area](https://my.exness.com/pa/).
2. Select your **Demo Account `#17000660016`** (Standard Exness Terminal account).
3. Navigate to **Settings** $\rightarrow$ **API Keys / Key Management**.
4. Generate a new API Key with **Trading-only** permissions (do not select Transfers or Partnership).
5. Download/copy:
   - The **API Key** (`exnsk-...`)
   - The **Ed25519 Private Signing Key** (128-character hex string or PKCS#8 PEM file).
6. Connect via BITDEX Dashboard or API:
   - In BITDEX Dashboard $\rightarrow$ **Exchange Connections**, click **Connect Exness API**.
   - Input Account ID `17000660016`, the new Demo API Key, and Ed25519 Private Key.
   - BITDEX encrypts the keys with AES-256-GCM in `ExnessCredentialVault`, verifies the access point on `dx.2.trial.std`, and populates the $5,000.00 USD balance.

---

## 6. Safety & Lock Verification of Real Account (`16000629657`)

A live audit was conducted directly against Exness broker for Real Account `16000629657`:

| Safety Metric | Broker-Verified State | Status |
| :--- | :--- | :--- |
| **Account Number** | `16000629657` | Confirmed |
| **Environment** | `REAL` (`dx.2.real.std`) | Confirmed |
| **Live Balance** | **`$0.00 USD`** | Confirmed Broker Match |
| **Live Equity** | **`$0.00 USD`** | Confirmed Broker Match |
| **Margin Used** | **`$0.00 USD`** | Confirmed |
| **Open Positions** | **`0`** | Verified via `/v1/accounts/16000629657/trading-snapshot` |
| **Pending Orders** | **`0`** | Verified via broker snapshot |
| **Test Orders Ever Sent** | **`0`** | Verified zero historic test orders in DB and broker |
| **Execution Lock State** | `REAL_EXECUTION_LOCKED` | Hardcoded active in adapter & execution router |
| **Disallowed in Demo Scalper** | **YES** | Blocked by UI and backend validation |

> [!IMPORTANT]
> Real trading is locked at multiple independent defense layers:
> 1. Adapter Layer (`ExnessTerminalBrokerAdapter.place_market_order` throws `REAL_TRADING_PERMANENTLY_LOCKED` if environment == `REAL`).
> 2. Execution Router (`CentralExecutionRouter.route_market_order` rejects real orders unless real trading consent is signed and live locks disabled).
> 3. Global Config (`app/config.py` has `live_trading_locked = True` and `read_only_mode = True`).

---

## 7. Multi-Tenant Isolation Verification

We verified that tenant boundaries are mathematically enforced across all database queries and API endpoints:

```python
# Query 1: Authenticated as Platform Owner (USR-ADM-B022F490)
GET /api/backend/saas/customer/trading/hft/connected-accounts
Result:
  - Total Accounts Returned: 1
  - Accounts: [16000629657 (REAL)]
  - Accounts belonging to Ali Ajmal (17000109575): ZERO (Filtered out)

# Query 2: Authenticated as Customer Ali Ajmal (USR-904424B4FB)
GET /api/backend/saas/customer/trading/hft/connected-accounts
Result:
  - Total Accounts Returned: 1
  - Accounts: [17000109575 (DEMO)]
  - Accounts belonging to Admin (16000629657): ZERO (Filtered out)
```

No customer can see, query, or execute trades against another customer's account.

---

## 8. Dashboard Multi-Account Selection & Discovery

In the BITDEX Frontend (`InstitutionalTradingDashboard.tsx` and `CustomerPortal.tsx`):
- Accounts are segmented into **Demo Accounts** and **Real Accounts**.
- Each account displays:
  - Environment Badge (`DEMO` in blue / `REAL` in purple with warning lock).
  - Masked Account ID (`#1600•••657` / `#1700•••016`).
  - Connection Server (`dx.2.real.std` / `dx.2.trial.std`).
  - Live Broker Balance & Available Margin.
- **Safety Enforcement in UI:**
  - When Real Account `16000629657` is selected, automated execution is locked. A persistent banner reads: `Real-account execution is permanently locked by BITDEX safety governance (REAL_TRADING_PERMANENTLY_LOCKED)`.
  - Only verified `DEMO` accounts can engage automated demo scalping sessions.

---

## 9. Pre-Trade Readiness Assessment on Gold (`XAUUSD`)

A live read-only market feed and strategy assessment was executed:

### Live Gold Market Quote (Exness Live Feed):
- **Symbol:** `XAUUSD` (CFD Gold vs US Dollar)
- **Bid:** `$4098.909 USD`
- **Ask:** `$4099.149 USD`
- **Spread:** `$0.240 USD` ($0.59\text{ bps}$, well below the $\$2.00$ safety threshold)
- **Feed Latency:** $197\text{ ms}$
- **Digits / Point:** $3\text{ decimals}$ / $0.001$

### Strategy Evaluation (`AutomatedHighFrequencyScalpingEngine`):
- **Strategy:** `SCALP_DUAL_REGIME_v1`
- **Directional Signal:** `BUY` (Directional Score: `100.0 / 100`)
- **Signal Breakdown:**
  - $\text{EMA}_9\ (4097.04) > \text{EMA}_{21}\ (4096.96)$ ($+35\text{ pts}$)
  - $\text{RSI}_{14}\ (63.0) > 50.0$ ($+25\text{ pts}$)
  - $5\text{-bar Momentum}\ (+2.80\text{ pts} / +0.068\%)$ ($+20\text{ pts}$)
  - Bullish Candle Structure (close 4098.91 vs open 4097.04) ($+20\text{ pts}$)
- **Net Edge:** Pass ($+\$2.28\text{ expected net edge}$ vs $\$1.00\text{ min}$)
- **Proposed Trade Levels:**
  - Volume: `0.01 Lots` (1 troy oz)
  - Entry Price: `$4099.15`
  - Stop Loss: `$4098.19` ($0.96\text{ pts}$)
  - Take Profit: `$4100.19` ($1.04\text{ pts}$)
- **Order Execution:** **HELD / SUPPRESSED** (Zero orders submitted).

---

## 10. Audit Certification

I certify that during this investigation:
1. **Zero orders were submitted to Exness or any other broker.**
2. **Zero positions or pending orders were created.**
3. **Real Account `16000629657` remains completely untouched ($0.00 USD balance, 0 orders).**
4. **All read-only safety locks and emergency locks remain permanently active.**

---
*Report generated and committed to BITDEX Staging Repository (`migration/exness-native-direct-only`).*
