# BITDEX — Next Milestone: Live Market Data & Multi-Engine Integration Audit

## Capability Classifications
1. **backtesting.py 0.6.5 (`/opt/bitdex-research-v2/engines/backtesting-py/.venv`):** `VERIFIED WORKING` (EURUSD historical test: 85 trades, $462.04 net profit).
2. **VectorBT 1.2.1 (`/opt/bitdex-research-v2/engines/vectorbt/.venv`):** `VERIFIED WORKING` (10-combo EMA sweep).
3. **Common Schema, Cost Model, Dataset Manager, `bitdex_research.db`:** `VERIFIED WORKING` (`validate_result_schema()`, `validate_cost_assumptions()`, `inspect_dataset()`).
4. **Market Intelligence (`core/market_intelligence/engine.py:analyze_market`):** `IMPLEMENTED BUT NOT CONNECTED` (tested with mocked L1 fixtures; not yet wired to live Exness/crypto feeds).
5. **Central Consensus Engine (`core/consensus/engine.py:evaluate_consensus`):** `VERIFIED WORKING` (deterministic BUY/SELL/HOLD, stale rejection, disagreement -> HOLD, duplicate proposal rejection, `execution_authorized: false`).
6. **Jeb & Tauric Research Adapters (`integrations/jeb/reviewer.py`, `integrations/tauric/reporter.py`):** `MOCKED / TEST ONLY` (tested with structured payloads; not yet wired to live `jev_client.py` / `tauric_engine.py` LLM calls or Research API).
7. **Freqtrade (`/opt/bitdex-research-v2/engines/freqtrade/`):** `MISSING` (not yet installed).
8. **Unified Trading Intelligence Dashboard:** `MISSING` (not yet added to `tauric-dashboard-staging`).

## Safety
- PM2 `#11` and `#16`, `experiment_lock.json`, `tauric_saas.db`, and `run_operator_experiment_runner.py` remain untouched.
