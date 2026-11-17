# Stage 8 — VectorBT Parity Report (`VERIFIED`)
- **Shared Datasets:** `/opt/bitdex-research-v2/datasets/BTCUSDT_5m_stage8.csv` and `ETHUSDT_5m_stage8.csv` (`1,000` bars each, `0.06%` fees).
- **VectorBT 1.2.1 Results (`stage8_vectorbt_results.json`):**
  - `BTCUSDT` `OOS_30`: `2` long trades, `-0.378%` return, `-0.38%` max DD
  - `ETHUSDT` `OOS_30`: `1` long trade, `-0.304%` return, `-0.30%` max DD
- **Parity Explanation:** `backtesting.py` includes SHORT entries and intra-bar ATR SL/TP exits, whereas the VectorBT signal run evaluated LONG-only signal exits; both engines independently confirm negative OOS performance.
