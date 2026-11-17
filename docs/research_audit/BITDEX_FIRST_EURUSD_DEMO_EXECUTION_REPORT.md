# BITDEX — First Live EURUSD Demo Execution Report

- **Timestamp (UTC):** `2026-11-15T20:18:38Z`
- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Outcome Classification:** **TRADE BLOCKED / HOLD — NO VALID SIGNAL (FOREX MARKET CLOSED / STALE QUOTES)**

## 1. Completed Remediation & Safety Gates
- **Old Experiment Deactivated:** Backed up `experiment_lock.json` to `experiment_lock.json.bak_pre_master` and set `authorized: false`.
- **PM2 #11 (`bitdex-longterm-protection-watchdog-staging`):** Kept `online` (`PID 3271427`), supervising all `3` legacy positions (`73604866` `EURNZD`, `74667980` `AUDUSD`, `75087127` `XAUUSD`).
- **Controlled PM2 #16 Reload:** Restarted PM2 `#16` (`PID 63606`, `online`); verified `stage4_loaded_after_mtime: True` (Stage 4 `shared_risk_manager.py`, SHA256 `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5`).
- **`REAL_TRADING_PERMANENTLY_LOCKED`:** `True`.

## 2. Live EURUSD Market Analysis & Stop Condition
- **Latest Exness `EURUSD` M1 Candle:** `2026-11-13T21:58:00+00:00` (`bid=1.10217`, `ask=1.10223`, `spread=0.00006`).
- **Staleness:** ~46 hours old (Sunday `20:18:38Z` — Forex market is closed).
- **Decision:** **HOLD / TRADE BLOCKED** — Per Absolute Stop Conditions (*"Quotes are stale"* / *"Consensus is HOLD"*), no `EURUSD` order was submitted, and `experiment_lock.json` remains `authorized: false`.
