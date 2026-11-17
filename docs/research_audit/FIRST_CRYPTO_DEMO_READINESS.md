# BITDEX — Crypto Demo Trade: Live Analysis & Readiness

- **Timestamp (UTC):** `2026-11-15T20:20:30Z`
- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Experiment Lock:** `authorized = False` | **Open Positions:** `3`
- **Outcome:** **BLOCKED / HOLD — NO ORDER PLACED**

## 1. Live Exness DEMO Market Analysis
- **BTCUSD (`2026-11-15T20:00:00+00:00`):** Bid `64766.07`, Ask `64767.02`, Spread `0.95`, H1 Trend `BEARISH` (`EMA50=66046.95`, `EMA200=69777.1`), `ATR14=615.35`, est. `0.01` lot risk at `1.5x ATR`: `$9.23`
- **ETHUSD (`2026-11-15T20:00:00+00:00`):** Bid `1819.76`, Ask `1819.89`, Spread `0.13`, H1 Trend `BEARISH` (`EMA50=1849.36`, `EMA200=1967.04`), `ATR14=21.13`, est. `0.01` lot risk at `1.5x ATR`: `$0.32`

## 2. Strategy Validation & Blocking Gates
1. **No Verified Live Crypto Strategy:** Phase 7/8 OOS backtests for `CRYPTO_LT_EMA_*`, `CRYPTO_SCALP_*`, `LT_STRUCTURE_BTCUSD`, and `LT_STRUCTURE_ETHUSD` all failed promotion (PF `0.25`–`0.96`), and Track 1 Scalping is permanently retired.
2. **No Active Crypto Authorization:** `experiment_lock.json` is `authorized: false` (`LT_STRUCTURE_EURUSD` only when authorized).
3. **Consensus Decision:** `HOLD` for both `BTCUSD` and `ETHUSD`. No broker order was placed.
