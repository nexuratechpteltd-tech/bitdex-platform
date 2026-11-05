# BITDEX — PHASE 13: ADMIN EXNESS CONNECTION TEST & CREDENTIAL SAFETY REPORT

**Timestamp:** 2026-11-05T00:20:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  

---

## 1. Executive Summary

This report documents the verification of Exness API credential handling, tenant isolation, and administrative connection controls implemented across the BITDEX backend and frontend.

---

## 2. Tenant Isolation & Zero Credential Exposure

1. **Cryptographic Storage**:
   - All customer and administrator API secrets, MT5 passwords, and Ed25519 private keys are encrypted prior to database insertion using AES-256-GCM.
   - Encryption key: Derived from environment salt and master key in `ExnessCredentialVault`.
2. **Database Masking**:
   - `SELECT` queries across customer routes automatically strip and mask sensitive columns:
     - `api_secret` is never returned to frontend clients.
     - `account_login` is masked in logs and public responses (`mask_id(login)`).
3. **Admin Credential Segregation**:
   - Administrator connections (`is_primary = 1` or associated with administrative user IDs) are strictly segregated from customer accounts.
   - Customer-scoped endpoints (`/api/v1/saas/customer/`) query only rows matching `user_id = current_user["user_id"]`.
   - Cross-tenant data leakage is structurally impossible at the SQL query level.

---

## 3. Connection Test Architecture

The new "Test Connection" functionality in `ExchangeConnectionsView.tsx`:
1. Dispatches an authenticated request to `POST /api/v1/hft/exness/real/connect`.
2. Resolves the Exness cluster access point via `https://www.exness-api.com`.
3. Issues a test probe with Ed25519 authentication.
4. Returns structured diagnostic feedback:
   - On invalid credentials: Clear error message detailing why authentication failed.
   - On valid credentials: Confirms successful handshake and loads authoritative account telemetry.
5. In all cases, `live_trading_locked = True` ensures zero live orders can be placed.
