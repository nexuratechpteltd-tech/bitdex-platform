# TAURIC PLATFORM — PHASE 3.7 PRODUCTION CUTOVER PRE-EXECUTION CHECKLIST

**Checklist Verification Timestamp:** 2026-10-22T04:58:30Z  
**Target Release Artifact:** `/opt/tauric-platform-releases/tauric-release-v3.6.1.tar.gz` (11 MB)  
**Target Release Directory:** `/opt/tauric-platform-releases/v3.6.1`  
**Cutover Engine:** `/opt/tauric-platform-releases/failsafe_cutover.py`  
**Production Boundary:** Hard Read-Only Boundary Enforced (`/opt/tauric-platform/` UNTOUCHED)  
**Lead Auditor:** Antigravity Autonomous Infrastructure & Security Agent  

---

## Final Pre-Execution Readiness Matrix

| Item # | Verification Requirement | Status | Concrete Evidence & Verification Details |
| :---: | :--- | :---: | :--- |
| **1** | Release Archive SHA-256 Verification | **PASS** | `42d2f13b1d6990f0348a0aa9bdb423d9a0470d8b4b473d7f9c354744a06a7a7d` confirmed |
| **2** | Production Health & Process Uptime | **PASS** | `tauric-backend` (PID 75730, 35h+ online), `tauric-dashboard` (PID 88836, 31h+ online), Portal HTTP/2 200 OK |
| **3** | Pre-Cutover Backup Integrity | **PASS** | `/opt/tauric-backups/production_backup_pre_v3.6.0` verified (0700, `.env` 0600); sandbox restore confirmed |
| **4** | Fail-Safe Engine, Allowlist & Locks | **PASS** | Target allowlist strictly enforces `['/opt/tauric-platform']` + `--execute-production`; `fcntl.flock` concurrency lock verified |
| **5** | Data & Secrets Protection Invariant | **PASS** | Live `.env`, `data/` (`jobs_registry.json`), `.venv/`, and `node_modules/` strictly excluded from switch paths |
| **6** | Stop Conditions & Deep Health Checks | **PASS** | Precondition abort, post-reload verification (`status=HEALTHY`, title marker, 6 API providers), auto-rollback on failure |
| **7** | Live Trading Hard-Locks Enforced | **PASS** | `live_trading_locked=true`, `read_only_mode=true`, live order submission returns HTTP 403 Forbidden |
| **8** | Safe Rollback Without Data Overwrite | **PASS** | Rollback restores code/build pointers (35 ms) without touching active `data/` or `.env` |

---

## 1. Item 1: Release Archive Hash & Integrity Verification

- **Archive File:** `/opt/tauric-platform-releases/tauric-release-v3.6.1.tar.gz`
- **Calculated SHA-256:** `42d2f13b1d6990f0348a0aa9bdb423d9a0470d8b4b473d7f9c354744a06a7a7d`
- **Expected Hash:** `42d2f13b1d6990f0348a0aa9bdb423d9a0470d8b4b473d7f9c354744a06a7a7d`
- **Verification Match:** **EXACT MATCH (PASS)**
- **Release Directory:** `/opt/tauric-platform-releases/v3.6.1/` (100% diff correspondence with extracted archive).
- **Frontend Build ID:** `dashboard/.next/BUILD_ID` = `yqDUznSNBWoD6Vb9qC8SB` (**PASS**).

---

## 2. Item 2: Production Health, PM2 Status & Portal Availability

- **Process `tauric-backend` (PM2 ID 0):**
  - PID: 75730
  - Uptime: **35 hours continuous**
  - Memory: 271.4 MB (Stable)
  - Endpoint `http://127.0.0.1:8001/api/v1/health`: `{"status": "HEALTHY", "uptime_seconds": 126133}`
- **Process `tauric-dashboard` (PM2 ID 1):**
  - PID: 88836
  - Uptime: **31 hours continuous**
  - Memory: 60.2 MB (Stable)
  - Local Port 8080: `HTTP/1.1 200 OK`
- **Canonical Portal:** `https://sheltr.agency/trading/`
  - Response: `HTTP/2 200 OK`
  - Protocol: HTTPS with Let's Encrypt TLS v1.3
  - Status: Continuously serving traffic without disruption.

---

## 3. Item 3: Pre-Cutover Backup & Verification

- **Full Production Snapshot:** `/opt/tauric-backups/production_backup_pre_v3.6.0/`
- **Permissions:** `drwx------` (Mode `0700`, accessible exclusively by root).
- **Secrets Security:** `backend/.env` is mode `0600` (`-rw-------`).
- **Data Completeness:** Contains full baseline `jobs_registry.json`, `ai_ledger.json`, `shadow_validation/`, `app/`, `src/`, and `.next/`.
- **Sandbox Restoration Test:** Restored into `/tmp/rollback_test_sandbox/`; verified 100% SHA-256 match with active production files.
- **Local Instant Rollback Pointers:** In addition to the full backup snapshot, local pre-cutover backups (`app_pre_cutover`, `src_pre_cutover`, `.next_pre_cutover`) will be created by `failsafe_cutover.py` during Step 1-3, enabling instantaneous **35 ms** recovery.

---

## 4. Item 4: Fail-Safe Script, Allowlist, Concurrency Lock & Rollback

- **Script Path:** `/opt/tauric-platform-releases/failsafe_cutover.py` (Executable, root-owned).
- **Allowlist Guard:** `ALLOWED_PROD_ROOTS = ["/opt/tauric-platform"]`.
  - Rejects any run against `/opt/tauric-platform` unless `--execute-production` is explicitly passed.
  - Rejects any attempt to target staging or arbitrary directories.
  - Rejects symlinked target roots.
- **Concurrency Lock:** Uses non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` on `.cutover.lock`. Tested in sandbox: secondary concurrent executions are immediately blocked with exit code 1.
- **Filesystem-Truth Reconciliation:** Tested crash recovery without state journal: script discovers active symlinks and backup directories and safely unwinds the state.
- **Failure Injection Coverage:** Tested all 8 interruption points in sandbox:
  1. Precondition failure $\rightarrow$ clean abort.
  2. After backend switch $\rightarrow$ restored `app` to v0.
  3. After dashboard `src` switch $\rightarrow$ restored `src` and `app` to v0.
  4. After dashboard `.next` switch $\rightarrow$ restored all 3 paths to v0.
  5. Service reload error $\rightarrow$ auto-rollback to coherent v0.
  6. Post-deployment health failure $\rightarrow$ auto-rollback to coherent v0.
  7. Resumption from interrupted state $\rightarrow$ recovered to coherent v0.
  8. Happy path cutover $\rightarrow$ committed to release v3.6.1.

---

## 5. Item 5: Protection of Persistent Data, Secrets & Runtimes

The cutover engine operates strictly on code and compilation build pointers:
- **`backend/.env`:** UNTOUCHED (Permanent configuration outside switch scope).
- **`backend/data/`:** UNTOUCHED (Live `jobs_registry.json`, `ai_ledger.json`, and positions remain active).
- **`backend/.venv/`:** UNTOUCHED (Python virtual environment preserved).
- **`dashboard/node_modules/`:** UNTOUCHED (Installed npm dependencies preserved).
- **`backend/tradingagents/`:** Symlinked from release if not already present; preserved otherwise.

---

## 6. Item 6: Stop Conditions & Deep Post-Deployment Health Checks

The engine will automatically abort and unwind to the prior release if:
1. Preconditions fail (archive missing/mismatched, directory missing, backup path collision).
2. PM2 service reload returns non-zero exit code.
3. Portal `https://sheltr.agency/trading/` returns non-200 or lacks `"Tauric Platform"` marker.
4. Backend API `http://127.0.0.1:8001/api/v1/health` returns non-200 or `status != "HEALTHY"`.
5. Frontend internal proxy fails to return all 6 exchange providers (`BINANCE`, `BYBIT`, `COINBASE`, `OKX`, `KRAKEN`, `CUSTOM`).
6. Security invariants are violated.

---

## 7. Item 7: Safety Invariants & Live Trading Lock

- **Configuration:** `live_trading_locked=true` and `read_only_mode=true` are verified in `config.py`, `exchange_framework.py`, and runtime health endpoints.
- **Hard-Lock Proof:** `POST /api/v1/orders/live/submit` returns `HTTP 403 Forbidden`.
- **Position Authenticity:** 4 Seeded Fixtures and 8 Paper Simulations strictly maintain `is_exchange_confirmed=False`. Zero false exchange trades.
- **Zero Orders Rule:** No live exchange API orders will be submitted during or after cutover.

---

## 8. Item 8: Safe Non-Destructive Rollback (Zero Data Overwrite)

- **Rollback Mechanism:**
  ```bash
  rm /opt/tauric-platform/backend/app
  rm /opt/tauric-platform/dashboard/src
  rm /opt/tauric-platform/dashboard/.next
  mv /opt/tauric-platform/backend/app_pre_cutover /opt/tauric-platform/backend/app
  mv /opt/tauric-platform/dashboard/src_pre_cutover /opt/tauric-platform/dashboard/src
  mv /opt/tauric-platform/dashboard/.next_pre_cutover /opt/tauric-platform/dashboard/.next
  pm2 reload tauric-backend
  pm2 reload tauric-dashboard
  ```
- **Execution Time:** **35 ms** filesystem switch duration; **~2.8 - 3.2 seconds** total recovery with PM2 reload.
- **Zero Data Overwrite Guarantee:** Active order logs, shadow validation databases, and live positions created while v3.6.1 was running are **NOT** overwritten by stale snapshots during rollback.

---

## 9. Operational Readiness & Authorization Command

When separate explicit user authorization is provided, the cutover will be triggered with:

```bash
python3 /opt/tauric-platform-releases/failsafe_cutover.py \
  --prod-root /opt/tauric-platform \
  --release-root /opt/tauric-platform-releases/v3.6.1 \
  --archive /opt/tauric-platform-releases/tauric-release-v3.6.1.tar.gz \
  --execute-production \
  --action cutover
```

If emergency rollback is ever required:
```bash
python3 /opt/tauric-platform-releases/failsafe_cutover.py \
  --prod-root /opt/tauric-platform \
  --release-root /opt/tauric-platform-releases/v3.6.1 \
  --archive /opt/tauric-platform-releases/tauric-release-v3.6.1.tar.gz \
  --execute-production \
  --action recover
```

---

## 10. Final Production Confirmation

- **Production Filesystem:** `/opt/tauric-platform/` has received **ZERO** modifications.
- **Production Services:** PM2 processes (PID 75730 & PID 88836) have **NOT** been restarted or reloaded.
- **Current Portal:** `https://sheltr.agency/trading/` is serving `HTTP/2 200 OK`.
- **Status:** **STOPPED. All 8 checklist items PASS. Ready for cutover upon your explicit authorization.**
