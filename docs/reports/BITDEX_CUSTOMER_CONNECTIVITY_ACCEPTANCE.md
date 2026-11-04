# BITDEX — Customer Account Connectivity & Isolation Acceptance (Phase 6)

**Suite:** `backend/test_phase4_6_customer_acceptance.py`  
**Execution Environment:** Linux Staging Server (`169.58.218.168`)  
**Date:** November 5, 2026  
**Result:** **12 PASSED | 0 FAILED**

---

## 1. Multi-Tenant Customer Isolation Results

A rigorous two-customer test (`Customer A` and `Customer B`) was executed on staging to verify tenant boundaries and cryptographic credential safety:

| Test ID | Objective | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **01** | Connect Customer Demo Account | Masked ID (e.g. `55****11`) stored | Masked ID returned, encrypted creds stored | **PASSED** |
| **02** | Ingest Customer Real Account | Clamped to Read-Only | Read-only mode enforced; live trades locked | **PASSED** |
| **03** | Multiple Accounts Support | Multiple accounts per tenant | Customer held 2 Demo and 1 Real account concurrently | **PASSED** |
| **04** | Preferred Account Switching | Update active account preference | Preference toggled cleanly without race conditions | **PASSED** |
| **05** | AES-256-GCM Vault Integrity | Ciphertext + Nonce in SQLite | Verified zero plaintext passwords stored in database | **PASSED** |
| **06** | Account Disconnect Lifecycle | Wipe credentials on delete | Connection deactivated, credentials wiped | **PASSED** |
| **07** | Cross-Tenant Read Rejection | Customer B viewing Customer A | Customer B cannot view Customer A accounts or cards | **PASSED** |
| **08** | Cross-Tenant Mutation Rejection | Customer B modifying Customer A | Returns HTTP 404 (Not Found); zero cross-talk | **PASSED** |
| **09** | Admin Account Isolation | Customer access to Admin 460310009 | Admin accounts strictly excluded from customer responses | **PASSED** |
| **10** | Input Format Validation | Non-numeric MT5 login rejection | Clean HTTP 400 Bad Request returned | **PASSED** |
| **11** | Immediate Session Revocation | Reuse of token after logout | Returns HTTP 401 Unauthorized | **PASSED** |
| **12** | Chartless Mandate Verification | Zero canvas / TradingView elements | 100% chartless institutional UI validated | **PASSED** |

---

## 2. Cryptographic Storage Standards

- Exchange API keys and MT5 passwords are encrypted using an AES-256-GCM master vault key.
- Each stored credential uses an independent 96-bit CSPRNG initialization vector (nonce).
- The credential masking layer enforces account masking (e.g. `46****09`, `14****61`) in all logging and serialization layers.
