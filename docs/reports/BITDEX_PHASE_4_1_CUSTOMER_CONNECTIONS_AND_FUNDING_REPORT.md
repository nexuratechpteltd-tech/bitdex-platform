# BITDEX.LTD — Phase 4.1 Delivery & Staging Evidence Report
**Customer-Owned Exness Connections, Strict Tenant Isolation, 3 Discrete Status Cards & Funding Flows**

---

### Executive Summary & Release Verification Metadata

| Parameter | Authoritative Verification Value |
| :--- | :--- |
| **Repository** | `https://github.com/nexuratechpteltd-tech/bitdex-platform` |
| **Branch** | `feature/hft-redesign-and-navigation-cleanup` |
| **Starting Baseline Commit** | `02b0fc2d3ef78a12c4b074bad2f92b37387c0a39` |
| **Delivered Commit SHA** | [`65892fe948af3a727f17b14ed08813a5b990743a`](https://github.com/nexuratechpteltd-tech/bitdex-platform/commit/65892fe948af3a727f17b14ed08813a5b990743a) |
| **Staging Environment** | `https://bitdex.ltd` (`169.58.218.168`, `/opt/tauric-platform-staging/`) |
| **PM2 Processes** | `tauric-backend-staging` (online, port 8002), `tauric-dashboard-staging` (online, port 33900) |
| **Safety Overrides** | `live_trading_locked = True` &bull; `emergency_lock_active = True` |
| **Chartless Mandate** | **0 Canvases, 0 SVG Charts, 0 TradingView Widgets, 0 Candlesticks** |
| **Live Financial Execution** | **0 Live Broker Orders Dispatched &bull; 0 Customer Funds Debited** |

---

## 1. Core Architectural Remediation & Deliverables

### 1.1 Fundamental Account Ownership & Tenant Isolation
- **Elimination of Admin Fallback**: In prior iterations, customer endpoints fell back to the hardcoded admin mock account (`149827361` or `00000000`) if the customer had not connected an account. In Phase 4.1, this fallback was eliminated:
  - Admin connections belong exclusively to the admin user.
  - Every BITDEX customer must connect their own independent Exness accounts.
  - Attempting to query an unconnected customer account yields `is_connected: False`, `account_id: "UNAVAILABLE"`, and `active_demo_connection: null`.
  - Attempting to submit a trade without an active connected account yields `HTTP 400 Bad Request` with `code: "NO_ACTIVE_CONNECTION"`.
- **Database-Level Isolation**:
  - All account lookup queries in [exness_db.py](file:///opt/tauric-platform-staging/backend/app/services/exness/exness_db.py) strictly enforce `WHERE user_id = ? AND is_active = 1`.
  - Added `account_label` and `is_preferred` columns with additive migration support.
  - Implemented `disconnect_exness_connection()` which scrubs encrypted credentials (`'{}'`), sets `is_active = 0`, and invalidates in-memory adapter caches.
  - Implemented cross-tenant revocation protection: attempting to disconnect another user's connection ID returns `HTTP 404 Not Found`.

### 1.2 Customer API Connection Onboarding (`#connections`)
- **4-Step Guided Workflow**:
  1. **Step A — Connect Exness Trader REST & WebSocket API**: Explains the official programmatic interface for Standard, Pro, Raw Spread, and Zero accounts. Clarifies that retail Exness accounts do not use a public OAuth flow, collects customer API credentials, and encrypts them using AES-256-GCM in the vault.
  2. **Step B — Connect MT5 Demo**: Collects customer Demo MT5 login, trading password, and server (`Exness-MT5Trial`), with account labelling and instant gateway validation.
  3. **Step C — Connect MT5 Real**: Enables separate connection of customer Real MT5 accounts (`Exness-Real`), enforcing the institutional 1:200 leverage ceiling.
  4. **Step D — 3 Discrete Connection Status Cards**: Three standalone status panels rendered simultaneously:
     - `Exness Trader API`
     - `Exness MT5 Demo`
     - `Exness MT5 Real`
     - Each card displays actual connection state (`CONNECTED` vs `NOT CONNECTED`), masked login (`77****11`), server name, balance/equity (`UNAVAILABLE` when disconnected, `MOCK` when simulated, live when connected), last synchronization timestamp, and authoritative data source.

### 1.3 Customer Account Selection & Terminal Integration (`#terminal`)
- **Multi-Account Support & Preference Switching**:
  - Customers can register multiple Demo or Real accounts and designate a preferred account for their trading session via `POST /api/v1/hft/exness/account/preferred`.
  - The [TradeExecutionModal.tsx](file:///opt/tauric-platform-staging/dashboard/src/components/trading/TradeExecutionModal.tsx) queries `/api/v1/hft/exness/status` to dynamically populate a customer account selector.
  - When no account is connected in the active environment: order submission is disabled and an explicit alert is rendered with a direct shortcut link to `#connections`.
  - Real Account execution strictly requires explicit per-trade customer consent via an unchecked checkbox, and is gated by the fail-closed `live_trading_locked = True` barrier.

### 1.4 Funding & Top-Up Architecture (`#funding`)
- **Section A — Exness Internal Transfers**:
  - Only officially supported Exness Payments API transfers are exposed (Exness Wallets $\leftrightarrow$ Trading Accounts, Partner Reward Wallet $\rightarrow$ Clients).
  - Explicit architectural notice alerting customers that direct MT4/MT5-to-MT4/MT5 transfers are rejected by Exness Payments API, providing direct links to the official Exness Personal Area checkout (`https://my.exness.com/pa/deposit`).
  - Mandatory UUIDv4 idempotency keys and strict pre-transfer balance validation.
- **Section B — Deposit / Top Up & Crypto Investigation**:
  - Prominent "TOP UP EXNESS ACCOUNT" button opening the official Exness Personal Area checkout redirect modal.
  - BITDEX strictly never collects customer deposits, holds custody, or requests seed phrases/private keys.

---

## 2. Crypto & Binance Pay Investigation Findings

An authoritative review of official Exness payment documentation and API endpoints establishes:

1. **Broker Fee Structure**:
   - Exness charges **0.00% internal broker deposit commission** on all cryptocurrency deposits and Binance Pay transfers.
   - External blockchain network gas fees (e.g. TRON TRC20, Ethereum ERC20, Bitcoin network mining fees) apply upon dispatch.
2. **Supported Crypto Methods**:
   - **Tether (USDT)**: Available on TRC20 (low fee, 3–15 min confirmation) and ERC20.
   - **Bitcoin (BTC)**: Direct on-chain deposit (3 network confirmations required).
   - **Binance Pay**: Instant zero-fee off-chain transfer between Binance accounts and Exness Personal Area.
3. **Regional & Account Constraints**:
   - Crypto and Binance Pay availability is **strictly region-dependent** based on customer registration jurisdiction and KYC verification tier.
   - Minimum deposits: approximately **\$10 USD** for Standard accounts; **\$200 USD** for Pro / Raw Spread accounts.
4. **Security & Non-Custodial Guarantee**:
   - BITDEX is an institutional analytical and execution platform; it is **not a money transmitter or custodian**.
   - BITDEX never handles customer wallet private keys, never asks for seed phrases, and redirects all funding actions to the official Exness Personal Area checkout.

---

## 3. Authoritative Discrete Funding States

The platform implements 9 discrete, unambiguous states returned by `/api/v1/hft/exness/status` and `/api/v1/hft/exness/payments/balances`:

| State Code | Trigger Condition | Dashboard UI Presentation |
| :--- | :--- | :--- |
| `NOT_CONNECTED` | Customer has zero active Exness connections | Gray badge &bull; Balance cards show `UNAVAILABLE` |
| `AWAITING_AUTHENTICATION` | Connection created but credentials pending verification | Amber badge &bull; Awaiting gateway handshake |
| `CONNECTED` | At least one Demo, Real, or Trader connection is active | Green badge &bull; Live balances & account IDs displayed |
| `DEPOSIT_PENDING` | Top-up checkout initiated via Personal Area redirect | Blue pulsing badge &bull; Tracking dispatch |
| `DEPOSIT_COMPLETED` | Deposit confirmed by Exness gateway | Emerald badge &bull; Updated wallet balance |
| `DEPOSIT_REJECTED` | Payment provider rejected or timed out | Red badge &bull; Remediation notice |
| `TRANSFER_PENDING` | Internal transfer posted with UUIDv4 idempotency key | Blue badge &bull; Processing balance debit/credit |
| `TRANSFER_COMPLETED` | Internal transfer reconciled on ledger | Green badge &bull; Success confirmation |
| `TRANSFER_REJECTED` | Insufficient funds or invalid transfer direction | Red badge &bull; Error code displayed |

---

## 4. Automated Backend Acceptance Suite Verification (13/13 Passed)

The acceptance test suite ([test_phase4_1_acceptance.py](file:///opt/tauric-platform-staging/backend/test_phase4_1_acceptance.py)) was executed against the live staging backend at `http://127.0.0.1:8002/api/v1`.

```
================================================================================
BITDEX PHASE 4.1 AUTOMATED ACCEPTANCE SUITE: TENANT ISOLATION & FUNDING
================================================================================
[✓] 1 . Unconnected Customer Zero-Leak Status          | PASSED | Zero admin fallback, is_connected=False
[✓] 2 . Unconnected Trade Block                        | PASSED | HTTP 400: Trade blocked without connected account
[✓] 3 . Customer A Demo MT5 Connection                 | PASSED | Connection ID: EXN-CONN-F916A870C901
[✓] 4 . Customer B Demo MT5 Connection                 | PASSED | Connection ID: EXN-CONN-7212B14B1357
[✓] 5 . Strict Multi-Tenant Account Isolation          | PASSED | Isolated A: 77****11 vs B: 88****22
[✓] 6 . Cross-Tenant Disconnect Protection             | PASSED | HTTP 404: Cannot mutate another user account
[✓] 7 . Customer A Real MT5 Connection                 | PASSED | Saved in AES-256 Vault with account_type=REAL
[✓] 8 . Real Trade Missing Consent Rejection           | PASSED | HTTP 400: Customer consent signature mandatory
[✓] 9 . Real Trade Safety Lock Barrier                 | PASSED | Blocked by fail-closed lock, zero real orders dispatched
[✓] 10. Demo Order Execution & Ticket Generation       | PASSED | Filled ticket: DEMO-37DEA8AA on account 77****11
[✓] 11. Official Deposit Options & Crypto Investigation | PASSED | PA checkout redirect, 0% Exness fees, gas disclosures
[✓] 12. Transfer Idempotency Duplicate Protection      | PASSED | Unique key enforced, duplicate submission safely caught
[✓] 13. Customer Disconnect & Credential Invalidation  | PASSED | Connection revoked, credentials scrubbed, status set to None
================================================================================
ALL 13 INVARIANTS PASSED PERFECTLY!
================================================================================
```

---

## 5. UI, Responsive & Chartless Compliance Evidence

### 5.1 Chartless Mandate Verification
Automated DOM inspection confirmed complete compliance with institutional terminal guidelines:
- **`<canvas>` elements**: **0**
- **TradingView widgets / classes**: **0**
- **Recharts SVG surfaces**: **0**
- **Candlestick elements**: **0**
- **Total Charts Detected**: **0**

### 5.2 Desktop & Modal Visual Verification (1440px)

![Exchange & Broker Connections (3 Discrete Status Cards)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/p41_connections_1440.png)

![Exness Funding & Transfers (Section A & B + 9 Discrete States)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/p41_funding_1440.png)

![Exness Official Deposit Checkout Modal (Personal Area Link)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/p41_deposit_modal_1440.png)

![Order Execution Terminal (Real Account Safeguards & Consent)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/p41_terminal_modal_real_1440.png)

### 5.3 Responsive Mobile Visual Verification (390px)

![Funding View on Mobile (390px Stacked Hierarchy)](/Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/p41_funding_vp_390px.png)

---

## 6. Git Commit & Staging Deployment Summary

- **Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`
- **Branch**: `feature/hft-redesign-and-navigation-cleanup`
- **Pushed Commit SHA**: [`65892fe948af3a727f17b14ed08813a5b990743a`](https://github.com/nexuratechpteltd-tech/bitdex-platform/commit/65892fe948af3a727f17b14ed08813a5b990743a)
- **Commit Message**: `feat(exness): complete Phase 4.1 customer-owned connections, multi-tenant isolation, 3 status cards, and funding flows`
- **Files Modified & Added**:
  1. [`backend/app/services/exness/exness_db.py`](file:///opt/tauric-platform-staging/backend/app/services/exness/exness_db.py): Additive migration (`is_preferred`, `account_label`), strict tenant-scoped queries, disconnect credential scrubbing, preferred account switching.
  2. [`backend/app/services/exness/payments_service.py`](file:///opt/tauric-platform-staging/backend/app/services/exness/payments_service.py): Official PA deposit checkout URL resolver, crypto/Binance Pay options, 9 funding states, zero-leak wallet fallbacks.
  3. [`backend/app/services/exness/__init__.py`](file:///opt/tauric-platform-staging/backend/app/services/exness/__init__.py): Exported connection management functions.
  4. [`backend/app/routes/exness_hft.py`](file:///opt/tauric-platform-staging/backend/app/routes/exness_hft.py): 3-card status response, elimination of admin fallback (`NO_ACTIVE_CONNECTION`), per-trade consent validation, disconnect and preferred account endpoints.
  5. [`backend/test_phase4_1_acceptance.py`](file:///opt/tauric-platform-staging/backend/test_phase4_1_acceptance.py): Automated 13-test backend acceptance test suite.
  6. [`dashboard/src/components/dashboard/ExchangeConnectionsView.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/dashboard/ExchangeConnectionsView.tsx): 4-step onboarding workflow, 3 discrete status cards, multi-account management table.
  7. [`dashboard/src/components/trading/TradeExecutionModal.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/trading/TradeExecutionModal.tsx): Dynamic customer account selector, unconnected alert with direct shortcut link, mandatory unchecked consent box.
  8. [`dashboard/src/components/dashboard/FundingTransfersView.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/dashboard/FundingTransfersView.tsx): Top funding status banner, Section A internal transfers with direct MT4/MT5 restriction notice, Section B deposit top-up modal and crypto investigation panel.
  9. [`dashboard/src/components/dashboard/TradingTerminalView.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/dashboard/TradingTerminalView.tsx): Token forwarding and navigation handlers.
  10. [`dashboard/src/components/CustomerPortal.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/CustomerPortal.tsx): Token propagation to connections and terminal views.
  11. [`verify_phase4_1_frontend.js`](file:///opt/tauric-platform-staging/verify_phase4_1_frontend.js): Headless Puppeteer verification and responsive screenshot capture suite.
