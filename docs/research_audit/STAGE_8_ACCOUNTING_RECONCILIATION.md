# Stage 8 — Accounting Reconciliation (`VERIFIED`)
- **Stage 7 Bug Found:** `strategy.py:66` used `cash=1000000`, while `strategy.py:76` subtracted `10000.0` instead of `1000000.0` (inflating `net_profit_usd` by `+$990,000.00`).
- **Corrected Results (`stage8_corrected_backtesting.json`, `init_cash=$1,000,000.00`, `0.06%` commission):**
  - `BTCUSDT` `IS_70`: `5` trades, `-$24,738.26`, WR `20.0%`, PF `0.06`, DD `-2.47%`
  - `BTCUSDT` `OOS_30`: `4` trades, `-$10,513.00`, WR `25.0%`, PF `0.22`, DD `-1.35%`
  - `ETHUSDT` `IS_70`: `3` trades, `-$12,021.30`, WR `33.33%`, PF `0.15`, DD `-1.68%`
  - `ETHUSDT` `OOS_30`: `1` trade, `-$4,979.66`, WR `0.0%`, PF `0.00`, DD `-0.50%`
