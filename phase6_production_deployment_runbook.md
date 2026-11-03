# TAURIC — Phase 6: Controlled Production Deployment Plan
## Planning and Preflight Only — No Production Changes

**Document Reference:** `TAURIC-DEP-P6-20261023-01`  
**Execution Timestamp:** 2026-10-23T09:25:00Z / 2026-10-23 14:25:00 PKT  
**Target Release Version:** `v3.9.0` (Universal Exchange API Engine, Paper Lifecycle & Macroeconomic Pipeline Release)  
**Previous Production Version:** `v3.8.2` (Currently live at `/opt/tauric-platform/`)  
**Authorized Scope:** Planning, read-only inspection, and sandbox rehearsal only. Zero changes to `/opt/tauric-platform/`.  
**Host:** Germany VPS (`169.58.218.168`)  

---

> [!IMPORTANT]
> **SAFETY ATTESTATION — ZERO PRODUCTION MODIFICATIONS APPLIED:**  
> In strict accordance with the Phase 6 Master Command mandate:
> 1. No production files have been modified, copied, or deleted.
> 2. No production symlinks have been switched.
> 3. No production services or PM2 processes (`tauric-backend` PID 237023, `tauric-dashboard` PID 237032) have been stopped, reloaded, or restarted (both maintain uninterrupted >20h uptime).
> 4. `live_trading_locked=true` and `read_only_mode=true` remain permanently enforced.
> 5. Zero live orders, transfers, or withdrawals have been initiated or permitted.
> 6. All cutover and rollback rehearsals were conducted strictly in isolated `/tmp/*` sandboxes.
> 7. Every production command in this runbook is explicitly labeled **PROPOSED — NOT EXECUTED** and requires separate operator authorization.

---

## 1. Production Freeze & Read-Only Baseline

### 1.1 Current Production State Verification
- **Production Root:** `/opt/tauric-platform/`
- **Active Release Symlinks:**
  - `backend/app -> /opt/tauric-platform-releases/v3.8.2/backend/app`
  - `dashboard/src -> /opt/tauric-platform-releases/v3.8.2/dashboard/src`
  - `dashboard/.next -> /opt/tauric-platform-releases/v3.8.2/dashboard/.next`
- **Active Release Version:** `v3.8.2` (Build ID: `Y5eOWTuygExWQ-MyimqoU`)
- **PM2 Supervised Processes:**
  - `id 0`: `tauric-backend` (PID 237023, Port 8001, Uptime: 20h+, Memory: 284.2 MB, CPU: 0%)
  - `id 1`: `tauric-dashboard` (PID 237032, Port 8080, Uptime: 20h+, Memory: 60.9 MB, CPU: 0%)
- **Persistent Production Stores (Untouched):**
  - `/opt/tauric-platform/backend/data/credential_vault.json` (5,561 bytes)
  - `/opt/tauric-platform/backend/data/jobs_registry.json` (153,917 bytes)
  - `/opt/tauric-platform/backend/data/positions_store.json` (9,489 bytes)
  - `/opt/tauric-platform/backend/data/ai_ledger.json` (682 bytes)
  - `/opt/tauric-platform/backend/data/orders_store.json` (2 bytes)
  - `/opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db` (49,152 bytes)

---

## 2. Release Candidate Inventory & Traceability

### 2.1 Packaged Release Candidate (`v3.9.0`)
- **Release Archive:** `/opt/tauric-platform-releases/tauric-release-v3.9.0.tar.gz`
- **Archive Size:** 0.81 MB (848,272 bytes)
- **Archive SHA-256 Checksum:** `b8f2be25e739ae9cf14d88de6041a51135732c7662e305d98c91da8c13aff3ca`
- **Release Directory:** `/opt/tauric-platform-releases/v3.9.0/`
- **Next.js BUILD_ID:** `lVslMJ9K4zA5PbViLcpPc`
- **Release Manifest:** `/opt/tauric-platform-releases/release_manifest_v3.9.0.json`

### 2.2 Core Release Component Checksums
| Component | Release File Path | SHA-256 Checksum |
| :--- | :--- | :--- |
| **Backend Config** | `backend/app/config.py` | `61159846b45e85c2c7d91d96e5797fbc5a2c270d47ad048e42650058e578c74d` |
| **Connections Router** | `backend/app/routes/connections.py` | `0144f80879eb95e56e09dc0f6eefc4efb01fc34226a27e74360e224e7561858a` |
| **Orders Router** | `backend/app/routes/orders.py` | `e2a44f77c8e9d3d02613fa1fbb9c28893a7d97eefd2ea789a715fe359ad34bbf` |
| **Signals Router** | `backend/app/routes/signals.py` | `5b3f2317fdb0e3458c97dd36bb4809e20eb58cf441e8e4a90575d522f28ea36a` |
| **Exchange Framework** | `backend/app/services/exchange_framework.py` | `c3bbbe6bc7d6c698ba9c0490b4adabfe4122d4f20bf842103f5ec787ea2935fe` |
| **Paper Trading Engine** | `backend/app/services/paper_trading_engine.py` | `4ba43a4185fe97ca275e5251aeec4652c7c5df9b8f2bf2a6435ef00fa1b7f053` |
| **Finance Calendar Adapter**| `backend/app/services/finance_calendar_adapter.py` | `4b182cbce0da66c6b412bfd3e91122cf2bebb936a287fa3f990fe66f0d3fc35c` |
| **Dashboard UI** | `dashboard/src/components/UnifiedSignalDashboard.tsx`| `96d28c3ee594c79d67b2d29486c7d9eef4b89f02fe0d88009b0b46ae72605335` |
| **Proxy Route** | `dashboard/src/app/api/backend/[...slug]/route.ts` | `011851a0fdaa5d91413269ae992fd8cde69d68bada9b1086eeb5ce461b5a8193` |
| **BUILD_ID** | `dashboard/.next/BUILD_ID` | `lVslMJ9K4zA5PbViLcpPc` |

### 2.3 Comprehensive File & Configuration Diff
```
================================================================================
                    FILE DIFFERENCE AUDIT (Prod v3.8.2 vs Release v3.9.0)
================================================================================
ADDED FILES (1 new core service):
  + backend/app/services/paper_trading_engine.py
    (AST verified: zero network imports, pure in-memory & local store paper execution)

MODIFIED FILES (9 backend files, 1 dashboard component):
  * backend/app/config.py
    (Added macroeconomic calendar flags, TTL settings, and security token definitions)
  * backend/app/routes/connections.py
    (Universal 9-provider engine, MT5 bridge validation, capability discovery)
  * backend/app/routes/orders.py
    (Normalized order lifecycle states, paper submit/fill/cancel, 403 live lock)
  * backend/app/routes/signals.py
    (Macroeconomic calendar proxy & symbol risk filtering)
  * backend/app/services/exchange_framework.py
    (Binance Spot vs Futures routing, 9 provider adapters, AES-256-GCM + AAD vault)
  * backend/app/services/finance_calendar_adapter.py
    (FinanceCalendar 14-day rolling ingestion, blackout windows, fail-closed logic)
  * backend/app/services/dual_ai_engine.py
    (Independent Tauric & JeV advisory review with macroeconomic awareness)
  * backend/app/services/snapshot_engine.py
    (SHA-256 digest calculation for frozen market evidence)
  * backend/app/services/unified_signal_engine.py
    (Friction math, min 0.25% fee buffer, dynamic capital compatibility)
  * dashboard/src/components/UnifiedSignalDashboard.tsx
    (Macroeconomic calendar UI, blackout badges, paper trading console)

UNCHANGED CRITICAL INFRASTRUCTURE:
  = backend/app/main.py (Identical router registrations)
  = dashboard/src/app/api/backend/[...slug]/route.ts (Identical proxy)
  = dashboard/next.config.mjs (Identical build configuration)
  = backend/requirements.txt (78/78 Python dependencies 100% identical)
  = dashboard/package.json & package-lock.json (100% identical dependencies)
```

### 2.4 External Provider & Operational Limits
- **Finance Calendar API:** Free tier, 15-minute cache TTL ($\le 96$ req/day against 500 req/day limit).
- **Crypto Exchange Public Feeds:** Binance, Bybit, Bitget, OKX, Kraken, Coinbase public market data (rate-limited via adapter backoffs).
- **Forex Feeds:** MT5 / IC Markets require external MetaTrader 5 Terminal Bridge (handled gracefully as `Bridge Offline` when bridge is absent).
- **AI Advisories:** OpenAI / Venice.ai / Typesafe LLM backends (cached with daily token budgets and strict timeouts).

---

## 3. Controlled Production Deployment Runbook

### 3.1 Operator Prerequisites & Maintenance Window
- **Operator Access:** SSH access with root privilege to `169.58.218.168`.
- **System Requirements:** Disk space $\ge 5.0\text{ GB}$ available (current available: $81\text{ GB}$), RAM $\ge 2.0\text{ GB}$ available (current available: $6.3\text{ GB}$).
- **Proposed Maintenance Window:** Off-peak traffic window (Recommended: Tuesday or Wednesday 02:00–02:15 UTC).
- **Expected Service Interruption:** $< 3.0\text{ seconds}$ during zero-downtime PM2 worker recycling (`pm2 reload`). Existing TCP connections are drained gracefully.

---

### 3.2 Pre-Deployment Preflight Checks
Before executing any deployment action, verify that production is completely healthy:

```bash
# PROPOSED — NOT EXECUTED
# Preflight 1: Confirm PM2 processes are online and healthy
pm2 status

# Preflight 2: Verify production endpoints return 200 OK
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/api/v1/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/

# Preflight 3: Confirm live trading hard lock is currently active (must return 403)
curl -s -X POST http://127.0.0.1:8001/api/v1/orders/live/submit \
  -H "Content-Type: application/json" \
  -d '{"profile_id":"preflight","symbol":"BTCUSDT","side":"BUY","order_type":"LIMIT","price":60000,"quantity":0.001}' \
  | grep -o "Live trading is hard-locked"
```

---

### 3.3 Production Backup Procedure
Before altering any symlink, capture an immutable production baseline backup:

```bash
# PROPOSED — NOT EXECUTED
# Step 1: Create timestamped production backup directory
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
BACKUP_ARCHIVE="/opt/tauric-backups/pre_v3.9.0_production_backup_${TIMESTAMP}.tar.gz"

# Step 2: Archive full production directory (preserving permissions and timestamps)
tar -czvf "${BACKUP_ARCHIVE}" \
  --exclude="node_modules" \
  --exclude=".venv" \
  --exclude=".next/cache" \
  --exclude="__pycache__" \
  /opt/tauric-platform/

# Step 3: Compute and record backup SHA-256
sha256sum "${BACKUP_ARCHIVE}" > "${BACKUP_ARCHIVE}.sha256"
cat "${BACKUP_ARCHIVE}.sha256"

# Step 4: Verify backup archive readability
tar -tzvf "${BACKUP_ARCHIVE}" | grep "credential_vault.json"
```

---

### 3.3.1 SQLite Online Backup and Restore Verification
To guarantee complete ACID transaction consistency and prevent page-tearing or corrupted snapshots during live operation, an online backup of the SQLite database must be captured using SQLite's native backup facility prior to archive creation.

#### Prerequisites
1. `sqlite3` CLI installed on host (`sqlite3 --version` $\ge 3.45.1$, verified installed on system).
2. Write access to `/opt/tauric-backups/` with at least 500 MB free space.
3. Target source database: `/opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db`.

#### Execution Commands
```bash
# PROPOSED — NOT EXECUTED
# 1. Define target backup path
SQLITE_BACKUP_DEST="/opt/tauric-backups/shadow_validation_pre_cutover_${TIMESTAMP}.db"

# 2. Execute atomic online backup using SQLite CLI
sqlite3 /opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db \
  ".backup '${SQLITE_BACKUP_DEST}'"

# 3. Check exit code and verify backup file existence and size
if [ $? -eq 0 ] && [ -s "${SQLITE_BACKUP_DEST}" ]; then
  echo "PASS: SQLite native online backup succeeded: ${SQLITE_BACKUP_DEST} ($(stat -c%s "${SQLITE_BACKUP_DEST}") bytes)"
else
  echo "CRITICAL FAILURE: SQLite online backup failed! Aborting cutover."
  exit 1
fi
```

#### Integrity Verification
Immediately verify database pages, foreign keys, and schemas on the destination backup file:
```bash
# PROPOSED — NOT EXECUTED
# 1. PRAGMA integrity_check (Must return 'ok')
INTEGRITY=$(sqlite3 "${SQLITE_BACKUP_DEST}" "PRAGMA integrity_check;")
if [ "$INTEGRITY" = "ok" ]; then
  echo "PASS: SQLite PRAGMA integrity_check returned ok."
else
  echo "CRITICAL: SQLite integrity check failed: $INTEGRITY! Aborting cutover."
  exit 1
fi

# 2. PRAGMA foreign_key_check (Must return empty / 0 violations)
FK_VIOLATIONS=$(sqlite3 "${SQLITE_BACKUP_DEST}" "PRAGMA foreign_key_check;")
if [ -z "$FK_VIOLATIONS" ]; then
  echo "PASS: Zero foreign key violations."
else
  echo "CRITICAL: Foreign key violations detected: $FK_VIOLATIONS! Aborting cutover."
  exit 1
fi

# 3. Table and Row Count Verification
sqlite3 "${SQLITE_BACKUP_DEST}" "SELECT name FROM sqlite_master WHERE type='table';"
sqlite3 "${SQLITE_BACKUP_DEST}" "SELECT count(*) FROM shadow_decisions;"
```

#### Failure Handling & Recovery Procedure
If the SQLite online backup fails or returns integrity errors:
1. **Immediate Abort:** The deployment MUST NOT proceed. Symlinks must remain pointed to `v3.8.2`.
2. **Investigation:** Check disk space (`df -h /opt/tauric-backups`), check file locks (`fuser /opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db`), and inspect `/root/.pm2/logs/tauric-backend-error.log`.
3. **Database Recovery Procedure:** If the production database was flagged as corrupted:
   - Restore from the last verified good backup:
     ```bash
     # PROPOSED RECOVERY COMMAND — NOT EXECUTED
     cp "${LAST_VERIFIED_GOOD_BACKUP}" /opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db
     chmod 644 /opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db
     chown root:root /opt/tauric-platform/backend/data/shadow_validation/shadow_validation.db
     ```
   - Re-run `PRAGMA integrity_check;` on the restored database.


---

### 3.4 Production Cutover Execution Sequence
The deployment uses Tauric's audited atomic switch engine `/opt/tauric-platform-releases/failsafe_cutover.py`:

```bash
# PROPOSED — NOT EXECUTED
# Execute the atomic cutover with deep health verification
python3 /opt/tauric-platform-releases/failsafe_cutover.py \
  --prod-root /opt/tauric-platform \
  --release-root /opt/tauric-platform-releases/v3.9.0 \
  --archive /opt/tauric-platform-releases/tauric-release-v3.9.0.tar.gz \
  --expected-hash b8f2be25e739ae9cf14d88de6041a51135732c7662e305d98c91da8c13aff3ca \
  --expected-build-id lVslMJ9K4zA5PbViLcpPc \
  --execute-production
```

**Internal Actions Performed Atomically by `failsafe_cutover.py`:**
1. Validates `--prod-root` allowlist (`/opt/tauric-platform`).
2. Acquires exclusive POSIX file lock (`.cutover.lock`).
3. Verifies archive SHA-256 (`b8f2be25...`) and BUILD_ID (`lVslMJ9K4zA5PbViLcpPc`).
4. Verifies protected paths exist (`.env`, `data/`, `node_modules/`, `.venv/`).
5. Atomically switches symlinks via POSIX rename:
   - `backend/app -> /opt/tauric-platform-releases/v3.9.0/backend/app`
   - `dashboard/src -> /opt/tauric-platform-releases/v3.9.0/dashboard/src`
   - `dashboard/.next -> /opt/tauric-platform-releases/v3.9.0/dashboard/.next`
6. Reloads PM2 processes with zero downtime: `pm2 reload tauric-backend` and `pm2 reload tauric-dashboard`.
7. Executes deep health verification checks.
8. Writes committed state to `/opt/tauric-platform/.cutover_state.json`.

---

### 3.5 Post-Deployment Smoke Verification Suite
Execute immediately following service reload to confirm system integrity:

```bash
# PROPOSED — NOT EXECUTED
# Smoke 1: Verify Next.js frontend returns HTTP 200 and renders the new BUILD_ID
curl -s -i https://sheltr.agency/trading/ | grep -E "HTTP/|lVslMJ9K4zA5PbViLcpPc"

# Smoke 2: Verify Backend Health endpoint
curl -s http://127.0.0.1:8001/api/v1/health | grep '"status":"ok"'

# Smoke 3: Verify Live Trading Hard Lock (Mandatory 403 Forbidden check)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8001/api/v1/orders/live/submit \
  -H "Content-Type: application/json" \
  -d '{"profile_id":"post_deploy","symbol":"BTCUSDT","side":"BUY","order_type":"LIMIT","price":60000,"quantity":0.001}')
if [ "$HTTP_CODE" -eq 403 ]; then
  echo "PASS: Live trading lock is hard-enforced (HTTP 403)."
else
  echo "CRITICAL FAILURE: Live submit returned HTTP $HTTP_CODE! TRIGGER IMMEDIATE ROLLBACK!"
fi

# Smoke 4: Verify Capabilities endpoint (Transfers/Withdrawals must be absent)
curl -s http://127.0.0.1:8001/api/v1/connections/capabilities | grep -qv "transfer" && echo "PASS: Capability #14 absent."

# Smoke 5: Verify Macroeconomic Calendar Integration
curl -s http://127.0.0.1:8001/api/v1/signals/calendar | grep '"attribution_approved"' && echo "PASS: Macro calendar live."

# Smoke 6: Verify Paper Trading Ledger Summary
curl -s http://127.0.0.1:8001/api/v1/orders/paper/ledger/summary | grep '"cash_balance"' && echo "PASS: Paper ledger active."
```

---

## 4. State & Rollback Compatibility

### 4.1 Persistent Stores Protection
- **Zero In-Place DB Migrations:** SQLite databases (`shadow_validation.db`) use backwards-compatible append schemas.
- **Graceful Initialization:** The new paper trading stores (`paper_orders_store.json`, `paper_ledger_store.json`, `idempotency_store.json`) are self-initializing. If absent upon startup, they are created with default structures ($100k starting equity, empty order index) without affecting existing profiles or historical grid records.
- **Credential Vault Integrity:** Existing profile credentials in `credential_vault.json` remain encrypted under `TAURIC_VAULT_KEY` with AES-256-GCM and retain 100% read compatibility.

### 4.2 Rollback Procedure & Expected Duration
If any smoke test fails, latency spikes, or errors emerge during the observation period:

```bash
# PROPOSED — NOT EXECUTED
# Step 1: Execute atomic rollback to v3.8.2
python3 /opt/tauric-platform-releases/failsafe_cutover.py \
  --prod-root /opt/tauric-platform \
  --release-root /opt/tauric-platform-releases/v3.8.2 \
  --archive /opt/tauric-platform-releases/tauric-release-v3.8.2.tar.gz \
  --execute-production \
  --action recover

# Step 2: Reload PM2 processes
pm2 reload tauric-backend
pm2 reload tauric-dashboard

# Step 3: Verify rollback state
ls -la /opt/tauric-platform/backend/app  # Must point to v3.8.2
curl -s https://sheltr.agency/trading/ | grep -q "Y5eOWTuygExWQ-MyimqoU" && echo "PASS: Reverted to v3.8.2."
```

- **Rollback Execution Duration:** $< 2.0\text{ seconds}$ total.
- **Data Impact:** Zero data loss. Persistent `data/` and `.env` remain untouched.

---

## 5. Security & Safety Invariants

| Security Invariant | Guarantee Mechanism | Production Verification Rule |
| :--- | :--- | :--- |
| **Live Trading Locked** | Server-level config: `live_trading_locked = True` | `POST /orders/live/submit` unconditionally returns HTTP 403 Forbidden. |
| **Read-Only Mode** | Server-level config: `read_only_mode = True` | Exchange adapters reject all write/mutate API calls. |
| **Paper Isolation** | AST verified: zero network imports in engine | Paper execution engine cannot reach exchange APIs or network sockets. |
| **Transfer Disablement** | Capability #14 omitted from all adapter models | Transfer and withdrawal endpoints do not exist in route tables. |
| **Macro Fail-Closed** | `evaluate_event_risk` returns `UNKNOWN` on outage | Unverified/stale calendar feeds block setup approval with `WAIT`. |
| **Credential Privacy** | Masks API keys as `••••••••`; excludes secrets | Zero plaintext secrets in logs or API responses. |
| **Rate Limiter Hardening**| Token checked against server secret; rejects spoofing | Unauthenticated clients cannot bypass 10 req/min limits. |

---

## 6. Explicit Go / No-Go Decision Gates

The production cutover may proceed **ONLY** when all six gates evaluate to **GO**:

```
+-------------------------------------------------------------------------------+
|                             GO / NO-GO GATES                                  |
+--------+------------------------------------------+-----------------+---------+
| Gate   | Criteria                                 | Evidence        | Status  |
+--------+------------------------------------------+-----------------+---------+
| Gate 1 | Preflight Production Health Verified     | PIDs online     | [ GO ]  |
| Gate 2 | Baseline Production Backup Tested        | Sandbox restore | [ GO ]  |
| Gate 3 | Release v3.9.0 Packaged & Checksummed    | Archive verified| [ GO ]  |
| Gate 4 | Sandbox Cutover & Rollback Rehearsed     | Exit code 0     | [ GO ]  |
| Gate 5 | Staging Acceptance (168/168 checks pass) | Phase 4 log     | [ GO ]  |
| Gate 6 | Explicit User Cutover Authorization     | Awaiting user   | [HOLD]  |
+--------+------------------------------------------+-----------------+---------+
```

### Authorization Requirement
> [!CAUTION]
> **GATE 6 IS CURRENTLY ON HOLD.**  
> Execution of the proposed cutover commands will **NOT** begin until the user reviews this runbook and provides an explicit command authorizing production deployment.

---

## 7. Post-Deployment 24-Hour Observation Plan

Following an authorized deployment:
1. **First 15 Minutes:** Monitor PM2 logs continuously:
   - `pm2 logs tauric-backend --lines 50`
   - `pm2 logs tauric-dashboard --lines 50`
   - Check error rates and memory stability.
2. **First Hour:** Monitor Finance Calendar ingestion:
   - Confirm rolling 14-day horizon updates every 15 minutes.
   - Confirm memory usage stays $< 450\text{ MB}$ for backend and $< 150\text{ MB}$ for dashboard.
3. **24-Hour Checkpoint:** Run non-destructive production audit:
   - Confirm zero live trading attempts.
   - Confirm paper order lifecycle reconciliation matches simulated fills.
   - Verify ledger equity balances.

---
*Report certified in accordance with Phase 6 Master Command guidelines.*  
*Staging environment status: Stable and verified.*  
*Production environment status: Frozen, healthy, and isolated.*
