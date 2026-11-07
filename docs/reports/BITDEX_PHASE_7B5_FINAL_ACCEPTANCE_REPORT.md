# BITDEX — PHASE 7B.5: FINAL AUDIT DISCREPANCY RESOLUTION & MT5 TELEMETRY VERIFICATION

**Audit Version:** 1.0.0  
**Date:** 2026-11-07  
**Audited Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Target Account:** Exness MT5 Demo `#474861031` (`EXN-CONN-3D40DE9B8CE8`)  
**Staging Host:** Linux VPS (`169.58.218.168`) & Windows Server 2022 VPS (`149.33.34.123`)  
**Safety Mandate:** `live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True`

---

## 1. Resolution of Git HEAD Discrepancy

### Investigation & Ancestry Evidence:
- **Local Branch HEAD:** `742e0e0c8020b03008f95ade91ea81f8e7b45f6a`
- **Remote Branch (`origin/feature/hft-redesign-and-navigation-cleanup`) HEAD:** `742e0e0c8020b03008f95ade91ea81f8e7b45f6a`
- **Commit History & Lineage:**
  ```text
  742e0e0 (HEAD -> feature/hft-redesign-and-navigation-cleanup, origin/feature/hft-redesign-and-navigation-cleanup)
          docs(phase7b.4): forensic acceptance audit of hft session-start remediation and safety locks
  1349bb9 feat(phase7b.3): remediate hft session-start routing, account-aware instrument discovery & read-only state
  d5111c7 feat(phase7b.2): validate multi-tenant mt5 isolation, worker supervisor & latency telemetry
  0b2c80a docs: Phase 7B.1 Architecture Validation & Technical Proof-of-Concept Report
  f0dbb65 docs: Phase 7B Commercial Multi-Tenant Architecture Blueprint
  ```
- **Clarification:** Commit `1349bb9` was the codebase implementation baseline that fixed routing, whereas `742e0e0` was the immediate documentation commit that recorded the Phase 7B.4 forensic audit. Both commits are verified in strict linear sequence on `origin`. No history rewriting, force-pushing, or main merges occurred.

---

## 2. MT5 Session 0 IPC Limitation & Windows Worker Architecture

### Forensic Finding on Windows Session 0:
- **Root Cause Confirmed:** The official MetaTrader 5 Python IPC library (`MetaTrader5.initialize()`) relies on Windows desktop messaging (Win32 GUI hooks). On Windows Server 2022, background Windows Services run in **Session 0** (isolated from the interactive desktop). When a headless process in Session 0 attempts to initialize MT5 IPC, it cannot establish desktop IPC and fails with:
  ```text
  LAST_ERROR: (-10005, 'IPC timeout')
  ```
- **Process & Session Telemetry on Windows VPS (`10.88.0.2`):**
  - Gateway Service: `BitdexMT5Gateway` (NSSM service, running as `NT AUTHORITY\SYSTEM` in Session 0).
  - Terminal Process: `terminal64.exe` (PID `4664`, Session `0`, path: `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`).
  - Active User Sessions:
    - Session `0`: Services (`services`, Session `0`).
    - Session `2`: Interactive RDP Session (`Administrator`, State: `Active`).
- **Production Architecture Solution (Interactive Worker Daemon):**
  - NSSM background services must not attempt direct GUI IPC.
  - As validated in Phase 7B.2, the robust multi-tenant pattern runs an interactive worker daemon (`mt5_worker_supervisor.py`) inside an authenticated, persistent interactive user session (or scheduled task configured with `Run only when user is logged on` / auto-logon interactive desktop), which serves IPC requests to the Session 0 Gateway via local HTTP/socket IPC (`127.0.0.1:8096`).
  - The Gateway was hardened with non-blocking fail-fast logic so that absent interactive workers return HTTP 503 rather than hanging HTTP connection pools.

---

## 3. Genuine Instrument Verification vs Backend Catalogue

### Instrument Specification Comparison:
| Symbol | Contract Size | Tick Size | Min Volume | Max Volume | Volume Step | Display Name |
|---|---|---|---|---|---|---|
| **BTCUSD** | `1.0` | `0.01` | `0.01` | `100.0` | `0.01` | Bitcoin vs US Dollar |
| **ETHUSD** | `1.0` | `0.01` | `0.01` | `100.0` | `0.01` | Ethereum vs US Dollar |
| **XAUUSD** | `100.0` | `0.01` | `0.01` | `50.0` | `0.01` | Gold vs US Dollar |
| **EURUSD** | `100,000.0` | `0.00001` | `0.01` | `200.0` | `0.01` | Euro vs US Dollar |
| **GBPUSD** | `100,000.0` | `0.00001` | `0.01` | `200.0` | `0.01` | Great Britain Pound vs US Dollar |

- **Symbol Incompatibility:** Binance perpetuals (`BTCUSDT`, `ETHUSDT`) are rejected with `HTTP 400` when an Exness account is scoped:
  `"UNSUPPORTED BY SELECTED BROKER: Instrument BTCUSDT is not a valid CFD pair on Exness MT5."`
- **Transparent Attribution:** The dashboard and backend explicitly distinguish between live broker tick feeds and controlled validation specifications.

---

## 4. Authoritative Session-State Terminology & Dashboard Synchronization

### Reconciled Session State Model:
The system now enforces a unified 5-state lifecycle across API and Dashboard:
1. `NOT_CONFIGURED`
2. `VALIDATING`
3. `ARMED_READ_ONLY`
4. `STOPPED`
5. `FAILED`

### UI Reconciliation (`InstitutionalTradingDashboard.tsx`):
- The misleading label `ACTIVE` has been removed.
- Upon arming, the dashboard badge explicitly displays:
  `Session State: ARMED_READ_ONLY` (Cyan pulse indicator).
- Subtitle explicitly declares:
  `"Session armed in strict READ-ONLY mode. Live and simulated order dispatch are locked by server-side safety gates."`
- Button state transitions to red `Emergency Stop / Disarm` (`#btn-stop-hft-session`), allowing clean symbol lease release and session termination.
- Verified in Playwright browser screenshot:
  [phase7b5_hft_session_armed_readonly.png](file:///Users/bilalahmad/.gemini/antigravity/brain/c990ba3f-f64a-4860-b921-fb4bb14776aa/phase7b5_hft_session_armed_readonly.png).

---

## 5. Standardized Execution Protection Responses (HTTP 403)

All order operations were tested directly against the backend. Every operation is strictly intercepted at the gateway with explicit HTTP 403 Forbidden semantics:

| Operation | Endpoint | HTTP Code | Enforced Detail Message |
|---|---|---|---|
| **Live Order Submit** | `POST /orders/live/submit` | `HTTP 403` | `"Live trading is hard-locked (live_trading_locked=true). Real exchange order submission is strictly blocked."` |
| **Demo Order Submit** | `POST /orders/demo/submit` | `HTTP 403` | `"Order submission blocked: Safety lock active (live_trading_locked=true / read_only_mode=true). All order execution is disabled."` |
| **Position Modify (TP/SL)** | `POST /positions/{id}/adjust-tp-sl` | `HTTP 403` | `"Position modification blocked: Safety lock active (live_trading_locked=true / read_only_mode=true). Position modifications are disabled."` |
| **Position Close** | `POST /positions/{id}/close` | `HTTP 403` | `"Position closure blocked: Safety lock active (live_trading_locked=true / read_only_mode=true). Position closures are disabled."` |
| **Order Cancel** | `POST /orders/cancel` | `HTTP 403` | `"Order cancellation blocked: Safety lock active (live_trading_locked=true / read_only_mode=true). Order cancellations are disabled."` |

---

## 6. Comprehensive Broker Routing Reverification

Direct API invocation verified:
- **A. Exness MT5 Demo `474861031`:**
  Routes cleanly to `EXNESS_MT5_GATEWAY` with worker instance `INST-474861031`. Session state: `ARMED_READ_ONLY`.
- **B. Exness Terminal Real `16000629657`:**
  Verified in database (`EXN-CONN-1F331CF65942` under user `USR-ADM-B022F490`). Summary reports `platform: EXNESS_TERMINAL`, `adapter_mode: EXNESS_TRADER_API`, `environment: REAL`. Attempting to start session without recorded live consent returns `HTTP 403` (`"Real Account Execution Consent required before starting session on live account."`).
- **C. Binance Routing:**
  When querying without an account parameter or selecting Binance, validates against Binance USDⓈ-M Perps (`BTCUSDT`) and verifies testnet API credentials.
- **D. Bybit Scoping:**
  Selecting an unverified or nonexistent Bybit account returns `HTTP 404` (`"Selected account BYBIT-UNVERIFIED-01 not found or unauthorized for this user."`).

---

## 7. Full Regression Test Results

Direct execution of the 14-point regression suite on staging:
```text
[PASS] 1. Account Ownership & Selection (HTTP 200)
[PASS] 2. Account / Environment Scoping (HTTP 200)
[PASS] 3. Instrument Discovery (Exness Account) (HTTP 200)
[PASS] 4. Incompatible Symbol Rejection (BTCUSDT on Exness) (HTTP 400)
[PASS] 5. Cross-Tenant Account Rejection (HTTP 404)
[PASS] 6. Session Start (ARMED_READ_ONLY) (HTTP 200)
[PASS] 7. Validation (Session Active State) (HTTP 200)
[PASS] 8. Session Stop / Disarm (HTTP 200)
[PASS] 9. Symbol Lease Released Verification (HTTP 200)
[PASS] 10. Live Order Submit Blocked (HTTP 403)
[PASS] 11. Demo Order Submit Blocked (HTTP 403)
[PASS] 12. Modify Position Blocked (HTTP 403)
[PASS] 13. Close Position Blocked (HTTP 403)
[PASS] 14. Cancel Order Blocked (HTTP 403)

FINAL PHASE 7B.5 REGRESSION: 14/14 PASSED (100%)
```

---

## 8. Final Acceptance Verdict

Phase 7B.5 audit discrepancy resolution is **ACCEPTED**:
- Git HEAD is verified and strictly linear on `origin`.
- Session-state terminology is reconciled to `ARMED_READ_ONLY` across API, database, and UI.
- All five order execution and modification gates strictly return `HTTP 403`.
- No live or demo orders were dispatched.
