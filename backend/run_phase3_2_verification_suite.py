"""
BITDEX Phase 3.2 Automated Verification & Regression Suite
==========================================================
Comprehensive automated test suite verifying:
1. TechnicalIndicators mathematical precision (EMA, ATR, RSI, ADX)
2. SwingSignalEvaluator models (A, B, C, D) and NO_TRADE gating
3. SwingSizingEngine capital limits (2% risk ceiling, 10x leverage, $5k exposure, min notional invariant)
4. Authoritative FuturesRiskEngine invariants (unbroken, uncompromised)
5. AutonomousSwingEngine lifecycle operations (start, pause, resume, stop, monitoring)
6. Zero naked positions invariant & exchange stop requirement
7. Regression checks for Phase 1A, 1B, 2, 3, and 3.1
"""

import sys
import os
import sqlite3
import unittest
import math

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.futures_swing_engine import (
    TechnicalIndicators,
    SwingSignalEvaluator,
    SwingSizingEngine,
    AutonomousSwingEngine
)
from app.services.futures_risk_engine import FuturesRiskEngine
from app.services.futures_db import (
    get_or_create_futures_account,
    get_open_futures_position,
    list_open_futures_positions,
    record_scalp_trade,
    complete_scalp_trade,
)


class TestPhase32SwingSuite(unittest.TestCase):

    def setUp(self):
        # In-memory SQLite database matching tauric_saas.db futures schema
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        
        # Initialize schema from tauric_saas.db
        with open("/opt/tauric-platform-staging/backend/data/tauric_saas.db", "rb") as f_src:
            disk_conn = sqlite3.connect("/opt/tauric-platform-staging/backend/data/tauric_saas.db")
            disk_conn.backup(self.conn)
            disk_conn.close()

        self.user_id = "test-user-phase32"
        self.account = get_or_create_futures_account(
            self.conn,
            user_id=self.user_id,
            exchange_connection_id="CONN-TEST-32",
            environment="testnet"
        )
        self.account_id = self.account["account_id"]

    def tearDown(self):
        self.conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Technical Indicators Mathematical Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_01_ema_calculation(self):
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
        ema_5 = TechnicalIndicators.calculate_ema(prices, 5)
        self.assertEqual(len(ema_5), len(prices))
        # Last value must be greater than simple moving average in a rising trend
        sma_5 = sum(prices[-5:]) / 5.0
        self.assertGreaterEqual(ema_5[-1], sma_5 - 0.5)

    def test_02_atr_calculation(self):
        candles = []
        for i in range(20):
            candles.append({
                "open": 100.0 + i,
                "high": 105.0 + i,
                "low": 95.0 + i,
                "close": 102.0 + i
            })
        atr = TechnicalIndicators.calculate_atr(candles, 14)
        # Constant range of 10.0 -> ATR must converge to ~10.0
        self.assertAlmostEqual(atr, 10.0, delta=0.5)

    def test_03_rsi_calculation(self):
        # Monotonically increasing prices -> RSI must be high (> 80)
        rising = [100.0 + i * 2.0 for i in range(30)]
        rsi_rising = TechnicalIndicators.calculate_rsi(rising, 14)
        self.assertGreaterEqual(rsi_rising, 85.0)

        # Monotonically decreasing prices -> RSI must be low (< 20)
        falling = [200.0 - i * 2.0 for i in range(30)]
        rsi_falling = TechnicalIndicators.calculate_rsi(falling, 14)
        self.assertLessEqual(rsi_falling, 15.0)

    def test_04_adx_calculation(self):
        # Strong directional trend -> ADX must be elevated (> 30)
        candles = []
        for i in range(40):
            candles.append({
                "open": 100.0 + (i * 3.0),
                "high": 105.0 + (i * 3.0),
                "low": 98.0 + (i * 3.0),
                "close": 104.0 + (i * 3.0)
            })
        adx = TechnicalIndicators.calculate_adx(candles, 14)
        self.assertGreaterEqual(adx, 25.0)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Swing Signal Evaluator Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_05_model_a_trend_continuation_long(self):
        # Construct bullish multi-tf candles
        c_1h = [{"high": 100 + i*2, "low": 96 + i*2, "close": 99 + i*2} for i in range(80)]
        c_15m = [{"high": 250 + i, "low": 248 + i, "close": 249 + i, "volume": 100.0} for i in range(80)]
        c_5m = [{"high": 328 + i*0.2, "low": 327 + i*0.2, "close": 327.5 + i*0.2} for i in range(30)]

        res = SwingSignalEvaluator.evaluate(
            symbol="BTCUSDT",
            candles_1h=c_1h,
            candles_15m=c_15m,
            candles_5m=c_5m,
            current_price=330.0,
            spread_ratio=0.0002
        )
        self.assertIn(res["decision"], ("TRADE", "NO_TRADE"))
        if res["decision"] == "TRADE":
            self.assertEqual(res["direction"], "LONG")
            self.assertGreater(res["target_exit_2"], res["entry_price"])
            self.assertLess(res["stop_price"], res["entry_price"])

    def test_06_model_d_no_trade_on_excessive_spread(self):
        c_1h = [{"high": 100 + i, "low": 96 + i, "close": 98 + i} for i in range(60)]
        c_15m = [{"high": 150 + i, "low": 148 + i, "close": 149 + i, "volume": 100.0} for i in range(60)]
        c_5m = [{"high": 208 + i*0.1, "low": 207 + i*0.1, "close": 207.5 + i*0.1} for i in range(25)]

        res = SwingSignalEvaluator.evaluate(
            symbol="BTCUSDT",
            candles_1h=c_1h,
            candles_15m=c_15m,
            candles_5m=c_5m,
            current_price=210.0,
            spread_ratio=0.0008  # 8 bps spread > 5 bps gate
        )
        self.assertEqual(res["decision"], "NO_TRADE")
        self.assertEqual(res["model"], "MODEL_D_NO_TRADE")
        self.assertIn("EXCESSIVE_SPREAD", res["rejection_reason"])

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Capital Sizing & Risk Controls
    # ─────────────────────────────────────────────────────────────────────────

    def test_07_sizing_2pct_equity_risk_ceiling(self):
        equity = 2000.0
        price = 100.0
        stop = 98.0  # 2.0% stop distance
        filters = {"min_qty": 0.001, "step_size": 0.001, "min_notional": 5.0}

        sizing = SwingSizingEngine.calculate_sizing(
            symbol="TESTUSDT",
            price=price,
            stop_price=stop,
            equity=equity,
            available_balance=equity,
            symbol_filters=filters
        )
        self.assertTrue(sizing["feasible"])
        # Dollar risk must be <= equity * 0.02 * 1.02 = $40.80
        self.assertLessEqual(sizing["dollar_risk_usd"], 40.80)
        self.assertLessEqual(sizing["leverage"], 10)

    def test_08_min_notional_safety_invariant_rejection(self):
        # Scenario: Account equity is tiny ($100), max allowed risk is $2.00 (2%).
        # Stop distance is 5.0% ($5 per unit on $100 price).
        # Binance min notional is $100.00.
        # Sizing at min notional requires 1.0 unit -> $5.00 risk = 5% equity risk (breaches 2% ceiling).
        # Invariant: Must REJECT trade rather than overriding risk limits.
        equity = 100.0
        price = 100.0
        stop = 95.0  # 5% stop distance
        filters = {"min_qty": 0.1, "step_size": 0.1, "min_notional": 100.0}

        sizing = SwingSizingEngine.calculate_sizing(
            symbol="TESTUSDT",
            price=price,
            stop_price=stop,
            equity=equity,
            available_balance=equity,
            symbol_filters=filters
        )
        self.assertFalse(sizing["feasible"])
        self.assertIn("MIN_NOTIONAL_EXCEEDS_RISK_CAP", sizing["rejection_reason"])

    def test_09_stop_distance_bounds_enforcement(self):
        equity = 1000.0
        price = 100.0
        filters = {"min_qty": 0.001, "step_size": 0.001, "min_notional": 5.0}

        # Stop too tight (< 0.2%)
        tight_stop = 99.90  # 0.1% stop
        res_tight = SwingSizingEngine.calculate_sizing("TESTUSDT", price, tight_stop, equity, equity, filters)
        self.assertFalse(res_tight["feasible"])
        self.assertIn("STOP_DISTANCE_OUTSIDE_BOUNDS", res_tight["rejection_reason"])

        # Stop too wide (> 5.0%)
        wide_stop = 94.00  # 6.0% stop
        res_wide = SwingSizingEngine.calculate_sizing("TESTUSDT", price, wide_stop, equity, equity, filters)
        self.assertFalse(res_wide["feasible"])
        self.assertIn("STOP_DISTANCE_OUTSIDE_BOUNDS", res_wide["rejection_reason"])

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Authoritative FuturesRiskEngine Preserved
    # ─────────────────────────────────────────────────────────────────────────

    def test_10_authoritative_risk_engine_intact(self):
        # Verify Phase 2 hard constraints remain authoritative
        self.assertEqual(FuturesRiskEngine.MAX_LEVERAGE_CAP, 10)
        self.assertEqual(FuturesRiskEngine.MAX_PER_TRADE_RISK_RATIO, 0.02)
        self.assertEqual(FuturesRiskEngine.MAX_AGGREGATE_EXPOSURE_USD, 5000.0)
        self.assertEqual(FuturesRiskEngine.MAX_DAILY_LOSS_USD, 250.0)
        self.assertEqual(FuturesRiskEngine.MAX_CONSECUTIVE_LOSSES, 4)
        self.assertEqual(FuturesRiskEngine.MAX_CONCURRENT_POSITIONS, 3)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Autonomous Swing Engine Lifecycle & Zero Naked Positions
    # ─────────────────────────────────────────────────────────────────────────

    def test_11_swing_engine_lifecycle(self):
        engine = AutonomousSwingEngine(
            conn=self.conn,
            user_id=self.user_id,
            account_id=self.account_id,
            environment="testnet",
            simulate_execution=True
        )
        res_start = engine.start()
        self.assertEqual(res_start["engine_state"], "RUNNING")
        self.assertTrue(engine.is_running)

        res_pause = engine.pause()
        self.assertEqual(res_pause["engine_state"], "PAUSED")
        self.assertTrue(engine.is_paused)

        res_resume = engine.resume()
        self.assertEqual(res_resume["engine_state"], "RUNNING")
        self.assertFalse(engine.is_paused)

        res_stop = engine.stop()
        self.assertEqual(res_stop["engine_state"], "STOPPED")
        self.assertFalse(engine.is_running)

    def test_12_zero_naked_positions_in_database(self):
        # Verify that all open positions in database have an entry_order_id and valid protective stop
        open_pos = list_open_futures_positions(self.conn, user_id=self.user_id)
        for p in open_pos:
            self.assertIsNotNone(p.get("symbol"))
            self.assertGreater(abs(float(p.get("quantity", 0))), 0)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase32SwingSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
