# BITDEX — HFT Strategy Validation & Demo Execution Safety Report (Phases 7 & 8)

**Test Suites:**
- `backend/test_phase5_quantitative_validation.py`
- `backend/test_phase6_launch_audit.py`
**Date:** November 5, 2026  
**Status:** **12 PASSED (Strategy Sim) | FAIL-CLOSED SAFETY ENFORCED**

---

## 1. Strategy Quantitative Simulation (Phase 7)

A quantitative validation harness evaluated strategy logic against a continuous synthetic dataset of 1,440 1-minute bars:

| Test Item | Parameter / Condition | Outcome | Status |
| :--- | :--- | :--- | :--- |
| **Historical Data Integrity** | Monotonic timestamps, High $\ge$ Max, Low $\le$ Min | 1,440 continuous bars validated | **PASSED** |
| **In-Sample Backtest** | Micro-Scalping strategy | 72.7% win rate (+$99.10 gross) | **PASSED (Sim)** |
| **Out-of-Sample Backtest** | Walk-forward validation window | 64.0% win rate (+$17.70 gross) | **PASSED (Sim)** |
| **Walk-Forward Robustness** | 3 consecutive sliding windows | 3/3 positive; Profit Factor: 1.87R | **PASSED (Sim)** |
| **Regime Adaptability** | Trending vs Ranging vs High Volatility | Volatility expansion clamped by risk circuit breaker | **PASSED (Sim)** |
| **Monte Carlo Simulation** | 1,000 synthetic geometric Brownian paths | 95% VaR Max DD: 18.7%, Ruin Prob: 0.00% | **PASSED (Sim)** |
| **Intrabar Ambiguity** | Pessimistic SL execution | Stop-loss takes priority on intrabar conflict | **PASSED** |
| **Protective Stop Bounds** | Dynamic SL clamp $[0.2\%, 5.0\%]$ | Mandatory protective stop required on every order | **PASSED** |
| **Anti-Martingale Rule** | Disallow position sizing increase on loss | Adding to losing positions strictly rejected | **PASSED** |
| **Exposure Boundaries** | Capital risk gates | Max $5,000 total exposure, $250 daily loss cap | **PASSED** |

> **IMPORTANT DISCLAIMER:** Backtest and simulation results are theoretical and model-based. They do **not** represent live broker execution or guarantee future profitability.

---

## 2. Demo & Real Execution Safety Hard-Locks (Phase 8)

All global safety locks remain actively enforced across staging:
```python
live_trading_locked = True
emergency_lock_active = True
read_only_mode = True
```

### Safety Hardening Applied This Session
1. **Real Account Guard:**
   Orders submitted to `/hft/exness/order` or `/hft/exness/trade/execute` for `REAL` accounts are intercepted before any network transmission and return `status: "BLOCKED_BY_SAFETY_LOCK"`, `barrier: "LIVE_TRADING_LOCKED"`.
2. **Demo Account Guard (Elimination of Fabricated Fills):**
   Previously, the Demo trade route simulated order fills with static hardcoded prices (e.g. 2745.50 / 78500.0) even with safety locks active.  
   **Correction:** Patched `execute_customer_trade` in `backend/app/routes/exness_hft.py`. When `read_only_mode` or `live_trading_locked` is active, Demo order submissions return `status: "BLOCKED_BY_SAFETY_LOCK"`, `barrier: "READ_ONLY_MODE"`. Zero orders and zero fake fills are generated.
