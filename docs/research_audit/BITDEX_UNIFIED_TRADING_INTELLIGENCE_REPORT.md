# BITDEX — Unified Multi-Engine Trading Intelligence Report

## 1. Architecture & Data Flow
`Market Intelligence Engine` -> `UnifiedSignal` (multiple independent engines) -> `Central Consensus Engine` (`BUY`/`SELL`/`HOLD`) -> `One Trade Proposal` (`execution_authorized: false`) -> `Jeb Review` -> `Tauric Consolidated Report`.

## 2. Implemented Modules (`/opt/bitdex-research-v2/`)
- `core/common_schema/unified_signal.py`: `UnifiedSignal` dataclass
- `core/market_intelligence/engine.py`: `analyze_market()` (L1 Bid/Ask, spread, ATR, regime, freshness; explicitly marks L2 unavailable)
- `core/consensus/engine.py`: `evaluate_consensus()` (rejects stale data, detects engine disagreement -> `HOLD`, enforces minimum independent engines, deduplicates proposals)
- `integrations/jeb/reviewer.py`: `review_proposal()`
- `integrations/tauric/reporter.py`: `build_consolidated_report()`

## 3. Test Evidence (`unified_intelligence_tests.json`)
- **EURUSD Multi-Engine Consensus:** `BUY` (`PROP-...`, `execution_authorized: false`)
- **Jeb Review:** `PASS`
- **Tauric Report:** `BUY`
- **Duplicate Proposal:** `DUPLICATE_PROPOSAL_REJECTED` (`HOLD`)
- **Engine Disagreement:** `ENGINE_DISAGREEMENT` (`HOLD`)
- **Stale Market Data:** `STALE_MARKET_DATA` (`HOLD`)

## 4. Safety & Remaining Blockers
- PM2 `#11`, PM2 `#16`, `experiment_lock.json`, and `tauric_saas.db` remain untouched.
- No broker orders were placed.
- **Remaining Blockers:** Separate operator approval is required before remediating `run_operator_experiment_runner.py` or enabling any live/demo execution from the unified intelligence layer.
