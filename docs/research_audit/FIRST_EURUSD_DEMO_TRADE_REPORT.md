# BITDEX — First Actual EURUSD Demo Trade Report

- **Timestamp (UTC):** `2026-11-15T20:13:53Z`
- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Decision:** **BLOCKED / NO ORDER PLACED**

## Step 1 Safety Gate Failures (Execution Halted)
1. **Gate 2 FAILED (`gate_2_pm2_16_loaded_stage4: False`):** PM2 `#16` (`PID 46520`) started *before* Stage 4 remediated `shared_risk_manager.py` and has not yet been reloaded.
2. **Gate 5 FAILED (`gate_5_concurrency_blocked: True`):** `experiment_lock.json` sets `max_concurrent_positions = 1`, while `3` legacy positions (`EURNZD`, `AUDUSD`, `XAUUSD`) are already open.

## Outcome
Per Step 1 (*"If any gate fails, STOP. Do not bypass it"*), no `EURUSD` order was submitted.
