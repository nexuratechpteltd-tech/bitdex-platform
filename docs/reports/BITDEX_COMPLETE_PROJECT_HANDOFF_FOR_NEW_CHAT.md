# BITDEX.LTD — COMPLETE MASTER PROJECT HANDOFF & CONTEXT DOCUMENT
**(For Starting a New Chat in ChatGPT / Antigravity)**

---

## 1. PROJECT & REPOSITORY IDENTITY

- **Project Name:** BITDEX (`https://bitdex.ltd`) — Institutional Digital Asset Intelligence, Spot Grid, Long-Term & High-Frequency Trading (HFT) Platform
- **GitHub Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`
- **Active Feature Branch:** `feature/hft-redesign-and-navigation-cleanup` *(All active work is pushed here; `main` branch has NOT been touched or merged)*
- **Latest Verified Remote HEAD Commit SHA:** `e8e040f434e5b9d5a3e5f4f25875a05f7caefc90`
- **Staging Environment URL:** `https://bitdex.ltd`
- **Staging Server Host:** `169.58.218.168` (`root`)
- **Staging Project Directory:** `/opt/tauric-platform-staging`
  - **Backend Directory:** `/opt/tauric-platform-staging/backend` (FastAPI, Python `.venv`, SQLite DB `tauric_saas.db`, Port `8002`, PM2 process: `tauric-backend-staging`)
  - **Frontend Directory:** `/opt/tauric-platform-staging/dashboard` (Next.js 14.2.13, TypeScript, TailwindCSS, Port `33900`, PM2 process: `tauric-dashboard-staging`)
  - **Watchdog Daemon:** PM2 process `bitdex-watchdog-staging`
  - **Reports Directory in Repo:** `/opt/tauric-platform-staging/docs/reports/`

---

## 2. COMPLETE CHRONOLOGICALCOMMIT HISTORY ON `feature/hft-redesign-and-navigation-cleanup`

Every phase of work is committed and pushed to GitHub (`origin/feature/hft-redesign-and-navigation-cleanup`) in clean sequential order:

| Commit SHA | Phase / Scope | Summary of Changes |
| :--- | :--- | :--- |
| `65892fe948af3a727f17b14ed08813a5b990743a` | **Phase 4.1 / 4.2 Baseline** | Initial HFT redesign, navigation cleanup, Exness MT5 & Trader API foundation, and Phase 4.2 independent live connectivity verification baseline |
| `cfb7bcc9101561503aebe36baf3fd54935f3aa45` | **Phase 4.3** | Windows Server MT5 Gateway deployment package (`mt5_gateway_server.py`, `deploy_windows_gateway.ps1`, `verify_mt5_terminal.py`, `gateway_watchdog.py`, `.env.gateway.template`) & Official Exness Trader API Ed25519 JWT (`EdDSA`) authentication |
| `6837aec113863db0fc477a14f524c63a11cf2ab8` | **Phase 4.4** | Rotated exposed gateway token (384-bit CSPRNG secret), customer-owned Demo/Real Exness account isolation, and Windows MT5 gateway verifier (`test_phase4_4_gateway_verifier.py`) |
| `ff95218a97c1e6e608e3345fb5d292694f37282b` | **Phase 4.5** | Customer-owned Exness Trader API Ed25519 connection & live verification (`test_phase4_5_trader_api.py`), per-customer encrypted credentials (`AES-128-CBC + HMAC-SHA256` Fernet), zero mock fallbacks |
| `93e76fc829547b476e4fb27bc0cb5cf07625836d` | **Phase 4.6** | Exness Partnership / Bilateral Deposit & Withdrawal IPN Webhook Verification (`exness_payments_service.py`, `test_phase4_6_payments.py`) |
| `810527262d916420e026e270f384845f59c441db` | **Phase 5.0** | Quantitative HFT Strategy Backtest & Paper-Trading Expectancy Harness (`hft_strategy_validator.py`, `test_phase5_strategy.py`) with net-of-spread/slippage/commission calculations |
| `b85750aa5c55dc26b77c4e514f09d846b0d91572` | **Phase 6.0** | Comprehensive Security Audit, RBAC & Tenant Isolation Verification (`test_phase6_security.py`) and Master Completion Reports |
| `d74a1c549d1b9d6dc9e024ffed2ff03a3417a9bf` | **GitHub Reconciliation** | Removed obsolete legacy CORS origins (`tauric.pro`), verified all Phase 4.4–6.0 reports and test suites in `docs/reports/` |
| `e8e040f434e5b9d5a3e5f4f25875a05f7caefc90` | **Master Stability, $20 HFT Activation, Logout Fix & SEO (LATEST HEAD)** | Fixed `#hft` React Error #321 crash, implemented $20.00 USD one-time HFT activation workflow (DB + API + UI Modal), fixed backend session logout revocation + 0ms frontend token purge, upgraded SEO & robots isolation, added `test_phase6_activation_security.py`, and committed all 8 Final Acceptance Reports |

---

## 3. WHAT HAS BEEN COMPLETED & VERIFIED SO FAR (DETAILED BREAKDOWN)

### A. Phase 4.2 & 4.3 — Exness MT5 Gateway & Official Trader API Architecture
1. **Honest Broker Status (Zero Fake Data / Zero Mock Fallbacks):**
   - Previously, the platform had a mock fallback when the Windows MT5 Gateway was unreachable. That was completely removed.
   - If a customer has not connected an account or the Windows MT5 Gateway (`127.0.0.1:8005` / external Windows VPS) is offline, the API returns honest `DISCONNECTED` / `GATEWAY_UNREACHABLE (HTTP 503)` status with `balance: null, equity: null`.
2. **Windows MT5 Gateway Deployment Package (`backend/mt5_gateway/`):**
   - Ready-to-deploy package for Windows Server 2022 (`mt5_gateway_server.py`, `deploy_windows_gateway.ps1`, `verify_mt5_terminal.py`, `gateway_watchdog.py`).
   - Supports separate Demo (`Exness-MT5Trial*`) and Real (`Exness-MT5Real*`) validation, constant-time `hmac.compare_digest` bearer token authentication, and read-only safety lock enforcement.
3. **Official Exness Trader API (`backend/app/services/exness_trader_api.py`):**
   - Uses genuine **Ed25519 asymmetric cryptographic signing (`EdDSA` JWT)** with customer-supplied `api_key_id` and `private_key_pem`, plus live REST token exchange and WebSocket quote streaming (`wss://rtapi-sg.eccalls.mobi/rtapi/mt5/...`).

### B. Phase 4.4, 4.5, 4.6, 5.0 & 6.0 — Isolation, Payments, Strategy & Security
1. **Gateway Token Rotation (Phase 4.4):**
   - Rotated the gateway token exposed in an earlier report to a new 384-bit CSPRNG secret (`sha256` fingerprint prefix: `a198332ef807fd97...`). Old token is rejected with `HTTP 403`.
2. **Customer-Owned Demo & Real Account Isolation (Phase 4.4 & 4.5):**
   - Every customer connects their own Demo and Real accounts (`user_exchange_connections` and `exness_customer_connections` tables).
   - Cross-tenant access between Customer A and Customer B is blocked at the SQL query and API handler layers (`HTTP 404/403`), and administrator account `460310009` is never exposed to customers.
3. **Exness Bilateral Payments & IPN Service (Phase 4.6):**
   - Implemented `backend/app/services/exness_payments_service.py` with HMAC-SHA256 webhook verification, idempotency protection against replay attacks (`exness_payment_webhooks`), and automatic failsafe fallback when IPN credentials are not yet provisioned (`ipn_configured: false`).
4. **HFT Quantitative Strategy Harness (Phase 5.0):**
   - Implemented `backend/app/services/hft_strategy_validator.py`. Evaluates Micro-Scalping / Order-Book Imbalance strategies net of realistic Exness spread, slippage, and commission, with automatic `AUTO_SHUTDOWN_NEGATIVE_NET_EXPECTANCY` kill-switch protection.

### C. Master Stability, $20.00 HFT Activation, Logout Fix & SEO (Latest Execution — Commit `e8e040f`)

#### 1. Phase 1 — Critical `#hft` Client-Side Crash Fixed (`https://bitdex.ltd/#hft`)
- **Root Cause Found:**
  1. In `dashboard/src/components/CustomerPortal.tsx`, a `useEffect` hook was nested *inside* the `navigateTo` click handler callback, triggering **React Error #321 (`Invalid hook call`)** whenever a user clicked **HFT** in the sidebar.
  2. `navigateTo` referenced `setActiveTab`, `setSettingsSubTab`, and `setTradingMode` before their `useState` declarations (Temporal Dead Zone reference error in production builds).
  3. Multiple components (`CustomerPortal.tsx`, `ProtectionCenter.tsx`, `InstitutionalConsole.tsx`, `UnifiedSignalDashboard.tsx`, `ExchangeConnectionsView.tsx`, `FundingTransfersView.tsx`) had local `const token = localStorage.getItem('tauric_jwt')` variables shadowing the valid `token` prop (`bitdex_session_token`), causing background `HTTP 401` and `HTTP 404` responses.
- **Fix Verified:**
  - Removed the illegal nested `useEffect`, hoisted state declarations above `navigateTo`, fixed `token` prop usage across all 6 components, and added `/api/v1/:path*` proxy rewrite in `dashboard/next.config.mjs`.
  - Verified in headless Chromium on `https://bitdex.ltd/#hft`: **`0` uncaught exceptions, `0` console errors, `0` HTTP 401/404/500 errors**.

#### 2. Phase 2 — One-Time USD `$20.00` Customer HFT Activation Feature
- **Database Schema (`backend/app/services/saas_db.py` & `activation_service.py`):**
  - `hft_account_activations`: Tracks `user_id`, `activation_status` (`NOT_ACTIVATED`, `PENDING_PAYMENT`, `ACTIVE`, `REVOKED`), `required_amount_usd` (`20.00`), `paid_amount_usd`, `currency` (`USD`), `payment_Reference`, `payment_provider`, `payment_method`, `activated_at`, `revoked_at`, `audit_metadata_json`.
  - `hft_activation_webhooks`: Prevents duplicate webhook replay processing via ` UNIQUE` `event_id` + `payload_sha256`.
- **Backend Endpoints & Enforcement (`backend/app/services/activation_service.py`, `saas_customer.py`, `exness_hft.py`):**
  - `GET /api/v1/saas/customer/hft/activation/status` — Returns real activation state from SQLite.
  - `POST /api/v1/saas/customer/hft/activation/checkout` — Generates a `$20.00 USD` payment intent (`HFT-ACT-...`) with HMAC-SHA256 verification signature.
  - `POST /api/v1/saas/customer/hft/activation/verify` — Verifies exact `$20.00 USD` amount, currency (`USD`), tenant ownership (`403 CROSS_TENANT_PAYMENT_REFERENCE_FORBIDDEN` if another user's reference is used), and HMAC-SHA256 signature (`403 INVALID_PAYMENT_SIGNATURE` if tampered).
  - `POST /api/v1/saas/customer/hft/activation/webhook` — Idempotent payment webhook receiver.
  - `POST /api/v1/saas/admin/customers/{user_id}/hft-activation` — Admin manual activation / revocation with audit logging.
  - **Server-Side Gate (`assert_hft_activated`)**: Blocks unactivated customers with `HTTP 403 ACCOUNT_ACTIVATION_REQUIRED` on:
    - `POST /api/v1/saas/customer/trading/hft/config`
    - `POST /api/v1/saas/customer/trading/hft/session/start`
    - `POST /api/v1/hft/exness/order`
    - `POST /api/v1/hft/exness/trade/execute`
  - **Pre-Trade Validation Gate**: Added `HFT_ACCOUNT_ACTIVATION` (`CRITICAL`) to `GET /api/v1/saas/customer/trading/hft/validation`.
- **Frontend UI (`dashboard/src/components/InstitutionalTradingDashboard.tsx`):**
  - Unactivated customers can open `#hft` in **View-Only Mode** without crashing.
  - Header displays `#hft-activation-badge`: **`UNACTIVATED — ACTIVATE HFT ($20.00)`** (amber) or **`HFT ACTIVATED ($20 VERIFIED)`** (emerald).
  - Clicking **Configure Strategy**, **Save Parameters**, or **Start Session** while unactivated opens the branded **`$20.00 USD` One-Time HFT Activation Modal** (`#hft-activation-modal`) with **Pay & Activate ($20.00)** (`#btn-pay-activate-20`), **Confirm $20.00 Payment** (`#btn-confirm-activate-20`), and **Continue Viewing (Read-Only)** (`#btn-continue-viewing-hft`).

#### 3. Phase 3 & 4 — Customer Logout & Session Revocation Fix
- **Backend P0 Bug Fixed (`backend/app/services/auth_manager.py`):**
  - Previously, `AuthManager.get_user_from_token` did not attach `u_dict["session_id"] = session_id` to the user dictionary returned to route handlers. As a result, `POST /api/v1/saas/auth/logout` saw `session_id = None` and never marked `sessions.revoked = 1` in SQLite.
  - Fixed `get_user_from_token` to include `session_id`. Now `POST /api/v1/saas/auth/logout` immediately marks `sessions.revoked = 1`, and any subsequent API call with the logged-out JWT returns **`HTTP 401 Session expired or revoked`**.
- **Frontend Logout Fixed (`dashboard/src/app/page.tsx` & `SidebarNav.tsx`):**
  - `handleSignOut` now synchronously purges all 9 session keys from `localStorage` (`bitdex_session_token`, `bitdex_user`, `tauric_jwt`, etc.), clears `window.location.hash` via `window.history.replaceState(null, "", window.location.pathname)`, resets React state to `PublicLandingPage` in `0ms`, and fires the backend revocation call with `keepalive: true`.

#### 4. Phase 5, 7 & 9 — Full 10-Destination Regression, 6 Viewports, Chartless Mandate & SEO
- **All 10 Customer Portal Destinations Verified (`0` errors, `0` `<canvas>`, `0` TradingView widgets):**
  - `#overview`, `#terminal`, `#long-term`, `#hft`, `#connections`, `#funding`, `#balances`, `#orders`, `#settings`, `#support`
- **All 6 Responsive Viewports Verified (`0px` horizontal overflow):**
  - `360x800`, `390x844`, `430x932`, `768x1024`, `1024x768`, `1440x900`
- **SEO & Public/Private Indexing Separation:**
  - Public Landing Page (`/`): Title `57 chars`, Description `151 chars`, `index, follow`, Canonical `https://bitdex.ltd`, OpenGraph + Twitter Card, JSON-LD `FinancialService` + `SoftwareApplication` schema, single `<h1>`.
  - Authenticated Portal: Dynamically sets `<meta name="robots" content="noindex, nofollow, noarchive">` so private customer states are never indexed.

---

## 4. INDEPENDENT TEST SUITE RESULTS (`74 PASSED | 2 BLOCKED | 0 FAILED`)

All automated verification suites are located in `/opt/tauric-platform-staging/backend/`:

| Test Script | Result | What It Verifies |
| :--- | :--- | :--- |
| `test_phase6_activation_security.py` | **16 PASSED, 0 FAILED** | Initial `NOT_ACTIVATED` state, read-only HFT access, `403` blocks on config/start/order, `$20.00` checkout, `$19.99` partial rejection, `EUR` currency rejection, forged HMAC rejection, cross-tenant reference block, valid `$20.00` activation, webhook replay idempotency, post-activation config save, admin revocation, logout `401` revocation, global safety locks |
| `test_phase4_4_gateway_verifier.py` | **12 PASSED, 1 BLOCKED, 0 FAILED** | Gateway token rotation, Customer A/B MT5 isolation, admin `460310009` non-exposure, honest `503` when Windows MT5 host is offline (*1 Blocked: external Windows Server host*) |
| `test_phase4_5_trader_api.py` | **10 PASSED, 1 BLOCKED, 0 FAILED** | Ed25519 JWT signing, customer isolation, disconnected trade prevention (*1 Blocked: customer live Exness API key provisioning*) |
| `test_phase4_6_payments.py` | **11 PASSED, 0 FAILED** | Bilateral IPN HMAC-SHA256 verification, replay idempotency, cross-customer deposit rejection, failsafe when IPN unconfigured |
| `test_phase5_strategy.py` | **9 PASSED, 0 FAILED** | Net-of-cost expectancy, spread/slippage/commission deduction, negative expectancy kill-switch |
| `test_phase6_security.py` | **16 PASSED, 0 FAILED** | Global safety locks (`live_trading_locked`, `emergency_lock_active`, `read_only_mode`), Fernet encryption at rest, RBAC, CORS hardening |

---

## 5. GLOBAL SAFETY LOCKS (CURRENTLY ACTIVE)

All three global trading safety locks remain strictly **ENABLED** on staging (`/opt/tauric-platform-staging/backend/app/config.py`):
- `live_trading_locked = True`
- `emergency_lock_active = True`
- `read_only_mode = True`

**Zero live or demo broker orders have been placed, and zero real customer charges have been executed.**

---

## 6. REMAINING EXTERNAL INFRASTRUCTURE DEPENDENCIES (OUTSIDE REPOSITORY CODE)

All software engineering, database, security, UI/UX, and automated testing tasks inside the repository are **100% complete**. The only remaining items before live production trading are external provisioning steps:

1. **External Blocker 1 — Windows Server 2022 + MetaTrader 5 Terminal Host:**
   - Provision a Windows Server 2022 VPS and run `backend/mt5_gateway/deploy_windows_gateway.ps1` with MetaTrader 5 installed.
   - Update `MT5_GATEWAY_URL` in `/opt/tauric-platform-staging/backend/.env` to point to the Windows Server over WireGuard/TLS.
2. **External Blocker 2 — Customer-Owned Exness Trader API Key Provisioning:**
   - Register customer Exness Personal Area Ed25519 public key and connect via `#connections` in the BITDEX Customer Portal.
3. **External Blocker 3 — Exness Partnership Bilateral IPN & Live Checkout Merchant Credentials:**
   - Obtain approved Exness Partnership Merchant ID & IPN HMAC secret (`EXNESS_PARTNERSHIP_MERCHANT_ID`, `EXNESS_IPN_HMAC_SECRET`) and live checkout webhook secret (`HFT_ACTIVATION_WEBHOOK_SECRET`) to switch from signed internal checkout to live merchant settlement.

---

## 7. ALL REPORTS AVAILABLE IN REPOSITORY (`docs/reports/`)

When inspecting the repository on branch `feature/hft-redesign-and-navigation-cleanup`, all detailed audit and completion reports are located in `docs/reports/`:
1. `docs/reports/BITDEX_MASTER_FINAL_ACCEPTANCE_REPORT.md`
2. `docs/reports/BITDEX_HFT_20_USD_ACTIVATION_REPORT.md`
3. `docs/reports/BITDEX_HFT_CRASH_FIX_REPORT.md`
4. `docs/reports/BITDEX_LOGOUT_AND_AUTHENTICATION_FIX_REPORT.md`
5. `docs/reports/BITDEX_FULL_PLATFORM_REGRESSION_REPORT.md`
6. `docs/reports/BITDEX_SEO_AUDIT_REPORT.md`
7. `docs/reports/BITDEX_SECURITY_REVALIDATION_REPORT.md`
8. `docs/reports/BITDEX_REMAINING_EXTERNAL_BLOCKERS.md`
9. `docs/reports/BITDEX_FINAL_RECONCILIATION_REPORT.md`
10. `docs/reports/BITDEX_MASTER_COMPLETION_REPORT.md`
11. `docs/reports/BITDEX_PHASE_4_4_REPORT.md`
12. `docs/reports/BITDEX_PHASE_4_5_REPORT.md`
13. `docs/reports/BITDEX_PHASE_4_6_REPORT.md`
14. `docs/reports/BITDEX_PHASE_5_REPORT.md`
15. `docs/reports/BITDEX_PHASE_6_SECURITY_AUDIT.md`

---

## 8. READY-TO-PASTE PROMPT FOR YOUR NEW CHAT (CHATGPT OR ANTIGRAVITY)

Copy and paste the block below into your new ChatGPT or Antigravity chat along with this `.md` file:

```markdown
# BITDEX.LTD — CONTINUATION FROM MASTER HANDOFF

**Repository:** https://github.com/nexuratechpteltd-tech/bitdex-platform
**Active Branch:** `feature/hft-redesign-and-navigation-cleanup`
**Latest Verified Commit SHA:** `e8e040f434e5b9d5a3e5f4f25875a05f7caefc90`
**Staging URL:** https://bitdex.ltd
**Staging Server:** `root@169.58.218.168` (`/opt/tauric-platform-staging`)

Please read the attached `BITDEX_COMPLETE_PROJECT_HANDOFF_FOR_NEW_CHAT.md` and inspect the repository branch `feature/hft-redesign-and-navigation-cleanup` (including `docs/reports/BITDEX_MASTER_FINAL_ACCEPTANCE_REPORT.md`).

All work through Phase 4.1–6.0 and the Master Stability, $20.00 HFT Activation, Logout Session Revocation Fix, 10-Destination Regression, and Technical SEO Command is complete and verified at commit `e8e040f434e5b9d5a3e5f4f25875a05f7caefc90` (`74 PASSED | 2 BLOCKED | 0 FAILED`).

Confirm that you have reviewed the full project state, commit history, architecture, and remaining external infrastructure items so we can discuss the next steps.
```
