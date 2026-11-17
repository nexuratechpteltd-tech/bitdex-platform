# BITDEX — Stage 5B: Pre-Reload Readiness Report

## 1. Readiness Classifications
- **PM2 #11 (`bitdex-longterm-protection-watchdog-staging`):** `READY` (`online`, PID `3271427`, supervises open Long-Term positions).
- **Stage 4 Backup (`shared_risk_manager.py.bak_stage4`):** `READY` (SHA256: `c8879f953ef6d075b5a5710823945f1f4bbe13aed27ada5d841c382f3c200c87`).
- **Remediated `shared_risk_manager.py`:** `READY` (SHA256: `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5`).
- **Syntax & Import Verification (`py_compile` + `import`):** `READY` (`PY_COMPILE_OK`, `IMPORT_OK`; zero import/dependency/syntax issues).
- **`experiment_lock.json`:** `READY` (`authorized: true`, `account_id: 17000694512`, `authorized_strategies: ["LT_STRUCTURE_EURUSD"]`, `expires_at_utc: 2026-11-18T18:52:03Z`).
- **`REAL_TRADING_PERMANENTLY_LOCKED`:** `READY` (`True`).
- **Controlled Reload of PM2 #16:** `REQUIRES APPROVAL` (do not execute until explicit operator authorization).

## 2. Exact Reload & Rollback Commands
- **Controlled Reload:** `pm2 restart 16`
- **Rollback (if needed):**
  `cp /opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py.bak_stage4 /opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py && pm2 restart 16`
