# BITDEX — HFT Dashboard Simplification & Next Actions Plan

**Date:** November 5, 2026  
**Scope:** Actionable implementation roadmap directly addressing user instructions.  

---

## 1. User Directives Summary

1. **Remove the Simulation Panel Completely:**
   - Eliminate the Quantitative HFT Simulation panel (synthetic 100-candle XAUUSDm backtest).
   - Clean up the UI so operators do not get confused by simulated -$2.79 PnL and 1.71 profit factors.
2. **Simplified 3-Stage HFT Layout (Binance-Style):**
   - **Top:** Pair Selection (Clean selector for active trading pairs).
   - **Sidebar / Middle:** Pre-Trade Checklist & Risk Bars (Instant feedback on what is active, what is wrong, what is risky).
   - **Bottom:** Open Trades & Positions Monitor (Similar to Binance: Open Orders, PnL, Symbol, Direction, Entry Price, Mark Price, Liquidation, and Duplicate-Pair Warning).
   - **Duplicate Pair Guard:** If an order or position is already active on a selected pair, show immediate warning that the pair already has an open trade.
3. **Exness API Connection Simplification:**
   - Replace MT5 desktop complexity with a clean, single **API Connection Tab**.
   - User inputs:
     - **Environment:** `DEMO` or `REAL` toggle.
     - **Account ID:** (Account login number).
     - **API Key:** (Trader API Key).
     - **API Secret:** (Trader API Secret / Private Key).
   - **Test Connection Button:** Tests the connection and fetches the account balance/equity directly onto the screen.

---

## 2. Immediate Pre-Implementation Action Checklist

- [ ] Apply cleanup to `InstitutionalTradingDashboard.tsx` to remove the simulation panel.
- [ ] Add the Binance-style Open Positions / Orders table at the bottom of the HFT view.
- [ ] Implement duplicate-pair detection banner in the pre-trade checklist.
- [ ] Simplify Exchange Connections tab to provide the streamlined Account ID + API Key + API Secret form with instant balance test.
- [ ] Maintain all safety locks (`live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True`).
