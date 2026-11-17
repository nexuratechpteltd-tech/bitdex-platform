# BITDEX — Multi-Strategy Demo Trading Readiness Report

## 1. Exness DEMO Account & Open Positions (`17000694512`, `dx.2.trial.raw`)
- **Open Positions (`3`):** `73604866` (`EURNZD` SELL `0.01`), `74667980` (`AUDUSD` SELL `0.01`), `75087127` (`XAUUSD` BUY `0.01`) — all supervised by PM2 `#11` (`online`).
- **Pending Orders:** `0`
- **Tradable Instruments Verified:** `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `USDCAD` (`contract_size=100000`, `tick_size=1e-5` / `1e-3`), `XAUUSD` (`contract_size=100`, `tick_size=0.001`), `BTCUSD` & `ETHUSD` (`contract_size=1.0`, `tick_size=0.01`).

## 2. Strategy Readiness Classification
- **`LT_STRUCTURE_EURUSD` (Forex Long-Term):** **READY** (OOS_30 PF `2.29`, `+$115.96`), pending controlled reload of PM2 `#16` to load Stage 4 `shared_risk_manager.py`.
- **`LT_STRUCTURE_GBPUSD` (Forex Long-Term):** **CONDITIONAL** (OOS_30 PF `2.18`, `+$85.73`; Phase 9 T2 drawdown `-$96.09`).
- **Track 1 Scalping:** **BLOCKED** (permanently retired/forbidden in `SharedCentralRiskManager.preflight_check()`).
- **Crypto Long-Term & Crypto Scalping (`BTCUSD`, `ETHUSD`):** **BLOCKED** (Phase 7/8 OOS backtests showed negative net expectancy across all 4 variants: PF `0.25`–`0.96`; no validated live crypto strategy).

## 3. Requirements for Separately Approved Demo Activation
1. Controlled reload of PM2 `#16` (`pm2 restart 16`) so the live process loads Stage 4 `shared_risk_manager.py`.
2. Clarify `max_concurrent_positions` in `experiment_lock.json` relative to the `3` existing legacy positions (`EURNZD`, `AUDUSD`, `XAUUSD`) vs `1` new position.
3. Explicit operator authorization for the revised `experiment_lock.json`.
