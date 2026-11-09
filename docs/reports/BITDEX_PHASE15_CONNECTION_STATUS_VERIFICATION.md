# BITDEX — PHASE 15: CONNECTION STATUS INTEGRITY & VERIFICATION REPORT

**Authoritative System:** BITDEX Institutional Platform  
**Environment:** Linux Staging Server (`169.58.218.168`)  
**Domain:** `https://bitdex.ltd`  
**Git Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Timestamp:** 2026-11-05T12:45:00Z  

---

## 1. Executive Summary

A critical issue identified by the administrator was that exchange and broker connections were previously reported as "Connected" (with green badges) merely because a database record existed, even when no successful handshake had occurred.

Under Phase 15, connection status reporting has been strictly normalized. Green `VERIFIED` status is only assigned when genuine API communication with the external exchange or broker succeeds. Accounts that have not undergone successful verification are reported as `NOT TESTED`, and failed attempts are reported as `ERROR` or `DISCONNECTED`.

---

## 2. Permitted Connection Status Enum & Rules

In `backend/app/routes/saas_customer.py` (`_resolve_hft_account`), connection statuses strictly adhere to the following deterministic rules:

| Status Value | Meaning | Rule / Condition | Badge Display |
|--------------|---------|------------------|---------------|
| `VERIFIED` | Genuine authentication confirmed | Live API handshake succeeded; `last_verified_at` or `last_reconciled_at` is non-null. | Green pill (`VERIFIED`) |
| `NOT TESTED` | Saved credentials, unverified | Connection saved in database, but no live API probe has been executed yet (`last_verified_at IS NULL`). | Slate/Gray pill (`NOT TESTED`) |
| `DISCONNECTED` | Unreachable or disarmed | Broker adapter disconnected, session expired, or broker access point unreachable. | Red pill (`DISCONNECTED`) |
| `ERROR` | Authentication failed | Upstream broker rejected credentials (e.g. invalid signature, wrong IP whitelist). | Red pill (`ERROR`) |

---

## 3. Account-by-Account Audit on Staging

An audit of all connected accounts for the administrator (`test_customer@bitdex.io`) was executed via `GET /api/v1/saas/customer/trading/hft/connected-accounts`:

```
Account 1: Exness — Demo Account — #5550•••011
- Source: exness_demo_connections
- Environment: DEMO
- Last Reconciled: None
- Status: NOT TESTED
- Connected: False
- Available Balance: None (not fabricated)

Account 2: Exness — Real Account — #1600•••657
- Source: exness_demo_connections
- Environment: REAL
- Last Reconciled: None
- Status: NOT TESTED
- Connected: False
- Available Balance: None (not fabricated)

Account 3: Binance — Testnet Account — #CONN•••TED
- Source: user_exchange_connections (CONN-DK-BIN-DEMO-MIGRATED)
- Environment: DEMO (Testnet)
- Last Verified: 2026-10-30T08:52:23Z
- Status: VERIFIED
- Connected: True
- Available Balance: Real balance loaded from demo-api.binance.com

Account 4: Binance — Real Account — #CONN•••TED
- Source: user_exchange_connections (CONN-DK-BIN-LIVE-MIGRATED)
- Environment: REAL
- Last Verified: 2026-10-30T08:52:23Z
- Status: VERIFIED
- Connected: True
- Available Balance: Real balance loaded from api.binance.com

Account 5: Bitget — Testnet Account — #CONN•••TED
- Source: user_exchange_connections (CONN-DK-BIT-DEMO-MIGRATED)
- Environment: DEMO
- Last Verified: 2026-10-27T11:55:22Z
- Status: VERIFIED
- Connected: True

Account 6: Bitget — Real Account — #CONN•••TED
- Source: user_exchange_connections (CONN-DK-BIT-LIVE-MIGRATED)
- Environment: REAL
- Last Verified: 2026-10-27T11:55:22Z
- Status: VERIFIED
- Connected: True
```

---

## 4. Integrity Safeguards

1. **Zero Balance Fabrication**:
   When an account has not been verified (such as the Exness accounts), the API returns `available_balance = None` and `equity = None`. The trading interface renders `"—"` rather than displaying fabricated numbers.

2. **No Synthetic or Paper Trading Modes**:
   Synthetic paper trading accounts have been completely purged from the account selector. Only genuine broker-connected accounts appear.

3. **Cross-Tenant Isolation**:
   Every database query strictly binds `user_id = current_user["user_id"]`. Accounts belonging to other tenants or internal administrative fixtures cannot be selected or queried.
