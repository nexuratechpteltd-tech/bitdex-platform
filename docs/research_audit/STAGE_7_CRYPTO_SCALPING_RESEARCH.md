# BITDEX — Stage 7: New Crypto Scalping Engine Research Report

## 1. Strategy Rules & Source
- **Source File:** `/opt/bitdex-research-v2/engines/crypto_scalping/strategy.py` (`CryptoMtfScalp`)
- **Dataset:** Binance Public M5 klines (`1,000` bars: `2026-11-12 09:05:00Z` to `2026-11-15 20:20:00Z`), split 70% In-Sample / 30% Out-of-Sample, `0.06%` per-side commission (`0.12%` round-trip).
- **Entry:** `EMA20 > EMA50 > EMA200` (BUY) or `<` (SELL), `RSI(14)` momentum (`52-68` BUY / `32-48` SELL), pullback to `EMA20`, volume `> 0.8x SMA(20)`, `1.5x ATR(14)` SL, `2.5x ATR(14)` TP.

## 2. Results (Before Promotion — Honest Research Output)
- **BTCUSDT:**
  - `IS_70`: `5` trades | WR `20.0%` | PF `0.06` | Expectancy `-0.524%` | Max DD `-2.47%`
  - `OOS_30`: `4` trades | WR `25.0%` | PF `0.22` | Expectancy `-0.269%` | Max DD `-1.35%`
- **ETHUSDT:**
  - `IS_70`: `3` trades | WR `33.33%` | PF `0.18` | Expectancy `-0.384%` | Max DD `-1.68%`
  - `OOS_30`: `1` trade | WR `0.0%` | PF `0.00` | Expectancy `-0.499%` | Max DD `-0.50%`

## 3. Qualification Decision: **DOES NOT QUALIFY FOR DEMO VALIDATION (`BLOCKED`)**
- Negative expectancy and `PF < 1.0` after costs in both IS and OOS, plus insufficient OOS sample size.
- No broker orders placed; `experiment_lock.json` and PM2 `#11`/`#16` untouched.
