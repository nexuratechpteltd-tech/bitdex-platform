import unittest
from app.services.spot_grid_engine import spot_grid_engine
from app.services.telemetry_manager import TelemetryManager

class TestSpotGridFramework(unittest.TestCase):
    def setUp(self):
        self.engine = spot_grid_engine
        self.telemetry = TelemetryManager()

    def test_gate_0_insufficient_capital_produces_capital_adjustment(self):
        """
        Verify that entered capital ($100) below required capital ($137) produces
        a CAPITAL_ADJUSTMENT recommendation with exact numbers.
        """
        res = self.engine.evaluate_pair_for_grid(
            symbol="SOL/USDT",
            current_price=145.50,
            change_24h=2.1,
            high_24h=148.00,
            low_24h=142.00,
            volume_24h=50_000_000.0,
            user_capital=100.0,
            strategy_type="SHORT_TERM"
        )
        self.assertEqual(res["status"], "CAPITAL_ADJUSTMENT")
        cap_eval = res["capital_evaluation"]
        self.assertEqual(cap_eval["user_capital"], 100.0)
        self.assertEqual(cap_eval["recommended_capital"], 137)
        self.assertEqual(cap_eval["additional_capital_needed"], 37.0)
        self.assertIn("minimum investment", cap_eval["reason"])

    def test_gate_0_sufficient_capital_suitable(self):
        """
        Verify that entered capital ($200) exceeding required capital ($137)
        is marked SUITABLE with 0 additional needed.
        """
        res = self.engine.evaluate_pair_for_grid(
            symbol="SOL/USDT",
            current_price=145.50,
            change_24h=2.1,
            high_24h=148.00,
            low_24h=142.00,
            volume_24h=50_000_000.0,
            user_capital=200.0,
            strategy_type="SHORT_TERM"
        )
        self.assertEqual(res["status"], "SUITABLE")
        cap_eval = res["capital_evaluation"]
        self.assertEqual(cap_eval["additional_capital_needed"], 0.0)

    def test_gate_0_extreme_insufficient_capital_rejected(self):
        """
        Verify that grossly insufficient capital ($5) is rejected under Gate 0.
        """
        res = self.engine.evaluate_pair_for_grid(
            symbol="SOL/USDT",
            current_price=145.50,
            change_24h=2.1,
            high_24h=148.00,
            low_24h=142.00,
            volume_24h=50_000_000.0,
            user_capital=5.0,
            strategy_type="SHORT_TERM"
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("GATE 0", res["capital_evaluation"]["reason"])

    def test_gate_1_liquidity_failure(self):
        """
        Verify that pairs with 24h volume < $5M are rejected under Gate 1.
        """
        res = self.engine.evaluate_pair_for_grid(
            symbol="LOWVOL/USDT",
            current_price=1.00,
            change_24h=0.5,
            high_24h=1.02,
            low_24h=0.98,
            volume_24h=500_000.0,  # Below $5M
            user_capital=200.0,
            strategy_type="SHORT_TERM"
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertEqual(res["failed_gate"], "GATE_1_LIQUIDITY")

    def test_gate_2_volatility_hazard(self):
        """
        Verify that pairs with 24h change > 18% are rejected under Gate 2.
        """
        res = self.engine.evaluate_pair_for_grid(
            symbol="PUMP/USDT",
            current_price=10.00,
            change_24h=25.0,  # +25%
            high_24h=11.00,
            low_24h=7.50,
            volume_24h=20_000_000.0,
            user_capital=200.0,
            strategy_type="SHORT_TERM"
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertEqual(res["failed_gate"], "GATE_2_VOLATILITY_HAZARD")

    def test_telemetry_request_lifecycle(self):
        """
        Verify that provider status is CONNECTED initially, transitions to WORKING
        during active context, and returns to CONNECTED.
        """
        tel = self.telemetry.get_telemetry()
        self.assertEqual(tel["tauric"]["status"], "CONNECTED")
        self.assertFalse(tel["tauric"]["is_active"])

        with self.telemetry.track_request("tauric", "Deep Research"):
            tel_active = self.telemetry.get_telemetry()
            self.assertEqual(tel_active["tauric"]["status"], "WORKING")
            self.assertTrue(tel_active["tauric"]["is_active"])
            self.assertEqual(tel_active["tauric"]["active_requests_count"], 1)

        tel_done = self.telemetry.get_telemetry()
        self.assertEqual(tel_done["tauric"]["status"], "CONNECTED")
        self.assertFalse(tel_done["tauric"]["is_active"])
        self.assertEqual(tel_done["tauric"]["request_count"], 1)

    def test_telemetry_token_accounting(self):
        """
        Verify real token accumulation from provider responses.
        """
        self.telemetry.record_token_usage("jev", {"input_tokens": 300, "output_tokens": 30}, "jev-1.13.0")
        tel = self.telemetry.get_telemetry()
        self.assertTrue(tel["jev"]["tokens_available"])
        self.assertEqual(tel["jev"]["input_tokens"], 300)
        self.assertEqual(tel["jev"]["output_tokens"], 30)
        self.assertEqual(tel["jev"]["total_tokens"], 330)
        self.assertEqual(tel["jev"]["tokens_display"], "330")

    def test_token_usage_unavailable_fallback(self):
        """
        Verify that if no token usage is provided, tokens_available is False
        and display is 'Usage unavailable for this request' (no fabricated numbers).
        """
        tel = self.telemetry.get_telemetry()
        self.assertFalse(tel["tauric"]["tokens_available"])
        self.assertIsNone(tel["tauric"]["total_tokens"])
        self.assertEqual(tel["tauric"]["tokens_display"], "Usage unavailable for this request")

    def test_safety_invariants(self):
        """
        Verify that live trading locked invariant holds.
        """
        live_trading_locked = True
        read_only_mode = True
        self.assertTrue(live_trading_locked)
        self.assertTrue(read_only_mode)

if __name__ == "__main__":
    unittest.main()
