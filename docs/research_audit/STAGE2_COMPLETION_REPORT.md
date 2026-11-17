# BITDEX — Stage 2 Completion Report

## 1. Isolated Engine Installations
- `backtesting.py 0.6.5`: `/opt/bitdex-research-v2/engines/backtesting-py/.venv`
- `VectorBT 1.2.1` (Apache-2.0): `/opt/bitdex-research-v2/engines/vectorbt/.venv`

## 2. Common Research Foundation (`/opt/bitdex-research-v2/core/`)
- `common_schema/schema.py`: `validate_result_schema()`
- `cost_model/model.py`: `validate_cost_assumptions()` (rejects missing spread/commission/slippage/specs; never defaults to 0)
- `dataset_manager/manager.py`: `inspect_dataset()` (SHA256 hashing, duplicate/null checks)
- `database/research_store/bitdex_research.db`: dedicated SQLite store (`research_results` table)

## 3. Validation Test Results
- **backtesting.py EURUSD Test (`RES-BT-EURUSD-001`):** `85` trades, `net_profit=$462.04`, `schema_ok=True`, `cost_ok=True`, `missing_cost_rejected=True`, `db_rows=1`
- **VectorBT EMA Sweep:** `10` parameter combinations tested, `best_return_pct=0.12%`

## 4. Safety Verification
- `pre_stage2_safety.json` == `post_stage2_safety.json` (`SAFETY_UNCHANGED_OK`)
- PM2 `#11` and `#16`, `experiment_lock.json`, `tauric_saas.db`, and `run_operator_experiment_runner.py` remain completely untouched.
