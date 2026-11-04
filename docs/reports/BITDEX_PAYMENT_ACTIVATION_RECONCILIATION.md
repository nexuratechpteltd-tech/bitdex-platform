# BITDEX — Payment & $20.00 USD HFT Activation Reconciliation Report (Phase 9)

**Service Implementation:** `backend/app/services/activation_service.py`  
**Test Suite:** `backend/test_phase6_activation_security.py`  
**Date:** November 5, 2026  
**Status:** **16 PASSED | MERCHANT SETTLEMENT PENDING**

---

## 1. Feature Specifications & Security Verification

The one-time USD $20.00 customer HFT activation pipeline was tested through automated suite `test_phase6_activation_security.py`:

| Test ID | Gate / Requirement Verified | Observed Behavior | Status |
| :--- | :--- | :--- | :--- |
| **01** | Initial Unactivated Status | Returns `NOT_ACTIVATED`, `fee: 20.0`, `currency: USD` | **PASSED** |
| **02** | Unactivated Read-Only Access | Open pairs, view config, validation runs cleanly | **PASSED** |
| **03** | Server-Side Config Gate | POST `/trading/hft/config` blocked with HTTP 403 | **PASSED** |
| **04** | Server-Side Session Gate | POST `/trading/hft/session/start` blocked with HTTP 403 | **PASSED** |
| **05** | Server-Side Order Gate | POST `/hft/exness/order` blocked with HTTP 403 | **PASSED** |
| **06** | Intent Creation | Intent generated (`PAY-HFT20-...`) with HMAC signature | **PASSED** |
| **07** | Amount Enforcement | Partial amount ($19.99) rejected with HTTP 400 | **PASSED** |
| **08** | Currency Enforcement | Non-USD (EUR) payment rejected with HTTP 400 | **PASSED** |
| **09** | Cryptographic HMAC Validation | Forged / tampered signatures rejected with HTTP 400 | **PASSED** |
| **10** | Tenant Reference Protection | Cross-tenant reference reuse rejected with HTTP 403 | **PASSED** |
| **11** | Customer Activation Flow | Exact $20.00 USD payment activates account (`ACTIVE`) | **PASSED** |
| **12** | Webhook Idempotency | Replay attack / duplicate webhook processed idempotently | **PASSED** |
| **13** | Post-Activation Capabilities | Customer permitted to configure and start HFT strategies | **PASSED** |
| **14** | Admin Revocation Override | Admin revocation immediately locks HFT execution | **PASSED** |
| **15** | Logout Session Revocation | Post-logout request immediately returns HTTP 401 | **PASSED** |
| **16** | Global Safety Barrier | `live_trading_locked = True`, `read_only_mode = True` | **PASSED** |

---

## 2. Payment Merchant Reconciliation (Honest Provider Audit)

1. **Internal Cryptographic Intent Sandbox:**
   In staging, payment intents and verification endpoints use internal HMAC-SHA256 signatures (`HFT_ACTIVATION_WEBHOOK_SECRET`).
2. **Real Customer Charges:**
   **Zero real customer funds or payment cards have been charged.** Test rows in SQLite reflect synthetic sandbox payment references.
3. **External Merchant Status:**
   A bilateral merchant agreement or external payment gateway API (e.g. Binance Pay Merchant API, Stripe, or NOWPayments) is **not yet connected with live API credentials**.
4. **Launch Dependency:**
   Before accepting live public funds, live merchant webhook credentials must be injected into `/opt/tauric-platform-staging/backend/.env`.
