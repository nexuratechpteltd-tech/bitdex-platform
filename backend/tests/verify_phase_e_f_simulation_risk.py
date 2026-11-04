"""
BITDEX Phase E & F Automated Verification Test Suite
Tests:
1. Quantitative Market Regime Classification (ADX, ATR, BB Width)
2. Cost Modeling & Friction Simulation (spread, slippage, swap)
3. Paired HFT Simulation Engine (Honest mark-to-market accounting, is_simulated=True)
4. ExnessRiskGuard Quantitative Clamps & Circuit Breakers (11 risk barriers)
5. Route Endpoints (/simulation/run, /risk/limits, /risk/check)
"""

import sys
import os
import time
import math
from typing import Dict, List, Any

# Ensure backend root is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.exness.simulation_engine import (
    HFTPairedSimulationEngine,
    QuantitativeRegimeClassifier,
    MarketRegime,
    CostModelConfig,
    RegimeAnalysis,
)
from app.services.exness.risk_guard import ExnessRiskGuard, RiskLimits


def generate_synthetic_candles(
    count: int = 100,
    start_price: float = 2000.0,
    regime: str = "RANGE",
) -> List[Dict[str, Any]]:
    candles = []
    curr = start_price

    for i in range(count):
        t = 1700000000 + i * 60
        if regime == "RANGE":
            # Small oscillating sine wave
            change = math.sin(i / 3.0) * 0.5
            curr = start_price + change
            high = curr + 0.3
            low = curr - 0.3
            close = curr + 0.1
        elif regime == "TRENDING_BULL":
            # Strong upward trend
            curr += 1.5
            high = curr + 0.8
            low = curr - 0.2
            close = curr + 0.6
        elif regime == "EXTREME_VOLATILITY":
            # Giant swings
            curr += (50.0 if i % 2 == 0 else -48.0)
            high = curr + 30.0
            low = curr - 30.0
            close = curr + 5.0
        else: # TRANSITION
            curr += (0.8 if i % 2 == 0 else -0.3)
            high = curr + 0.5
            low = curr - 0.5
            close = curr

        candles.append({
            "time": t,
            "open": round(curr, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": 100 + i,
        })
    return candles


def test_regime_classification():
    print("\n--- [TEST 1] Quantitative Market Regime Classification ---")

    # 1. Range test
    range_candles = generate_synthetic_candles(50, 2000.0, "RANGE")
    res_range = QuantitativeRegimeClassifier.classify(range_candles)
    print(f"Range Regime: {res_range.regime.value}, ADX: {res_range.adx}, ATR: {res_range.atr}, BB%: {res_range.bb_width_pct}")
    assert res_range.regime in (MarketRegime.RANGE, MarketRegime.TRANSITION)
    print("✓ PASSED: Range condition properly evaluated.")

    # 2. Bull Trend test
    bull_candles = generate_synthetic_candles(50, 2000.0, "TRENDING_BULL")
    res_bull = QuantitativeRegimeClassifier.classify(bull_candles)
    print(f"Bull Trend Regime: {res_bull.regime.value}, ADX: {res_bull.adx}, Safe for Hedging: {res_bull.is_safe_for_hedging}")
    assert res_bull.regime == MarketRegime.TRENDING_BULL
    assert res_bull.is_safe_for_hedging is False
    print("✓ PASSED: Trending market classified with hedging disabled (asymmetric drift prevention).")

    # 3. Extreme Volatility test
    vol_candles = generate_synthetic_candles(50, 2000.0, "EXTREME_VOLATILITY")
    res_vol = QuantitativeRegimeClassifier.classify(vol_candles)
    print(f"Volatile Regime: {res_vol.regime.value}, ATR: {res_vol.atr}, Safe for Hedging: {res_vol.is_safe_for_hedging}")
    assert res_vol.regime == MarketRegime.EXTREME_VOLATILITY
    assert res_vol.is_safe_for_hedging is False
    print("✓ PASSED: Extreme volatility detected and unhedged execution prohibited.")


def test_paired_simulation_engine():
    print("\n--- [TEST 2] Paired HFT Quantitative Simulation Engine ---")
    candles = generate_synthetic_candles(100, 2000.0, "RANGE")
    engine = HFTPairedSimulationEngine(CostModelConfig(spread_points=16.0, slippage_base_pips=0.5))

    res = engine.run_simulation(
        symbol="XAUUSDm",
        candles=candles,
        volume_per_leg=0.01,
        take_profit_points=30.0,
        stop_loss_points=60.0,
        max_hold_bars=15,
    )

    print(f"Simulation Status: {res['status']}")
    print(f"Is Simulated: {res['is_simulated']}")
    print(f"Simulated Cycles: {res['simulated_cycles']}, Win Rate: {res['win_rate_pct']}%")
    print(f"Net PnL: ${res['net_simulated_pnl_usd']}, Max Drawdown: ${res['max_drawdown_usd']} ({res['max_drawdown_pct']}%)")
    print(f"Friction Costs: {res['cost_breakdown']}")

    assert res["status"] == "COMPLETED"
    assert res["is_simulated"] is True
    assert "SIMULATED QUANTITATIVE RESEARCH ONLY" in res["simulation_disclaimer"]
    assert res["cost_breakdown"]["total_friction_usd"] > 0
    assert res["simulated_cycles"] > 0
    print("✓ PASSED: Simulation completed with honest friction accounting and simulated labeling.")


def test_risk_guard_limits_and_breakers():
    print("\n--- [TEST 3] ExnessRiskGuard Quantitative Clamps & Circuit Breakers ---")
    guard = ExnessRiskGuard(RiskLimits(
        max_open_positions=3,
        max_volume_per_order=0.05,
        max_volume_per_symbol=0.20,
        max_aggregate_exposure_usd=30000.0,
        max_daily_loss_usd=200.0,
        max_basket_loss_usd=100.0,
        max_margin_utilization_pct=30.0,
        max_stale_quote_ms=3000,
        emergency_lock_active=True,
    ))

    # 1. Emergency lock check
    safe, msg = guard.check_emergency_lock(live_trading_locked=True)
    assert safe is True
    print(f"✓ PASSED: Emergency lock check: {msg}")

    # 2. Pre-trade rejection when emergency lock is active
    positions = []
    account = {"equity": 5000.0, "used_margin": 100.0, "free_margin": 4900.0, "live_trading_locked": True}
    safe, msg = guard.validate_pre_order("XAUUSDm", 0.01, 2000.0, positions, account)
    assert safe is False
    assert "PRE_TRADE_BLOCKED" in msg
    print(f"✓ PASSED: Pre-order blocked under emergency lock: {msg}")

    # Unlock for unit testing individual quantitative boundaries
    guard.limits.emergency_lock_active = False
    account["live_trading_locked"] = False

    # 3. Single order volume limit
    safe, msg = guard.validate_pre_order("XAUUSDm", 0.10, 2000.0, positions, account)
    assert safe is False
    assert "VOLUME_LIMIT_EXCEEDED" in msg
    print(f"✓ PASSED: Single order volume limit exceeded rejected: {msg}")

    # 4. Max open positions limit
    open_3 = [
        {"symbol": "XAUUSDm", "volume": 0.01, "price_open": 2000.0, "sl": 1990.0},
        {"symbol": "EURUSDm", "volume": 0.01, "price_open": 1.08, "sl": 1.07},
        {"symbol": "GBPUSDm", "volume": 0.01, "price_open": 1.25, "sl": 1.24},
    ]
    safe, msg = guard.validate_pre_order("XAUUSDm", 0.01, 2000.0, open_3, account)
    assert safe is False
    assert "POSITION_LIMIT_EXCEEDED" in msg
    print(f"✓ PASSED: Max open positions clamp triggered: {msg}")

    # 5. Daily loss circuit breaker
    safe, msg = guard.validate_pre_order("XAUUSDm", 0.01, 2000.0, [], account, daily_realized_loss=-250.0)
    assert safe is False
    assert "CIRCUIT_BREAKER_TRIGGERED" in msg
    print(f"✓ PASSED: Daily loss circuit breaker triggered: {msg}")

    # 6. Stale quote check
    old_time_ms = int((time.time() - 10) * 1000) # 10 seconds old
    fresh, msg = guard.validate_quote_freshness(old_time_ms)
    assert fresh is False
    assert "STALE_DATA_REJECTED" in msg
    print(f"✓ PASSED: Stale quote (10s old) rejected: {msg}")

    # 7. Missing stop-loss detection
    unprotected_positions = [
        {"ticket": 101, "symbol": "XAUUSDm", "volume": 0.01, "sl": 0.0, "side": "BUY", "price_open": 2000.0},
        {"ticket": 102, "symbol": "EURUSDm", "volume": 0.01, "sl": 1.075, "side": "BUY", "price_open": 1.08},
    ]
    missing = guard.detect_missing_stop_loss(unprotected_positions)
    assert len(missing) == 1
    assert missing[0]["ticket"] == "101"
    print(f"✓ PASSED: Missing broker-side stop-loss flagged: Ticket {missing[0]['ticket']}")

    # 8. Basket floating loss check
    losing_positions = [
        {"symbol": "XAUUSDm", "profit": -70.0},
        {"symbol": "EURUSDm", "profit": -45.0},
    ] # Total -115.0 exceeds -100.0
    basket_safe, total_loss, msg = guard.evaluate_basket_drawdown(losing_positions)
    assert basket_safe is False
    assert total_loss == -115.0
    assert "BASKET_LOSS_BREACH" in msg
    print(f"✓ PASSED: Basket drawdown breach detected: ${abs(total_loss):.2f}")


def test_fastapi_endpoints():
    print("\n--- [TEST 4] FastAPI Simulation & Risk Endpoints ---")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM, jwt

    # Generate test auth token for active user
    token = jwt.encode({"sub": "USR-328E147ACA"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. GET /api/v1/hft/exness/risk/limits
    r = client.get("/api/v1/hft/exness/risk/limits", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "SUCCESS"
    assert d["limits"]["live_trading_locked"] is True
    print(f"✓ PASSED: /risk/limits endpoint: live_trading_locked={d['limits']['live_trading_locked']}")

    # 2. POST /api/v1/hft/exness/simulation/run
    r = client.post("/api/v1/hft/exness/simulation/run", json={
        "symbol": "XAUUSDm",
        "volume_per_leg": 0.01,
        "take_profit_points": 30.0,
        "stop_loss_points": 60.0,
        "candle_count": 50,
    }, headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "SUCCESS"
    assert d["simulation"]["is_simulated"] is True
    print(f"✓ PASSED: /simulation/run endpoint: is_simulated={d['simulation']['is_simulated']}, cycles={d['simulation']['simulated_cycles']}")

    # 3. POST /api/v1/hft/exness/risk/check
    r = client.post("/api/v1/hft/exness/risk/check", json={
        "symbol": "XAUUSDm",
        "volume": 0.01,
        "price": 2000.0,
        "order_type": "BUY",
    }, headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "SUCCESS"
    assert d["risk_approved"] is False  # Must fail closed because live_trading_locked=True
    assert "PRE_TRADE_BLOCKED" in d["reason"]
    print(f"✓ PASSED: /risk/check endpoint properly enforced fail-closed safety gate: {d['reason']}")


if __name__ == "__main__":
    test_regime_classification()
    test_paired_simulation_engine()
    test_risk_guard_limits_and_breakers()
    test_fastapi_endpoints()
    print("\n=======================================================")
    print("ALL PHASE E & F SIMULATION AND RISK GUARD TESTS PASSED!")
    print("=======================================================")
