# BITDEX.LTD — Phase 3 & Phase 4: Customer Logout & Authentication Lifecycle Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Environment:** `https://bitdex.ltd`  
**Status:** **RESOLVED & VERIFIED (Immediate Session Revocation & Clean State Purge)**

---

## 1. Executive Summary & Root Cause Analysis

Independent auditing of the customer logout and session authentication lifecycle across both the FastAPI backend ([auth_manager.py](file:///opt/tauric-platform-staging/backend/app/services/auth_manager.py), [saas_customer.py](file:///opt/tauric-platform-staging/backend/app/routes/saas_customer.py)) and the Next.js frontend ([page.tsx](file:///opt/tauric-platform-staging/dashboard/src/app/page.tsx), [CustomerPortal.tsx](file:///opt/tauric-platform-staging/dashboard/src/components/CustomerPortal.tsx)) uncovered **three critical authentication and logout defects**:

### Defect 1 (Backend P0): `session_id` Omitted from `get_user_from_token` Return Dictionary
- **Root Cause**: In `AuthManager.get_user_from_token(token)` (`auth_manager.py` lines 1635–1660), the JWT payload's `session_id` was extracted to check `SELECT revoked FROM sessions WHERE session_id = ?`, but `u_dict = dict(user)` (queried from the `users` table) **never attached `u_dict["session_id"] = session_id`**.
- **Consequence**: When `POST /api/v1/saas/auth/logout` ran (`saas_customer.py` line 376):
  ```python
  session_id = current_user.get("session_id")
  if session_id:
      AuthManager.logout(session_id)
  ```
  `current_user.get("session_id")` was always `None`! As a result, `AuthManager.logout(session_id)` was never invoked, `sessions.revoked` remained `0` in SQLite, and logged-out JWT tokens remained valid until natural expiration.
- **Fix Implemented**: Added `u_dict["session_id"] = session_id` in `AuthManager.get_user_from_token(token)`. Immediately upon `POST /api/v1/saas/auth/logout`, `UPDATE sessions SET revoked = 1 WHERE session_id = ?` executes, and any subsequent request with the logged-out token is rejected with `HTTP 401 Session has been revoked or logged out`.

### Defect 2 (Frontend): Incomplete `localStorage` Token Purge on Logout
- **Root Cause**: `handleSignOut` in `dashboard/src/app/page.tsx` only removed `tauric_session_token` and `tauric_session_user`, leaving legacy/auxiliary keys (`bitdex_auth_token`, `tauric_token`, `bitdex_token`, `bitdex_active_account`, `bitdex_preferred_account`, `bitdex_customer_trades`) in `localStorage`.
- **Fix Implemented**: `handleSignOut` now explicitly purges all 9 session/account storage keys upon sign-out.

### Defect 3 (Frontend): Stale URL Hash Left Active After Logout
- **Root Cause**: Signing out from `#hft`, `#orders`, or `#settings` left `window.location.hash` intact on the public landing page, causing hash listeners to fire on subsequent logins or page transitions.
- **Fix Implemented**: `handleSignOut` now executes `window.history.replaceState(null, "", window.location.pathname + window.location.search)` to cleanly reset the URL hash before rendering `PublicLandingPage`.

---

## 2. Full Customer Authentication & Account Lifecycle Audit Matrix (Phase 4)

| Lifecycle Stage | Test Case | Expected Behavior | Verified Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1. Registration & Provisioning** | New customer account creation & session initialization | Creates isolated `USR-*` record, `NOT_ACTIVATED` HFT state, zero shared balances | Verified via `test_phase6_activation_security.py` & `test_phase4_6_customer_acceptance.py` | **PASS** |
| **2. Login & Token Issuance** | Valid customer login vs invalid password | Valid credentials issue signed HS256 JWT with `session_id`; wrong password returns `401` | Verified (`401 Unauthorized` on invalid credentials) | **PASS** |
| **3. Protected Route Access** | Unauthenticated request to `/api/v1/saas/customer/*` or `/api/v1/hft/exness/*` | Blocked by `TauricSecurityMiddleware` with `HTTP 401` | Verified across all customer & HFT endpoints | **PASS** |
| **4. Logout & Server Revocation** | `POST /api/v1/saas/auth/logout` followed by reusing the same Bearer JWT | Logout returns `200 OK`; immediate reuse of token returns `401 Session has been revoked` | Verified in `Test 15` (`logout=200, post_logout_access=401`) | **PASS** |
| **5. Frontend Logout State Reset** | Click **Sign Out** from `#hft` | Purges all `localStorage` tokens, clears `#hft` hash, returns to `PublicLandingPage` with 0 errors | Verified via Puppeteer E2E browser test | **PASS** |
| **6. RBAC Privilege Boundary** | Customer JWT attempting `POST /api/v1/saas/admin/*` or `/api/v1/saas/admin/customers/{id}/hft-activation` | Blocked with `HTTP 403 Admin privileges required` | Verified in `Test 15` (`rbac_block=403`) | **PASS** |
| **7. Cross-Tenant Isolation** | Customer B attempting to read or mutate Customer A's connections, balances, or `$20` payment references | Blocked with `HTTP 403` / `404`; zero data leakage | Verified in `Test 10` & `test_phase4_6_customer_acceptance.py` | **PASS** |
