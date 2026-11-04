# BITDEX.LTD — Phase 4.6: Customer-Owned Account Connectivity & Acceptance Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Host:** `169.58.218.168` | `https://bitdex.ltd`  
**Date:** 2026-11-04  
**Safety Status:** `live_trading_locked = True` | `emergency_lock_active = True` | `read_only_mode = True`

---

## 1. Executive Summary

Phase 4.6 validates that every BITDEX customer independently connects, manages, and executes trading workflows on their own Exness accounts under strict tenant isolation.

Administrator Exness credentials are completely isolated and never serve as customer fallbacks. Customer credentials are encrypted at rest with **AES-256-GCM** in SQLite. Multiple Demo and Real accounts per customer are supported with safe preferred-account switching. Disconnecting an account immediately purges credentials and revokes the active session. Cross-tenant access and mutation attempts return **HTTP 404 Not Found**.

All 12 automated acceptance criteria passed with **100% success**. Responsive layout tests across all 6 viewports (360px, 390px, 430px, 768px, 1024px, 1440px) confirmed zero horizontal overflow and strict **chartless compliance (0 canvases, 0 TradingView widgets)**.

---

## 2. Multi-Tenant Isolation & Account Ownership Matrix

| Security Control | Implementation Detail | Test Verification Result |
| :--- | :--- | :---: |
| **Strict Tenant Isolation** | All queries filtered strictly by `user_id = ?`. Customer B cannot query Customer A accounts. | **PASSED** (Test 7) |
| **Zero Admin Leakage** | Admin logins (`149827361`, `460310009`) never appear in customer responses or status cards. | **PASSED** (Test 9) |
| **Cross-Tenant Mutation Guard** | Customer B attempting to disconnect or set preferred on Customer A account returns `HTTP 404`. | **PASSED** (Test 8) |
| **AES-256-GCM Vault** | Passwords encrypted with authenticated ciphertext and 12-byte random nonces; zero plaintext. | **PASSED** (Test 5) |
| **Credential Invalidation on Disconnect** | Disconnect sets `is_active = 0` and wipes `encrypted_credentials = '{}'`. | **PASSED** (Test 6) |
| **Multiple Accounts per Customer** | Customers can hold multiple Demo accounts + Real account simultaneously. | **PASSED** (Test 3) |
| **Preferred Account Switching** | Atomic switching of active account per environment with zero data races. | **PASSED** (Test 4) |
| **Numeric Login Format Validation** | Non-numeric MT5 logins rejected with clean `HTTP 400 Bad Request`. | **PASSED** (Test 10) |
| **Session Revocation** | Revoking a customer's session immediately blocks subsequent API calls with `HTTP 401`. | **PASSED** (Test 11) |

---

## 3. Responsive Viewport & Chartless Compliance Audits

A full headless Puppeteer audit was conducted on staging (`https://bitdex.ltd`) across all 6 required viewport widths:

| Viewport Width | Device Target | Layout Behavior | Overflow Detected? | Charts / Canvases |
| :---: | :--- | :--- | :---: | :---: |
| **360 px** | Small mobile (Galaxy S8) | Single-column stacked cards, full-width buttons | **NO (0px overflow)** | **0 (Chartless)** |
| **390 px** | Standard mobile (iPhone 12/13/14) | Single-column stacked cards, responsive typography | **NO (0px overflow)** | **0 (Chartless)** |
| **430 px** | Large mobile (iPhone Pro Max) | Single-column optimized cards, legible badges | **NO (0px overflow)** | **0 (Chartless)** |
| **768 px** | Tablet portrait (iPad Mini) | Two-column responsive grid, collapsible sidebar | **NO (0px overflow)** | **0 (Chartless)** |
| **1024 px** | Tablet landscape / Small laptop | Three-column dashboard grid, persistent navigation | **NO (0px overflow)** | **0 (Chartless)** |
| **1440 px** | Desktop monitor | Full institutional 3-card layout, level matrix | **NO (0px overflow)** | **0 (Chartless)** |

### Chartless Verification Summary:
- Canvases: **0**
- TradingView Widgets: **0**
- Recharts / Sparklines: **0**
- Candlestick Graphs: **0**
- Total Graphical Charts: **0 (100% Compliant)**

---

## 4. Automated Acceptance Test Results (`backend/test_phase4_6_customer_acceptance.py`)

```
================================================================================
BITDEX PHASE 4.6 AUTOMATED ACCEPTANCE SUITE
CUSTOMER-OWNED ACCOUNTS, STRICT TENANT ISOLATION & LIFECYCLE
================================================================================

================================================================================
BITDEX PHASE 4.6 ACCEPTANCE VERIFICATION SUMMARY
================================================================================
[✓]  1. Customer Demo Account Connection & Masking       | PASSED   | Connection created with masked ID 55****11
[✓]  2. Customer Real Account Ingestion (Read-Only)      | PASSED   | Real account ingested with read-only clamp; live orders locked
[✓]  3. Multiple Accounts Support per Customer           | PASSED   | Customer successfully holds 2 Demo accounts and 1 Real account
[✓]  4. Preferred Account Selection per Environment      | PASSED   | Preferred account switched to secondary demo without data race
[✓]  5. Encrypted Credential Storage (AES-256-GCM)       | PASSED   | AES-256-GCM ciphertext + nonce verified in SQLite; zero plaintext passwords
[✓]  6. Account Disconnect & Credential Invalidation     | PASSED   | Account deactivated, stored AES credentials completely wiped on disconnect
[✓]  7. Strict Cross-Tenant Account Isolation            | PASSED   | Customer B cannot view Customer A accounts, balances, or status cards
[✓]  8. Cross-Tenant Mutation Rejection (404 Not Found)  | PASSED   | Cross-tenant disconnect and preferred mutation strictly rejected with HTTP 404
[✓]  9. Zero Administrator Account Leakage               | PASSED   | Admin MT5 accounts completely hidden from customers; admin mutation blocked
[✓] 10. Invalid Account Credentials Validation           | PASSED   | Non-numeric login and malformed requests rejected with clean HTTP 400/422
[✓] 11. Session Revocation Enforcement                   | PASSED   | Revoked customer session immediately rejected with HTTP 401 Unauthorized
[✓] 12. Strict Chartless Institutional UI Verification   | PASSED   | Zero candlestick, TradingView, or graphical charts found in customer frontend
================================================================================
RESULTS: 12 PASSED | 0 FAILED
================================================================================
```
