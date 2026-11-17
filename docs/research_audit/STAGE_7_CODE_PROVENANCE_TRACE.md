# Stage 7 Code Provenance Trace (`/opt/bitdex-research-v2/engines/crypto_scalping/strategy.py`)

1. **Author & Provenance:** `CryptoMtfScalp` (lines `24–60`) is 100% custom BITDEX research code; not derived from any external GitHub strategy repo.
2. **Indicators:** `EMA20/50/200` (`ewm`, lines `33–35`), `RSI14` (`compute_rsi`, lines `17–22`, `36`), `ATR14` (`rolling(14).mean()`, lines `38–39`) are computed via `pandas` + `numpy`.
3. **Market Data:** Binance Public REST `https://api.binance.com/api/v3/klines` (line `8`, HTTP market-data API, not a GitHub repo). `1,000` M5 bars per symbol (`700` `IS_70`, `300` `OOS_30`).
4. **Backtest Engine:** `backtesting.py 0.6.5` (`Backtest`, `Strategy`, lines `4–5`, `66–67`) executes the backtest, handles SL/TP, deducts `0.06%` per-side commission, and computes Win Rate, Profit Factor, Expectancy, and Max Drawdown.
5. **Cross-Check & AI:** `VectorBT`, `Freqtrade`, `Jeb` (`jev_client.py`), and `Tauric` (`tauric_engine.py`) were **not** invoked during Stage 7.
6. **Bug Note:** Line `76` computes `st["Equity Final [$]"] - 10000.0` despite `cash=1000000` on line `66` (percentage metrics `win_rate_pct`, `profit_factor`, `max_dd_pct`, `expectancy_pct` are unaffected and accurate).
