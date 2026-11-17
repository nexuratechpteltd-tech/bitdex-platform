# Stage 8 — Jeb & Tauric Integration Plan (`PARTIAL` — Design Verified, Live LLM Wiring Pending Approval)
- **Jeb (`jev_client.py`):** Receives `stage8_corrected_backtesting.json` + `stage8_vectorbt_results.json` and returns structured JSON critique (sample size, negative OOS PF, cost sensitivity).
- **Tauric (`tauric_engine.py`):** Consumes engine results + Jeb critique to produce one consolidated research report without fabricating metrics or executing orders.
