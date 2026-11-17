# BITDEX — Complete GitHub Repository Utilisation Forensic Audit

## Scorecard
- `nexuratechpteltd-tech/bitdex-platform`: **VERIFIED EXECUTED** (`/opt/tauric-platform-staging`, commit `e0c4e78`)
- `TauricResearch/TradingAgents`: **VERIFIED INTEGRATED BUT NOT EXECUTED IN STAGE 7** (vendored at `/opt/tauric-platform-staging/backend/tradingagents`)
- `kernc/backtesting.py` (`0.6.5`): **VERIFIED EXECUTED** (used in Stage 2 and Stage 7 `strategy.py:66-67`)
- `polakowo/vectorbt` (`1.2.1`): **VERIFIED INTEGRATED BUT NOT EXECUTED IN STAGE 7** (used in Stage 2 sweep only)
- `freqtrade/freqtrade`: **NOT INSTALLED**
- `QuantConnect/Lean`: **NOT INSTALLED**
- `nautechsystems/nautilus_trader`: **NOT INSTALLED**
- `jakeschincariol/day-trader-skill`: **RESEARCHED ONLY**

See `STAGE_7_CODE_PROVENANCE_TRACE.md` and `GITHUB_REPOSITORY_EXECUTION_MATRIX.csv` for full line-by-line evidence.
