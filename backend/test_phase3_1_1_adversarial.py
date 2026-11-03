"""
Tauric Phase 3.1.1 Adversarial Verification Test Suite
Covers Verification B & Verification C:
1. Required clearance plus UNKNOWN returns WAIT.
2. Required clearance plus STALE or UNAVAILABLE returns WAIT.
3. is_blackout=False cannot override an unsafe status.
4. An unclassified relevant event cannot yield CLEAR.
5. A fresh, successfully checked window with no relevant events can return CLEAR.
6. Optional screening behaves as documented without claiming news clearance.
7. Cached and legacy signal paths cannot convert unknown risk into an actionable cleared signal.
8. A calendar surprise alone cannot generate a trade recommendation or execution action.
9. Interpretation review: boundaries, missing values, revised values, unexpected units, rate decisions (hikes, cuts, holds), ambiguous indicators (MIXED), and unmapped series (UNKNOWN).
"""

import math
import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.services.finance_calendar_adapter import (
    FinanceCalendarAdapter,
    NormalizedEconomicEvent,
    FINANCE_CALENDAR_SPECS,
    AMBIGUOUS_SERIES,
    EVENT_INTERPRETATION_RULES
)
from app.services.regime_engine import (
    DeterministicMarketRegimeEngine,
    MarketRegime,
    EventSeverity,
    MacroEvent,
    RegimeEngineConfig
)
from app.services.unified_signal_engine import unified_signal_engine
from app.services.telemetry_manager import telemetry_manager
from app.config import settings


class TestPhase311AdversarialVerification(unittest.TestCase):

    def setUp(self):
        self.adapter = FinanceCalendarAdapter(enabled=False)
        self.regime_engine = DeterministicMarketRegimeEngine()
        self.now_utc = datetime.now(timezone.utc)
        self.now_ms = int(self.now_utc.timestamp() * 1000)

    # =========================================================================
    # VERIFICATION B — ADVERSARIAL TESTS
    # =========================================================================

    def test_01_required_clearance_plus_unknown_returns_wait(self):
        """1. Required clearance plus UNKNOWN returns WAIT."""
        self.adapter.enabled = False
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.5,
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.event_risk_status, "DISABLED")
        self.assertFalse(res.is_blackout)

    def test_02_required_clearance_plus_stale_or_unavailable_returns_wait(self):
        """2. Required clearance plus STALE or UNAVAILABLE returns WAIT."""
        # A. Stale (>1h)
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc - timedelta(hours=3)
        res_stale = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.5,
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res_stale.status, "WAIT")
        self.assertEqual(res_stale.event_risk_status, "STALE")

        # B. Unavailable (Error)
        mock_error = MagicMock()
        mock_error.enabled = True
        mock_error.is_stale.return_value = False
        mock_error._last_retrieval_utc = self.now_utc
        mock_error.is_reliable.return_value = True
        mock_error.get_events.side_effect = ConnectionResetError("HTTP connection reset by peer")
        res_unavail = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.5,
            calendar_source=mock_error,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res_unavail.status, "WAIT")
        self.assertEqual(res_unavail.event_risk_status, "UNAVAILABLE")

    def test_03_is_blackout_false_cannot_override_unsafe_status(self):
        """3. is_blackout=False cannot override an unsafe status to return PASS."""
        self.adapter.enabled = False
        is_bo, regime, reasons, _ = self.regime_engine.check_event_blackout(self.now_ms, self.adapter, "BTCUSDT")
        # is_blackout is False because provider is disabled, NOT confirmed clear!
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=4.0,  # strong positive technical momentum
            indicators={"rsi": 60.0, "ema50": 67000.0, "ema200": 65000.0},
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        # Even with perfect bullish momentum and EMA alignment, cannot return PASS!
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertNotEqual(res.status, "PASS")

    def test_04_unclassified_relevant_event_cannot_yield_clear(self):
        """4. An unclassified relevant event within the risk window cannot yield CLEAR."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._last_error = None
        raw_events = [{
            "id": "unknown-impact-speech",
            "series": "central-bank-speech",
            "title": "Central Bank Keynote Address",
            "country": "US",
            "impact": "UNSPECIFIED",  # unknown/missing impact
            "release_at_utc": (self.now_utc + timedelta(minutes=10)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(raw_events)

        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "UNKNOWN")
        self.assertNotEqual(risk["event_risk_status"], "CLEAR")
        self.assertEqual(risk["policy"], "UNCLASSIFIED_EVENT_RISK")

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.0,
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.event_risk_status, "UNKNOWN")

    def test_05_fresh_checked_window_with_no_relevant_events_returns_clear(self):
        """5. A fresh, successfully checked window with no relevant events can return CLEAR."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._last_error = None
        # Loaded events are scheduled 24 hours away (outside the ±30m risk window)
        raw_events = [{
            "id": "fomc-tomorrow",
            "series": "fomc",
            "title": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "release_at_utc": (self.now_utc + timedelta(hours=24)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(raw_events)

        # Fresh window with no active events returns CLEAR
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "CLEAR")
        self.assertFalse(risk["is_blackout"])

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.event_risk_status, "CLEAR")

    def test_06_optional_screening_behaves_as_documented_without_claiming_clearance(self):
        """6. Optional screening behaves as documented without claiming news clearance."""
        self.adapter.enabled = False
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=False  # Optional screening mode
        )
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.event_risk_status, "DISABLED")
        self.assertNotEqual(res.event_risk_status, "CLEAR")

    def test_07_cached_and_legacy_signal_paths_cannot_convert_unknown_risk_to_cleared(self):
        """7. Cached and legacy signal paths cannot convert unknown risk into an actionable cleared signal."""
        # Run generate_unified_signals asynchronously
        feed1 = asyncio.run(unified_signal_engine.generate_unified_signals(force_refresh=True))
        feed2 = asyncio.run(unified_signal_engine.generate_unified_signals(force_refresh=False))

        for feed_name, feed in [("Fresh Feed", feed1), ("Cached Feed", feed2)]:
            self.assertEqual(feed["calendar"]["status"], "DISABLED", f"{feed_name} calendar must be DISABLED")
            self.assertEqual(feed["calendar"]["event_risk_policy"], "UNKNOWN", f"{feed_name} policy must be UNKNOWN")
            self.assertIn("disabled in production isolation", feed["calendar"]["warning"])

            signals = feed.get("signals", [])
            self.assertGreater(len(signals), 0, f"{feed_name} must contain signals")
            for sig in signals:
                risk = sig.get("event_risk", {})
                self.assertEqual(risk.get("status"), "UNKNOWN", f"Signal {sig['symbol']} event_risk status must be UNKNOWN")
                self.assertFalse(risk.get("is_blackout"), f"Signal {sig['symbol']} is_blackout must be False")
                self.assertEqual(risk.get("recommendation"), "WAIT_OR_MANUAL_VERIFICATION")
                be = sig.get("breakeven_analysis", {})
                self.assertTrue(be.get("automated_execution_blocked"), "Automated execution must be blocked")

    def test_08_calendar_surprise_alone_cannot_generate_trade_recommendation(self):
        """8. A calendar surprise alone cannot generate a trade recommendation or execution action."""
        # Massive hawkish CPI surprise (+10.0%)
        interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="us-cpi",
            actual=13.5,
            forecast=3.5,
            previous=3.4
        )
        self.assertEqual(interp["status"], "EVALUATED")
        self.assertEqual(interp["surprise_diff"], 10.0)
        self.assertEqual(interp["currency_bias"], "BULLISH")
        self.assertEqual(interp["crypto_bias"], "BEARISH")

        # Must NOT contain order fields or execution parameters
        self.assertNotIn("action", interp)
        self.assertNotIn("order_type", interp)
        self.assertNotIn("limit_price", interp)
        self.assertNotIn("position_size", interp)
        self.assertIn("not a trade recommendation", interp["disclaimer"].lower())
        self.assertIn("automated trade execution is strictly disabled", interp["disclaimer"].lower())

    # =========================================================================
    # VERIFICATION C — INTERPRETATION BOUNDARIES & EDGE CASES
    # =========================================================================

    def test_interpretation_boundary_missing_values(self):
        """Missing actual or forecast returns UNAVAILABLE without synthetic fills."""
        # Missing actual
        r1 = FinanceCalendarAdapter.interpret_actual_vs_forecast("us-cpi", None, 3.1)
        self.assertEqual(r1["status"], "UNAVAILABLE")
        self.assertIsNone(r1["surprise_diff"])
        self.assertEqual(r1["currency_bias"], "NEUTRAL")

        # Missing forecast
        r2 = FinanceCalendarAdapter.interpret_actual_vs_forecast("us-cpi", 3.2, None)
        self.assertEqual(r2["status"], "UNAVAILABLE")
        self.assertIsNone(r2["surprise_diff"])

    def test_interpretation_boundary_exact_match_zero_variance(self):
        """Exact match print (actual == forecast) yields IN_LINE surprise direction and NEUTRAL bias."""
        r = FinanceCalendarAdapter.interpret_actual_vs_forecast("us-cpi", 3.2, 3.2, previous=3.4)
        self.assertEqual(r["status"], "EVALUATED")
        self.assertEqual(r["surprise_diff"], 0.0)
        self.assertEqual(r["surprise_direction"], "IN_LINE")
        self.assertEqual(r["currency_bias"], "NEUTRAL")
        self.assertEqual(r["crypto_bias"], "NEUTRAL")

    def test_interpretation_revised_prior_capture(self):
        """Revised prior values are captured with is_revised flag and separate fields."""
        r = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="us-jobs-report",
            actual=210.0,
            forecast=180.0,
            previous=150.0,
            raw_actual="210K",
            raw_forecast="180K",
            raw_previous="150K",
            revised_previous=165.0
        )
        self.assertTrue(r["is_revised"])
        self.assertEqual(r["previous_value"], 150.0)
        self.assertEqual(r["revised_previous"], 165.0)
        self.assertEqual(r["raw_actual"], "210K")
        self.assertEqual(r["surprise_direction"], "POSITIVE")

    def test_interpretation_rate_decisions_all_modes(self):
        """Rate decisions handle hikes, cuts, and holds with explicit comparison basis."""
        # 1. Rate Hike
        hike = FinanceCalendarAdapter.interpret_actual_vs_forecast("fomc", 5.50, 5.25, previous=5.25)
        self.assertEqual(hike["currency_bias"], "BULLISH")
        self.assertEqual(hike["crypto_bias"], "BEARISH")
        self.assertIn("benchmark", hike["comparison_basis"].lower())

        # 2. Rate Cut
        cut = FinanceCalendarAdapter.interpret_actual_vs_forecast("fomc", 4.75, 5.00, previous=5.25)
        self.assertEqual(cut["currency_bias"], "BEARISH")
        self.assertEqual(cut["crypto_bias"], "BULLISH")

        # 3. Rate Hold (forecast=5.25, actual=5.25, prior=5.25)
        hold = FinanceCalendarAdapter.interpret_actual_vs_forecast("fomc", 5.25, 5.25, previous=5.25)
        self.assertEqual(hold["currency_bias"], "NEUTRAL")
        self.assertEqual(hold["crypto_bias"], "NEUTRAL")

    def test_interpretation_ambiguous_and_unmapped_series(self):
        """Ambiguous indicators return MIXED; unmapped indicators return UNKNOWN."""
        # Ambiguous series
        for amb in ["trade-balance", "retail-inventories", "crude-oil-stocks", "michigan-sentiment", "average-hourly-earnings"]:
            res = FinanceCalendarAdapter.interpret_actual_vs_forecast(amb, 150.0, 100.0)
            self.assertEqual(res["status"], "MIXED")
            self.assertEqual(res["currency_bias"], "MIXED")
            self.assertEqual(res["crypto_bias"], "MIXED")

        # Unmapped series
        unmapped = FinanceCalendarAdapter.interpret_actual_vs_forecast("completely-unknown-metric", 99.0, 50.0)
        self.assertEqual(unmapped["status"], "UNKNOWN")
        self.assertEqual(unmapped["currency_bias"], "UNKNOWN")
        self.assertEqual(unmapped["crypto_bias"], "UNKNOWN")
        self.assertIn("rejected for safety", unmapped["model_interpretation"].lower())


if __name__ == "__main__":
    unittest.main()
