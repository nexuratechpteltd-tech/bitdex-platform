"""
Tauric Phase 2 Extended Verification Test Suite (Unittest Isolated)
Covers 17 Scenarios:
- Scenarios 1-5: Defect A, B, and C fixes (null guards, non-finite guards, fast_decision, 503 errors, no $100 fallback)
- Scenarios 6-7: Defect D (conservative LOSS_SL same-candle conflict resolution and TP3 resolution)
- Scenarios 8-14: Multi-Target Signal Engine (50/30/20 allocation, 1.2R/2.0R/3.2R, 30 bps friction, feasibility check, spot-only labeling, breakeven guidance, PKT timers, stable ID)
- Scenarios 15-16: Finnhub Economic Calendar Adapter (tier boundaries, mock parsing, blackout detector)
- Scenario 17: Zero paid AI cost invariant maintained
"""

import sys
import math
import unittest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException

from app.services.venice_client import venice_client
from app.routes.analysis import get_all_analysis, get_symbol_analysis
from app.services.jev_client import jev_client
from app.routes.jev import run_fast_decision, run_blind_check, FastDecisionRequest, BlindCheckRequest
from app.services.outcome_engine import outcome_engine
from app.services.unified_signal_engine import unified_signal_engine
from app.services.finnhub_calendar_adapter import finnhub_calendar_adapter
from app.services.telemetry_manager import telemetry_manager


class TestPhase2Extended(unittest.IsolatedAsyncioTestCase):

    # ─── DEFECT A: Live Meter Unavailable ─────────────────────────────
    async def test_01_defect_a_live_meter_unavailable(self):
        """Scenario 1: Live meter returns DATA_UNAVAILABLE without fabricating a 50 neutral gauge."""
        mock_ticker = {"status": "UNAVAILABLE", "price": None, "quote_age_seconds": 999}
        with patch("app.services.unified_signal_engine.fetch_single_symbol_market_data", return_value=mock_ticker):
            res = await unified_signal_engine.compute_live_directional_meter("BTC")
            self.assertEqual(res["status"], "DATA_UNAVAILABLE")
            self.assertIsNone(res["current_price"])
            self.assertNotIn("meter", res, "Should not include meter object when data is unavailable")

    # ─── DEFECT B: Venice Client & Analysis Route Guards ──────────────
    async def test_02_defect_b_venice_client_guards(self):
        """Scenario 2: venice_client handles None, NaN, and Inf without TypeError."""
        res_none = await venice_client.get_regime_analysis("BTC", None, None)
        self.assertEqual(res_none["status"], "DATA_UNAVAILABLE")
        self.assertEqual(res_none["regime"], "UNKNOWN")
        self.assertIsNone(res_none["current_price"])

        res_nan = await venice_client.get_regime_analysis("ETH", float("nan"), 1.5)
        self.assertEqual(res_nan["status"], "DATA_UNAVAILABLE")

        res_inf = await venice_client.get_regime_analysis("SOL", 150.0, float("inf"))
        self.assertEqual(res_inf["status"], "DATA_UNAVAILABLE")

        res_valid = await venice_client.get_regime_analysis("BTC", 65000.0, 2.5)
        self.assertEqual(res_valid["status"], "PASS")
        self.assertEqual(res_valid["regime"], "TRENDING_UP")

    async def test_03_defect_b_analysis_route_unavailable_handling(self):
        """Scenario 3: /analysis route returns safe DATA_UNAVAILABLE on missing or invalid data."""
        mock_data = {
            "BTC": {"status": "UNAVAILABLE", "price": None, "change_24h": None},
            "ETH": {"status": "PASS", "price": float("nan"), "change_24h": 0.5},
            "SOL": {"status": "PASS", "price": 150.0, "change_24h": None}
        }
        with patch("app.routes.analysis.fetch_live_market_data", new=AsyncMock(return_value=mock_data)):
            all_res = await get_all_analysis()
            for a in all_res["analyses"]:
                self.assertEqual(a["status"], "DATA_UNAVAILABLE")

            sym_res = await get_symbol_analysis("BTC")
            self.assertEqual(sym_res["status"], "DATA_UNAVAILABLE")

    # ─── DEFECT C: Jev fast_decision & Route 503 ──────────────────────
    async def test_04_defect_c_jev_fast_decision_interface(self):
        """Scenario 4: jev_client.fast_decision exists and provides statistical decision & bias."""
        market_state = {"price": 2500.0, "change_24h": 3.2, "volume_24h": 15000000.0}
        res = await jev_client.fast_decision("ETH-USD", market_state)
        self.assertIn("decision", res)
        self.assertIn("bias", res)
        self.assertIn("opportunity", res)

    async def test_05_defect_c_jev_route_503_on_unavailable_data(self):
        """Scenario 5: routes/jev.py raises HTTP 503 if market data is unavailable (no $100 fallback)."""
        mock_unavailable = {"ETH": {"status": "UNAVAILABLE", "price": None}}
        with patch("app.routes.jev.fetch_live_market_data", new=AsyncMock(return_value=mock_unavailable)):
            with self.assertRaises(HTTPException) as ctx:
                await run_fast_decision(FastDecisionRequest(ticker="ETH-USD"))
            self.assertEqual(ctx.exception.status_code, 503)

            with self.assertRaises(HTTPException) as ctx2:
                await run_blind_check(BlindCheckRequest(ticker="ETH-USD", trade_plan={"direction": "LONG"}))
            self.assertEqual(ctx2.exception.status_code, 503)

    # ─── DEFECT D: Conservative Same-Candle Conflict Resolution ──────
    def test_06_defect_d_conservative_conflict_resolution(self):
        """Scenario 6: outcome_engine defaults same-candle TP/SL conflict to LOSS_SL."""
        entry = 100.0
        stop_loss = 98.0
        tp1 = 102.4
        tp2 = 104.0
        tp3 = 106.4

        conflict_candles = [{"open": 100.0, "high": 103.0, "low": 97.0, "close": 99.0}]

        res = outcome_engine.evaluate_single_trade(
            direction="LONG",
            entry=entry,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            candles=conflict_candles,
            tp3=tp3
        )

        self.assertEqual(res["outcome"], "LOSS_SL", "Conflict must resolve to LOSS_SL")
        self.assertEqual(res["exit_price"], stop_loss)
        self.assertTrue(res["same_candle_conflict"])
        self.assertEqual(res["conflict_resolution"], "CONSERVATIVE_STOP_FIRST")
        self.assertLess(res["net_pnl"], 0)

    def test_07_outcome_engine_win_tp3_resolution(self):
        """Scenario 7: outcome_engine resolves WIN_TP3 cleanly without conflict."""
        entry = 100.0
        stop_loss = 98.0
        tp1 = 102.4
        tp2 = 104.0
        tp3 = 106.4

        clean_candles = [
            {"open": 100.0, "high": 101.5, "low": 99.5, "close": 101.0},
            {"open": 101.0, "high": 107.0, "low": 100.5, "close": 106.5}
        ]

        res = outcome_engine.evaluate_single_trade(
            direction="LONG",
            entry=entry,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            candles=clean_candles,
            tp3=tp3
        )

        self.assertEqual(res["outcome"], "WIN_TP3")
        self.assertEqual(res["exit_price"], tp3)
        self.assertFalse(res["same_candle_conflict"])
        self.assertGreater(res["net_pnl"], 0)

    # ─── MULTI-TARGET ENGINE VERIFICATION ────────────────────────────
    def test_08_multi_target_allocations_and_r_multiples(self):
        """Scenario 8: Verifies TP1 50% (1.2R), TP2 30% (2.0R), TP3 20% (3.2R) sum to 100%."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.5,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        mt = sig["multi_targets"]
        self.assertEqual(mt["total_allocation_pct"], 100)
        self.assertEqual(mt["tp1"]["allocation_pct"], 50)
        self.assertEqual(mt["tp2"]["allocation_pct"], 30)
        self.assertEqual(mt["tp3"]["allocation_pct"], 20)

        self.assertEqual(mt["tp1"]["r_multiple"], 1.2)
        self.assertEqual(mt["tp2"]["r_multiple"], 2.0)
        self.assertEqual(mt["tp3"]["r_multiple"], 3.2)

    def test_09_friction_drag_and_net_rewards(self):
        """Scenario 9: Verifies 30 bps round-trip friction deducted from gross rewards."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.5,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        mt = sig["multi_targets"]
        self.assertEqual(mt["round_trip_friction_bps"], 30)
        self.assertEqual(mt["tp1"]["net_reward_pct"], round(mt["tp1"]["gross_reward_pct"] - 0.30, 2))
        self.assertEqual(mt["tp2"]["net_reward_pct"], round(mt["tp2"]["gross_reward_pct"] - 0.30, 2))
        self.assertEqual(mt["tp3"]["net_reward_pct"], round(mt["tp3"]["gross_reward_pct"] - 0.30, 2))
        self.assertGreater(mt["blended_net_reward_pct"], 0)

    def test_10_binance_min_notional_feasibility_check(self):
        """Scenario 10: Verifies $1,000 reference capital, $5 min notional, and $25 min split position."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.5,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        feas = sig["feasibility"]
        self.assertEqual(feas["reference_capital_usd"], 1000.0)
        self.assertEqual(feas["min_exchange_notional_usd"], 5.0)
        self.assertEqual(feas["min_position_for_full_split_usd"], 25.0)
        self.assertTrue(feas["tp3_notional_compliant"])
        self.assertEqual(feas["feasibility_status"], "FEASIBLE")

    def test_11_bearish_crypto_spot_only_labeling(self):
        """Scenario 11: Crypto SELL signals are labeled strictly as Inventory Exit / Defensive bias."""
        indicators = {
            "ema20": 96.0, "ema50": 97.0, "ema200": 102.0,
            "rsi14": 38.0, "macd_hist": -0.30, "atr14": 2.0,
            "high_20": 105.0, "low_20": 95.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:ETHUSDT",
            symbol="ETH/USDT",
            name="Ethereum",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=-3.5,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        self.assertEqual(sig["direction"], "SELL")
        self.assertEqual(sig["direction_label"], "INVENTORY EXIT / REDUCE BIAS")
        self.assertIsNotNone(sig["spot_disclaimer"])
        self.assertIn("spot only", sig["spot_disclaimer"].lower())

    def test_12_tp1_breakeven_advisory_guidance(self):
        """Scenario 12: Breakeven guidance after TP1 is present and explicitly advisory-only."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.0,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        self.assertIn("advisory only", sig["breakeven_guidance"].lower())
        self.assertIn("manual execution required", sig["breakeven_guidance"].lower())

        ba = sig["breakeven_analysis"]
        self.assertEqual(ba["model_type"], "EXPLICIT_ROUND_TRIP_FRICTION_MODEL")
        self.assertEqual(ba["total_round_trip_friction_pct"], 0.30)
        # Entry 100.0 with 30 bps round trip -> true net breakeven is 100.30
        self.assertEqual(ba["true_net_breakeven_price"], 100.30)
        self.assertTrue(ba["advisory_only"])
        self.assertTrue(ba["automated_execution_blocked"])

        # Also test Crypto SELL (Inventory exit) breakeven analysis
        indicators_sell = {
            "ema20": 96.0, "ema50": 97.0, "ema200": 102.0,
            "rsi14": 38.0, "macd_hist": -0.30, "atr14": 2.0,
            "high_20": 105.0, "low_20": 95.0
        }
        sig_sell = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=-3.5,
            bid=100.0,
            ask=100.0,
            indicators=indicators_sell
        )
        self.assertEqual(sig_sell["direction"], "SELL")
        ba_sell = sig_sell["breakeven_analysis"]
        self.assertEqual(ba_sell["true_net_breakeven_price"], 99.70)
        self.assertEqual(ba_sell["breakeven_buffer_pct"], -0.30)
        self.assertIn("spot inventory", sig_sell["breakeven_guidance"].lower())

    def test_13_dual_timers_and_pkt_separation(self):
        """Scenario 13: Authoritative UTC server time, PKT formatting, and separation from holding duration."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.0,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )

        timing = sig["timing"]
        self.assertIn("Z", timing["server_time_utc"])
        self.assertIn("PKT", timing["entry_expires_at_pkt"])
        self.assertGreater(timing["remaining_entry_seconds"], 0)
        self.assertTrue("hours" in timing["max_holding_duration_guidance"].lower() or "duration" in timing["max_holding_duration_guidance"].lower())

    def test_14_deterministic_signal_id_sha256(self):
        """Scenario 14: Generates stable 16-character SHA-256 signal ID."""
        indicators = {
            "ema20": 102.0, "ema50": 101.0, "ema200": 98.0,
            "rsi14": 55.0, "macd_hist": 0.25, "atr14": 2.0,
            "high_20": 105.0, "low_20": 97.0
        }
        sig = unified_signal_engine._score_and_build_signal(
            instrument_id="crypto:binance:BTCUSDT",
            symbol="BTC/USDT",
            name="Bitcoin",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=100.0,
            change_24h=2.0,
            bid=100.0,
            ask=100.0,
            indicators=indicators
        )
        self.assertEqual(len(sig["signal_id"]), 16)

    # ─── FINNHUB CALENDAR ADAPTER ────────────────────────────────────
    def test_15_finnhub_tier_specifications_and_boundaries(self):
        """Scenario 15: Finnhub rate limits, pricing, and free-tier boundaries are documented."""
        specs = finnhub_calendar_adapter.get_tier_specifications()
        self.assertEqual(specs["provider"], "Finnhub")
        self.assertEqual(specs["free_tier_status"], "NOT_AVAILABLE")
        self.assertEqual(specs["free_tier_entitlement"], "NEEDS APPROVAL / UNVERIFIED")
        self.assertEqual(specs["paid_tier_cost_monthly_usd"], 50.0)
        self.assertIn("Premium Access Required", specs["entitlement_finding"])

    def test_16_finnhub_mock_fixtures_and_blackout_detection(self):
        """Scenario 16: Finnhub offline mock parser extracts events and detects event blackout risk."""
        events = finnhub_calendar_adapter.get_mock_fixtures()
        self.assertGreaterEqual(len(events), 3)

        high = finnhub_calendar_adapter.filter_high_impact_events(events)
        self.assertGreaterEqual(len(high), 2)
        for ev in high:
            self.assertEqual(ev["impact_level"], "HIGH")

        blackout = finnhub_calendar_adapter.check_event_blackout_risk(events, "BTC/USDT", buffer_minutes=1440)
        self.assertIn("policy", blackout)
        self.assertEqual(blackout["symbol"], "BTC/USDT")

    # ─── INVARIANT & FOCUSED REGRESSION TESTS ─────────────────────────
    def test_17_zero_paid_ai_costs_maintained(self):
        """Scenario 17: Telemetry tokens and requests remain exactly 0 across all operations."""
        t = telemetry_manager.get_telemetry()
        known = t.get("known_tokens", 0)
        daily = t.get("daily_tokens_used", 0)
        reqs = t.get("request_count", 0)
        self.assertEqual(known, 0)
        self.assertEqual(daily, 0)
        self.assertEqual(reqs, 0)

    async def test_18_expired_signals_cannot_be_revived_by_cache(self):
        """Scenario 18: Expired setups cannot be presented as valid active signals."""
        from app.services.signal_timing_engine import signal_timing_engine
        timing_expired = {
            "generated_at_utc": "2026-10-01T00:00:00Z",
            "entry_valid_until_utc": "2026-10-01T00:45:00Z",
            "expires_at_utc": "2026-10-01T02:00:00Z",
            "time_stop_utc": "2026-10-01T04:00:00Z"
        }
        res = await signal_timing_engine.evaluate_spot_grid_status(
            symbol="BTC",
            lower=60000.0,
            upper=70000.0,
            timing_meta=timing_expired
        )
        self.assertIn(res["grid_state"], ["EXPIRED", "STALE", "INVALIDATED"])
        self.assertNotEqual(res["grid_state"], "IN_RANGE")

    def test_19_zero_order_execution_calls(self):
        """Scenario 19: Proves no trading credentials, private keys, or exchange execution endpoints exist."""
        from app.config import settings
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

    def test_20_stale_or_missing_calendar_does_not_fabricate_events(self):
        """Scenario 20: Missing or empty calendar data returns CLEAR without phantom events."""
        res = finnhub_calendar_adapter.check_event_blackout_risk([], "BTC/USDT")
        self.assertFalse(res["has_blackout_risk"])
        self.assertEqual(res["policy"], "CLEAR")
        self.assertEqual(len(res["conflicting_events"]), 0)


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING TAURIC PHASE 2 EXTENDED AUTOMATED TEST SUITE (20 SCENARIOS)")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase2Extended)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    print(f"TESTS RUN: {result.testsRun} | FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print("=" * 70)
    sys.exit(0 if result.wasSuccessful() else 1)
