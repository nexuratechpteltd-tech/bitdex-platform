# BITDEX — Stage 5A: Runtime Safety Verification Report

## 1. Runtime & Process Evidence
- **PM2 #16 (`bitdex-overnight-experiment-supervisor`):** `PID 46520`, script `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py`, status `online`, restarts `36`, started `2026-11-15 19:52:03 +0100` (`18:52:03Z`). (**VERIFIED**)
- **PM2 #11 (`bitdex-longterm-protection-watchdog-staging`):** `PID 3271427`, script `/opt/tauric-platform-staging/backend/run_longterm_crash_watchdog.py`, status `online`, restarts `1`, started `2026-11-11 14:52:41 +0100`. (**VERIFIED**)
- **On-Disk `shared_risk_manager.py` SHA256:** `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` (matches Stage 4), mtime `2026-11-15 20:53:09 +0100`. (**VERIFIED**)
- **In-Memory Module Status of PM2 #16:** **NOT VERIFIED / STALE IN MEMORY** — PM2 #16 started ~61 minutes *before* `shared_risk_manager.py` was modified in Stage 4, so `PID 46520` is still running the pre-Stage 4 in-memory code. (**REQUIRES APPROVAL** for controlled reload)

## 2. Proposed Controlled Reload Procedure (DO NOT EXECUTE WITHOUT APPROVAL)
1. Confirm PM2 `#11` watchdog remains `online` to protect any open positions.
2. Account for existing open positions (`EURNZD`, `AUDUSD`, `XAUUSD`) and pending orders on `17000694512`.
3. Verify backup exists (`shared_risk_manager.py.bak_stage4`).
4. Execute `pm2 reload 16` (or `pm2 restart 16`).
5. Verify new PID start time is *after* `shared_risk_manager.py` mtime (`20:53:09 +0100`) and confirm `REAL_TRADING_PERMANENTLY_LOCKED=True` and `experiment_lock.json` integrity.

## 3. Safety Confirmation
- No processes were restarted/reloaded, no orders were placed, and `experiment_lock.json` remains untouched.
