# BITDEX — PHASE 7B.7: RECURRING CAS COLLISION & DUPLICATE TENANT ACCOUNT OWNERSHIP REMEDIATION

**Document Reference**: `BITDEX_PHASE_7B7_RECURRING_CAS_COLLISION_REMEDIATION.md`  
**Execution Timestamp**: `2026-11-08T00:10:00Z`  
**Git Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Staging Host**: `169.58.218.168` (Ubuntu 24.04 LTS / WireGuard `10.88.0.1`)  
**Windows MT5 Gateway**: `149.33.34.123:8095` (Windows Server 2022 / WireGuard `10.88.0.2`)  
**Target Account**: Exness MT5 Demo `#474861031` (`Exness-MT5Trial15`)  
**Primary Tenant**: `USR-ADM-B022F490` (`hello@nexura.ltd`)  
**Secondary Tenant (Conflict)**: `USR-66BCFD7350` (`admin@tauric.com`)  
**Target Symbol**: `BTCUSD`  
**Conflicting Tokens Investigated**: `LSE-bed6ec473ba3b7ea` (BTCUSD) & `LSE-578fc79592d138dd` (XAUUSD)  
**Safety Invariants**: `live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True` (ZERO live orders dispatched)  

---

## 1. Executive Summary & Forensic Investigation Findings

During Phase 7B.6, an Engine Exclusivity Mutual Lock (CAS) collision was resolved for `XAUUSD` (`LSE-578fc79592d138dd`). However, upon navigating to `BTCUSD`, the live dashboard reported a recurring CAS lock:
- **Symbol**: `BTCUSD`
- **Conflicting Engine**: `ENGINE_B`
- **Reported Lease Token**: `LSE-bed6ec473ba3b7ea`
- **Dashboard State**: `BLOCKED`

### Database Forensic Trace of `LSE-bed6ec473ba3b7ea`
Direct query of the authoritative SQLite database table `futures_symbol_leases` revealed:

```json
{
  "account_id": "FACC-1A8017734CFA",
  "symbol": "BTCUSD",
  "engine_id": "ENGINE_B",
  "lease_token": "LSE-bed6ec473ba3b7ea",
  "acquired_at": "2026-11-07T18:13:20Z",
  "expires_at": "2026-11-07T19:13:20Z",
  "status": "ACTIVE",
  "metadata_json": "{}"
}
```

Cross-referencing `FACC-1A8017734CFA` against `futures_accounts`, `users`, and `exness_demo_connections`:
- **Owning User**: `USR-ADM-B022F490` (`hello@nexura.ltd`)
- **Physical Broker Login**: `474861031` on server `Exness-MT5Trial15`
- **Connection Record**: `EXN-CONN-A4E7BE39D276` (`is_preferred: 1`, `is_active: 1`, `verification_status: VERIFIED`)

### Discovery of Duplicate Physical Broker Registration
Inspection of `exness_demo_connections` revealed that the same physical login `474861031` was registered under two distinct SaaS users:
1. `EXN-CONN-A4E7BE39D276` → `USR-ADM-B022F490` (`hello@nexura.ltd`, Primary Owner).
2. `EXN-CONN-3D40DE9B8CE8` → `USR-66BCFD7350` (`admin@tauric.com`, synthetic test seed from `/tmp/register_mt5_account.py`).

In institutional multi-tenant architecture, physical broker accounts cannot be concurrently registered to multiple unrelated tenants without authorized delegation.

---

## 2. Root Cause Determination

The recurring collision was traced to two compounding defects:

### Root Cause 1: Un-Scoped Account Lookup in Backend Endpoints
In `backend/app/routes/saas_customer.py`:
1. `get_hft_pretrade_validation_route` queried:
   ```python
   acc_row = conn.execute("SELECT * FROM futures_accounts WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (user_id,)).fetchone()
   ```
   For `hello@nexura.ltd`, who owns multiple connections (Binance LIVE and Exness MT5 Demo), SQLite consistently returned `FACC-64F5ABB5E75F` (the Binance account), not `FACC-1A8017734CFA` (the Exness account).
2. When comparing the active lease (`active_lease["account_id"] == my_account_id`):
   - `active_lease["account_id"]` was `FACC-1A8017734CFA` (Exness).
   - `my_account_id` evaluated to `FACC-64F5ABB5E75F` (Binance).
   - The comparison failed! The backend reported that the session was locked by "another account", creating an **artificial self-collision** where the rightful owner was blocked by its own active session.
3. `stop_hft_session_route` suffered from the identical flaw: it updated `futures_symbol_leases WHERE account_id = 'FACC-64F5ABB5E75F'`, releasing **0 rows**, leaving the Exness lease `LSE-bed6ec473ba3b7ea` permanently orphaned and active!

### Root Cause 2: Absence of Physical Broker Account Uniqueness Enforcement
The Exness connection provisioning service lacked a cross-tenant uniqueness check on `account_login`. When synthetic scripts registered login `474861031` under `USR-66BCFD7350`, it created duplicate bindings to the same physical terminal worker (`INST-474861031`), violating tenant isolation.

---

## 3. Remediation Actions

### 1. Remediate Duplicate Broker Account Binding
In `exness_demo_connections`:
- Preserved historical record `EXN-CONN-3D40DE9B8CE8` for complete audit integrity.
- Deactivated duplicate:
  - `is_active = 0`
  - `is_preferred = 0`
  - `verification_status = 'DUPLICATE_TENANT_CONFLICT'`
  - `error_type = 'DUPLICATE_PHYSICAL_BINDING'`
  - `error_detail = 'Physical account 474861031 on Exness-MT5Trial15 is exclusively registered to primary tenant USR-ADM-B022F490 (hello@nexura.ltd).'`

### 2. Implement Strict Physical Broker Uniqueness Policy
In `backend/app/services/exness/exness_db.py` (`save_exness_connection`):
```python
# Strict Physical Broker Uniqueness: Verify account_login is not already registered under another user
other_owner = conn.execute(
    "SELECT user_id, connection_id FROM exness_demo_connections WHERE account_login = ? AND user_id != ? AND is_active = 1 LIMIT 1",
    (login, user_id)
).fetchone()
if other_owner:
    raise ValueError(
        f"DUPLICATE_BROKER_ACCOUNT_CONFLICT: Physical broker account {login} on {server} "
        f"is already registered to another user ({other_owner['user_id']}). "
        "Multi-tenant duplicate registration without authorized delegation is prohibited."
    )
```

### 3. Correct Scoped Account Resolution & Disarm in Backend
In `backend/app/routes/saas_customer.py`:
- In `get_hft_pretrade_validation_route`: When `account_id` is supplied, strictly resolve `sel_acct = _resolve_hft_account(conn, user_id, account_id)` and scope `futures_accounts WHERE user_id = ? AND (account_id = ? OR exchange_connection_id = ?)`.
- Enriched `collision_detail` payload:
  - `account_id`: Conflicting account ID (`FACC-1A8017734CFA`)
  - `owning_email`: Masked tenant email (`hello@nexura.ltd`)
  - `broker_login`: Masked login (`4748•••031`)
  - `broker_server`: `Exness-MT5Trial15`
  - `engine_id`: `ENGINE_B`
  - `lease_token`: Active lease token
  - `expires_at`: ISO timestamp
  - `recovery_explanation`: Actionable instructions for disarm or lazy expiration.
- In `stop_hft_session_route`: Scoped account lookup to `_resolve_hft_account(conn, user_id, req.account_id)`. Rejects cross-tenant stops with HTTP 404. Cleanly releases the exact lease on the scoped account and disables `engine_b_enabled`.

### 4. Client-Side State Clearing & Dynamic Collision Feedback
In `dashboard/src/components/InstitutionalTradingDashboard.tsx`:
- On `selectedAccountId` change: immediately clears stale client-side session state (`setSessionState("NOT_CONFIGURED")`, `setCollisionInfo(null)`, `setChecklist([])`, `setIsReady(false)`).
- Section 4 subtitle and click-to-inspect toasts dynamically display conflicting account ID, masked login (`#4748•••031`), and recovery guidance.
- Guaranteed that whenever a collision exists, the session badge renders `BLOCKED` (never false `ACTIVE`).

---

## 4. Mandatory 12-Scenario Regression Audit Suite

The comprehensive regression suite (`/opt/tauric-platform-staging/test_phase7b7_regression.py`) was executed on the staging server:

| Scenario # | Test Description | Verification Condition | Result |
|:---:|:---|:---|:---:|
| **1** | BTCUSD Collision Attribution | Detects collision from un-owned account, reports `FACC-1A8017734CFA`, `#4748•••031`, `ENGINE_B` | **PASS** |
| **2** | Historical Leases & Lazy Expiry | Expired leases lazily marked `EXPIRED`, query returns `None`, historical rows preserved | **PASS** |
| **3** | Broker Account Uniqueness | `save_exness_connection` rejects duplicate active registration with `DUPLICATE_BROKER_ACCOUNT_CONFLICT` | **PASS** |
| **4** | Cross-Tenant Lease Isolation | Tenant B cannot stop or release Tenant A's lease (HTTP 404 unauthorized, lease remains active) | **PASS** |
| **5** | Engine A / Engine B Mutual Exclusion | CAS prevents Engine A from acquiring lease when Engine B holds active lock | **PASS** |
| **6** | Expired Lease Recovery | Expired lease safely reclaimed by new session without position collision | **PASS** |
| **7** | Active Lease Protection | Unexpired active lease cannot be overwritten by another account or engine | **PASS** |
| **8** | Scoped Session Stop & Release | Stop endpoint cleanly releases exact lease on scoped account (`status = RELEASED`) | **PASS** |
| **9** | Client-Side State Reset | Account switching clears stale session state; pre-trade validation reports clean `READY` | **PASS** |
| **10** | Session-Start Idempotency | Repeated start request on active session preserves active token without orphaning | **PASS** |
| **11** | Fail-Closed Safety | Failing gates (margin/consent/activation/CAS) never yield false `ACTIVE` state | **PASS** |
| **12** | Historical Data Preservation | Leases and connection records preserved in DB; clean disarm leaves 0 active leases | **PASS** |

**Total Score: 12 / 12 Scenarios Passed (100% Accepted)**

---

## 5. Visual Proof of Compliance

Two authoritative browser screenshots were captured via headless Chromium on the staging VPS:

1. **Owner Armed View**:
   - File: `phase7b7_owner_armed_readonly_btcusd.png`
   - Account: Exness Demo `#4748•••031` (`FACC-1A8017734CFA`)
   - Symbol: `BTCUSD`
   - State: `ARMED_READ_ONLY` (Cyan pulsing badge)
   - Pre-Trade Gates: All 9 security checks passed (`READY`)
   - Action Button: Rendered as red `Emergency Stop / Disarm`

2. **Cross-Account Collision Blocked View**:
   - File: `phase7b7_cross_tenant_collision_blocked.png`
   - Account: Exness Real `#1600•••657` (`FACC-268B3145465C`)
   - Symbol: `BTCUSD`
   - State: `BLOCKED` (Red glowing badge)
   - Section 4 Subtitle:
     > `Collision detected: Engine ENGINE_B holds active lock (LSE-5182c5b4bf7a545c) on account FACC-1A8017734CFA (Broker #4748•••031). Symbol BTCUSD is locked by ENGINE_B under account FACC-1A8017734CFA (Broker #4748•••031, User hello@nexura.ltd) until 2026-11-07T19:48:14Z. Disarm the active session on that account or wait for lease expiration to reclaim.`
   - Action Button: `Checklist Incomplete — Click to Inspect`

---

## 6. Post-Remediation Verification & Clean State

Following regression verification:
- `BTCUSD` was cleanly stopped and disarmed via `/customer/trading/hft/session/stop`.
- `XAUUSD` was cleanly stopped and disarmed via `/customer/trading/hft/session/stop`.
- Database query confirms **0 active leases** remaining in `futures_symbol_leases`.
- Platform remains strictly protected by triple locks: `live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True`. Zero orders were placed, modified, or cancelled on Exness or any other venue.
