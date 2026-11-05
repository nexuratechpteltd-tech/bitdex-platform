# BITDEX — PHASE 13: REMOVAL OF SYNTHETIC SIMULATION UI REPORT

**Timestamp:** 2026-11-05T00:16:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Target File:** `dashboard/src/components/InstitutionalTradingDashboard.tsx`  

---

## 1. Objective & Scope

Under Phase B of the Phase 13 specification, all synthetic simulation components, fabricated historical candles, mock profit metrics, and misleading quantitative widgets were permanently removed from the customer-facing interface.

---

## 2. Inventory of Removed Components

The following customer-facing components previously located in `Section 6` (lines 1455 to 1894) of `InstitutionalTradingDashboard.tsx` were completely removed:

1. **Synthetic 100-Candle Generator & Controls**:
   - `simSymbol` (hardcoded default `XAUUSDm`)
   - `simVolume` (`0.01` lots)
   - `simTpPoints` (`30.0` points)
   - `simSlPoints` (`60.0` points)
   - `simHoldBars` (`15` bars)
   - `simCandleCount` (`100` bars)
   - Simulated regime selector (`RANGE: SCALP VIABLE` / `TRENDING: DRIFT RISK`)
2. **Fabricated Performance Metric Cards**:
   - Simulated Win Rate (`win_rate_pct` with fake `W / L` cycle counters)
   - Simulated Profit Factor (`profit_factor` displaying hardcoded or synthetic `1.71`)
   - Simulated Drawdown (`max_drawdown_usd` / `max_drawdown_pct`)
   - Simulated Equity progression (`final_equity_usd`, `peak_equity_usd`)
   - Synthetic Cost Breakdown (`total_spread_cost_usd`, `total_slippage_cost_usd`, `total_swap_cost_usd`, `total_friction_usd`)
   - Residual Directional Exposure widget (`typical_unhedged_delta_lots`)
3. **Synthetic Handlers and State in Frontend**:
   - `simResult`, `setSimResult` (`ExnessSimulationResult` interface)
   - `simLoading`, `setSimLoading`
   - `runQuantitativeSimulation` callback and `initialSimFired` automatic background invocation
   - Pre-order mock check button (`runRiskCheck`)

---

## 3. Preservation of Underlying Research Libraries

While removed from the customer terminal, the mathematical algorithms in `backend/app/services/exness/` remain intact on the server for administrative quantitative research and backtesting:
- `backend/app/services/exness/simulation_engine.py` (Preserved)
- `backend/app/services/exness/risk_guard.py` (Preserved)
- `backend/app/routes/exness_hft.py` administrative endpoints (Preserved)

No backend analysis services were broken or deleted.

---

## 4. Verification

1. **Codebase Grep**:
   - Grep verification across `InstitutionalTradingDashboard.tsx` confirmed that zero references to `runQuantitativeSimulation`, `simResult`, `simVolume`, or `simTpPoints` remain in customer rendering paths.
2. **TypeScript Compilation**:
   - `npx tsc --noEmit` verified that no broken references or orphaned props exist.
3. **Customer Experience**:
   - The customer dashboard now renders only authoritative broker-backed telemetry, replacing speculative simulation with real portfolio tracking.
