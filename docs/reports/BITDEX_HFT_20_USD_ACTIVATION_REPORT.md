# BITDEX.LTD — Phase 2: One-Time USD $20.00 HFT Account Activation Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Environment:** `https://bitdex.ltd/#hft`  
**Status:** **IMPLEMENTED & VERIFIED (16/16 Backend Security & Lifecycle Tests Passing)**

---

## 1. Executive Summary & Business Rule Enforcement

Every BITDEX customer is now required to complete a **one-time USD $20.00 Account Activation** before High-Frequency Trading (HFT) strategy configuration, session arming, or live/demo HFT order execution is unlocked.

### Enforced Access Boundaries
- **Allowed Before Activation (`NOT_ACTIVATED` / `PAYMENT_PENDING` / `PAYMENT_FAILED`)**:
  - Customer registration, login, and full navigation across all 10 portal destinations.
  - Opening `https://bitdex.ltd/#hft` in **View-Only Mode** without crashing or blocking the dashboard.
  - Inspecting HFT eligible pairs (`GET /api/v1/saas/customer/trading/hft/pairs`), read-only strategy parameters (`GET /api/v1/saas/customer/trading/hft/config`), pre-trade safety checklists (`GET /api/v1/saas/customer/trading/hft/validation`), and quantitative simulations.
- **Strictly Blocked Until Activated (`HTTP 403 ACCOUNT_ACTIVATION_REQUIRED`)**:
  - Saving or modifying HFT strategy configurations (`POST /api/v1/saas/customer/trading/hft/config`).
  - Arming or starting an autonomous HFT session (`POST /api/v1/saas/customer/trading/hft/session/start`).
  - Submitting HFT orders (`POST /api/v1/hft/exness/order` and `POST /api/v1/hft/exness/trade/execute`).
- **Administrator Exemption**:
  - Administrator accounts (`ADMIN` / `OWNER`) are automatically recognized as exempt (`is_admin_exempt = True`, `activation_status = "ACTIVE"`).

---

## 2. Database Schema (`saas_db.py` & `activation_service.py`)

Two dedicated SQLite tables were added and initialized in `/opt/tauric-platform-staging/backend/tauric_saas.db`:

```sql
CREATE TABLE IF NOT EXISTS hft_account_activations (
    activation_id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVATED', -- NOT_ACTIVATED, PAYMENT_PENDING, ACTIVE, PAYMENT_FAILED, REVOKED
    activation_amount REAL NOT NULL DEFAULT 20.0,
    currency TEXT NOT NULL DEFAULT 'USD',
    payment_reference TEXT,
    payment_provider TEXT, -- BINANCE_PAY, CRYPTO_USDT, STRIPE, ADMIN_OVERRIDE
    activated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hft_activation_webhooks (
    event_id TEXT PRIMARY KEY,
    payment_reference TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
```

---

## 3. Backend Service & API Endpoints

Implemented in [activation_service.py](file:///opt/tauric-platform-staging/backend/app/services/activation_service.py), [saas_customer.py](file:///opt/tauric-platform-staging/backend/app/routes/saas_customer.py), and [exness_hft.py](file:///opt/tauric-platform-staging/backend/app/routes/exness_hft.py):

| Endpoint | Method | Auth Boundary | Purpose |
| :--- | :--- | :--- | :--- |
| `/api/v1/saas/customer/hft/activation/status` | `GET` | Customer JWT | Returns current customer activation status (`NOT_ACTIVATED`, `PAYMENT_PENDING`, `ACTIVE`, `PAYMENT_FAILED`, `REVOKED`), `$20.00` fee, and timestamps. |
| `/api/v1/saas/customer/hft/activation/checkout` | `POST` | Customer JWT | Generates a unique `PAY-HFT20-*` reference, transitions status to `PAYMENT_PENDING`, and writes `HFT_ACTIVATION_CHECKOUT_INITIATED` audit log. |
| `/api/v1/saas/customer/hft/activation/verify` | `POST` | Customer JWT | Verifies HMAC-SHA256 signature, exact `$20.00` amount, `USD` currency, and tenant ownership before transitioning to `ACTIVE`. |
| `/api/v1/saas/customer/hft/activation/webhook` | `POST` | HMAC-SHA256 Signed | Idempotent payment webhook processor using `hft_activation_webhooks(event_id)` to prevent replay attacks. |
| `/api/v1/saas/admin/customers/{user_id}/hft-activation` | `POST` | Admin JWT (`RBAC`) | Allows administrators to waive (`ACTIVE`) or revoke (`REVOKED`) a customer's HFT activation with full audit trail. |

---

## 4. Frontend Modal & UX Integration (`InstitutionalTradingDashboard.tsx`)

- **Header Activation Badge (`#hft-activation-badge`)**:
  - Displays `UNACTIVATED — ACTIVATE HFT ($20.00)` for unactivated customers (clicking opens the modal) and `HFT ACTIVATED ($20 VERIFIED)` once activated.
- **Pre-Trade Safety Checklist Gate**:
  - Added critical gate `HFT_ACCOUNT_ACTIVATION` (`One-Time $20.00 USD Account Activation`) as the first item in Step 3 (`Pre-Trade Safety Checklist`).
- **Action Interception & Branded Activation Modal (`#hft-activation-modal`)**:
  - Clicking **Configure Strategy ($20 Unlock)** or **Activate Account ($20.00) to Start HFT** while unactivated opens the branded modal:
    - Title: *"Activate Your BITDEX Account"*
    - Subtitle: *"Your account must be activated before you can use High-Frequency Trading."*
    - Fee Card: *"$20.00 USD — One-Time Activation Fee (Lifetime HFT Access)"*
    - Actions: **Pay $20.00 & Activate Account** and **Continue Viewing Dashboard**.

---

## 5. Automated Security & Invariant Verification (`test_phase6_activation_security.py`)

Executed on staging via `/opt/tauric-platform-staging/backend/.venv/bin/python3 test_phase6_activation_security.py`:

| # | Test Case | Expected Result | Observed Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| 01 | Initial customer activation status | `200 OK`, `NOT_ACTIVATED`, `$20.0` | `HTTP 200, status=NOT_ACTIVATED, fee=$20.0` | **PASS** |
| 02 | Read-only HFT endpoints while unactivated | `200 OK` on pairs, config, validation | `pairs=200, config=200, validation=200, checklist_gate_passed=False` | **PASS** |
| 03 | Unactivated customer `POST /trading/hft/config` | `403 ACCOUNT_ACTIVATION_REQUIRED` | `HTTP 403, error=ACCOUNT_ACTIVATION_REQUIRED` | **PASS** |
| 04 | Unactivated customer `POST /trading/hft/session/start` | `403 ACCOUNT_ACTIVATION_REQUIRED` | `HTTP 403, error=ACCOUNT_ACTIVATION_REQUIRED` | **PASS** |
| 05 | Unactivated customer `POST /hft/exness/order` | `403 ACCOUNT_ACTIVATION_REQUIRED` | `HTTP 403, error=ACCOUNT_ACTIVATION_REQUIRED` | **PASS** |
| 06 | Create `$20.00 USD` checkout | `200 OK`, `PAYMENT_PENDING` | `HTTP 200, ref=PAY-HFT20-7D300C5B936D, status=PAYMENT_PENDING` | **PASS** |
| 07 | Tampered/partial payment amount (`$19.99`) | `400 INVALID_ACTIVATION_AMOUNT` | `HTTP 400, error=INVALID_ACTIVATION_AMOUNT` | **PASS** |
| 08 | Wrong currency (`EUR`) | `400 INVALID_ACTIVATION_CURRENCY` | `HTTP 400, error=INVALID_ACTIVATION_CURRENCY` | **PASS** |
| 09 | Forged cryptographic payment signature | `400 INVALID_PAYMENT_SIGNATURE` | `HTTP 400, error=INVALID_PAYMENT_SIGNATURE` | **PASS** |
| 10 | Cross-tenant payment reference reuse (Customer B using Customer A's reference) | `403 CROSS_TENANT_PAYMENT_REFERENCE_FORBIDDEN` | `HTTP 403, error=CROSS_TENANT_PAYMENT_REFERENCE_FORBIDDEN` | **PASS** |
| 11 | Valid signed `$20.00 USD` payment verification | `200 OK`, `ACTIVE` | `HTTP 200, status=ACTIVE, activated_at=2026-11-04T19:42:34Z` | **PASS** |
| 12 | Duplicate webhook replay (`event_id` reuse) | `200 OK`, `idempotent_replay=True` | `HTTP 200, idempotent_replay=True` | **PASS** |
| 13 | Activated customer `POST /trading/hft/config` | `200 OK`, `CONFIGURED` | `HTTP 200, config_status=CONFIGURED` | **PASS** |
| 14 | Admin revocation (`REVOKED`) re-locks HFT immediately | `403 ACCOUNT_ACTIVATION_REQUIRED` | `revoke=200, post_revoke_start=403` | **PASS** |
| 15 | RBAC boundary & logout session revocation | `403` on admin route, `401` after logout | `rbac_block=403, logout=200, post_logout_access=401` | **PASS** |
| 16 | Global trading safety locks remain enabled | `live_trading_locked=True, read_only_mode=True` | `live_trading_locked=True, read_only_mode=True` | **PASS** |
